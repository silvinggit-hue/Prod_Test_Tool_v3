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


@dataclass(frozen=True)
class ParsedDiscoveryPacket:
    ip: str
    mac: str
    mac12: str
    model: str | None = None
    firmware: str | None = None
    lens: str | None = None
    note: str | None = None


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
    best: Optional[tuple[int, bytes, str]] = None

    for marker in MAC_MARKERS:
        start = 0
        while True:
            idx = pkt.find(marker, start)
            if idx == -1:
                break

            cand_offs = [idx + len(marker) - 1, idx + len(marker), idx + len(marker) + 1]

            for mac_off in cand_offs:
                if mac_off < 0 or mac_off + 6 > len(pkt):
                    continue

                mac6 = pkt[mac_off:mac_off + 6]
                if not is_probable_unicast_mac(mac6):
                    continue

                why = f"marker:{marker.hex()}@{mac_off}"

                if mac6.startswith(TRUEN_OUI):
                    return mac_off, mac6, why

                if best is None:
                    best = (mac_off, mac6, why)

            start = idx + 1

    return best


def extract_model_fw_after_mac(pkt: bytes, mac_off: int | None) -> tuple[str | None, str | None]:
    if mac_off is None:
        return None, None

    start = mac_off + 6
    search = pkt[start:start + 96]

    runs: list[str] = []
    buf = bytearray()

    def flush() -> None:
        nonlocal buf
        if len(buf) >= 4:
            try:
                runs.append(buf.decode("ascii"))
            except Exception:
                pass
        buf = bytearray()

    for b in search:
        if 0x20 <= b <= 0x7E:
            buf.append(b)
        else:
            flush()
    flush()

    if not runs:
        return None, None

    model = runs[0]
    fw = runs[1] if len(runs) >= 2 else None

    def looks_fw(s: str) -> bool:
        return bool(re.match(r"^[Vv]\d", s)) or ("." in s and any(c.isdigit() for c in s))

    def looks_model(s: str) -> bool:
        return ("-" in s and len(s) >= 6) or bool(re.match(r"^[A-Za-z]{1,4}[A-Za-z0-9\-]{4,}$", s))

    if fw and looks_model(fw) and looks_fw(model):
        model, fw = fw, model

    if not looks_model(model):
        for s in runs:
            if looks_model(s):
                model = s
                break

    if fw and not looks_fw(fw):
        for s in runs:
            if s != model and looks_fw(s):
                fw = s
                break

    return model, fw


def parse_discovery_packet(pkt: bytes, src_ip: str) -> ParsedDiscoveryPacket | None:
    if not is_discovery_response(pkt):
        return None

    mac_found = extract_mac_by_marker(pkt)
    if not mac_found:
        return None

    mac_off, mac6, mac_note = mac_found
    mac = mac6_to_str(mac6)
    mac12 = mac6.hex().upper().zfill(12)
    model, firmware = extract_model_fw_after_mac(pkt, mac_off)
    lens = str(len(pkt))

    return ParsedDiscoveryPacket(
        ip=src_ip,
        mac=mac,
        mac12=mac12,
        model=model,
        firmware=firmware,
        lens=lens,
        note=mac_note,
    )