from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


RSP_SIG = bytes.fromhex("23 68 54 10")
REQ24 = bytes.fromhex("34 52 34 87 01 05") + b"\x00" * (24 - 6)

MAC_MARKERS = [
    b"\x48\x00\x00\x00\x00",
]

TRUEN_OUI = b"\x00\x1c\x63"

ASCII_WINDOW_LEN = 192


@dataclass(frozen=True)
class ParsedDiscoveryPacket:
    ip: str
    mac: str
    mac12: str
    model: str | None = None
    firmware: str | None = None
    lens: str | None = None
    note: str | None = None


def normalize_mac12(mac: str) -> str:
    raw = (mac or "").strip()
    if raw.lower().startswith("0x"):
        raw = raw[2:]
    raw = re.sub(r"[^0-9a-fA-F]", "", raw)
    if len(raw) != 12:
        raise ValueError(f"invalid mac12: {mac}")
    return raw.upper()


def mac6_to_str(mac6: bytes) -> str:
    return ":".join(f"{b:02X}" for b in mac6)


def is_probable_unicast_mac(mac6: bytes) -> bool:
    if len(mac6) != 6:
        return False
    if mac6 == b"\x00" * 6:
        return False
    if mac6[0] & 0x01:
        return False
    return True


def is_discovery_response(pkt: bytes) -> bool:
    return len(pkt) >= 4 and pkt.startswith(RSP_SIG)


def extract_mac_by_marker(pkt: bytes) -> Optional[tuple[int, bytes, str]]:
    """
    marker 뒤 MAC offset이 1바이트 정도 흔들리는 패킷 편차를 허용한다.
    TRUEN OUI가 보이면 우선 사용하고, 아니면 가장 먼저 잡힌 후보를 사용한다.
    """
    best: Optional[tuple[int, bytes, str]] = None

    for marker in MAC_MARKERS:
        start = 0
        while True:
            idx = pkt.find(marker, start)
            if idx == -1:
                break

            candidate_offsets = [
                idx + len(marker) - 1,
                idx + len(marker),
                idx + len(marker) + 1,
            ]

            for mac_off in candidate_offsets:
                if mac_off < 0 or mac_off + 6 > len(pkt):
                    continue

                mac6 = pkt[mac_off : mac_off + 6]
                if not is_probable_unicast_mac(mac6):
                    continue

                why = f"marker:{marker.hex()}@{mac_off}"

                if mac6.startswith(TRUEN_OUI):
                    return mac_off, mac6, why

                if best is None:
                    best = (mac_off, mac6, why)

            start = idx + 1

    return best


def _clean_ascii_token(text: str | None) -> str | None:
    if text is None:
        return None
    s = "".join(ch for ch in str(text) if 0x20 <= ord(ch) <= 0x7E)
    s = " ".join(s.split()).strip().strip("\x00")
    return s or None


def _collect_ascii_tokens(blob: bytes, *, min_len: int = 1) -> list[str]:
    runs: list[str] = []
    buf = bytearray()

    def flush() -> None:
        nonlocal buf
        if len(buf) >= min_len:
            try:
                raw = buf.decode("ascii", errors="ignore").strip()
                cleaned = _clean_ascii_token(raw)
                if cleaned:
                    runs.append(cleaned)
            except Exception:
                pass
        buf = bytearray()

    for value in blob:
        if 0x20 <= value <= 0x7E:
            buf.append(value)
        else:
            flush()
    flush()

    return runs


def _looks_fw(token: str) -> bool:
    s = _clean_ascii_token(token)
    if not s:
        return False
    return bool(re.match(r"^[Vv]\d[0-9A-Za-z._\-]*$", s))


def _looks_model(token: str) -> bool:
    s = _clean_ascii_token(token)
    if not s:
        return False
    return bool(re.match(r"^[A-Z][A-Z0-9]{1,10}-[A-Z0-9]{4,20}$", s))


def _sanitize_model_token(token: str | None) -> str | None:
    """
    discovery 패킷 모델명은 현재 현장 기준으로
    앞에 불필요한 1글자가 더 붙는 경우가 있다.

    규칙:
    - 앞 1글자를 제거한 결과가 T계열 모델(TCAM / TN / TX / TA...)이면 제거값 사용
    - 아니면 OEM 모델일 수 있으므로 원문 유지
    """
    s = _clean_ascii_token(token)
    if not s:
        return None

    # 앞쪽 비정상 잡문자 제거
    while s and not s[0].isalnum():
        s = s[1:]

    if not s:
        return None

    # 모델 패턴 추출
    m = re.search(r"[A-Z][A-Z0-9]{1,12}-[A-Z0-9]{4,24}", s)
    if m:
        s = m.group(0)

    # 앞 1글자를 제거했을 때 T계열 모델이면 그 값을 사용
    if len(s) > 1:
        trimmed = s[1:].strip()
        if re.match(r"^T[A-Z0-9]{1,12}-[A-Z0-9]{4,24}$", trimmed):
            return trimmed

    # 그 외는 OEM 포함 원문 그대로 유지
    return s or None


def _extract_model_and_fw(tokens: list[str]) -> tuple[str | None, str | None]:
    if not tokens:
        return None, None

    cleaned = [_clean_ascii_token(t) for t in tokens]
    cleaned = [t for t in cleaned if t]

    if not cleaned:
        return None, None

    fw_idx = -1
    fw: str | None = None

    for idx, token in enumerate(cleaned):
        if _looks_fw(token):
            fw_idx = idx
            fw = token
            break

    model: str | None = None

    # 1순위: 펌웨어 바로 앞 token
    if fw_idx > 0:
        model = _sanitize_model_token(cleaned[fw_idx - 1])

    # 2순위: 하이픈 포함 token 중 모델 패턴 후보
    if not model:
        for token in cleaned:
            normalized = _sanitize_model_token(token)
            if normalized and _looks_model(normalized):
                model = normalized
                break

    # 3순위: 마지막 fallback
    if not model and cleaned:
        model = _sanitize_model_token(cleaned[0])

    return model, fw


def extract_model_fw_after_mac(pkt: bytes, mac_off: int | None) -> tuple[str | None, str | None]:
    if mac_off is None:
        return None, None

    start = mac_off + 6
    search = pkt[start : start + ASCII_WINDOW_LEN]

    tokens = _collect_ascii_tokens(search, min_len=1)
    model, fw = _extract_model_and_fw(tokens)

    return model, fw


def parse_discovery_packet(pkt: bytes, src_ip: str) -> ParsedDiscoveryPacket | None:
    if not is_discovery_response(pkt):
        return None

    mac_found = extract_mac_by_marker(pkt)
    if not mac_found:
        return None

    mac_off, mac6, mac_note = mac_found
    model, firmware = extract_model_fw_after_mac(pkt, mac_off)

    return ParsedDiscoveryPacket(
        ip=src_ip,
        mac=mac6_to_str(mac6),
        mac12=mac6.hex().upper().zfill(12),
        model=model or "-",
        firmware=firmware or "-",
        lens=str(len(pkt)),
        note=mac_note or "-",
    )