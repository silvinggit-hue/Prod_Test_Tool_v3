from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

from domain.errors.app_error import AppError
from infra.discovery.packet_parser import RSP_SIG, extract_mac_by_marker, normalize_mac12


PORT = 64988
LIMITED_BCAST = "255.255.255.255"

AES_KEY_16 = b"truen is the wor"
CTR_NONCE_8 = b"fprintf("

REQ24 = bytes.fromhex("34 52 34 87 01 05") + b"\x00" * (24 - 6)
REQ64_SCAN = bytes.fromhex("34 52 34 87 03 05") + b"\x00" * (64 - 6)
REQ64_WRITE = bytes.fromhex("34 52 34 87 04 05") + b"\x00" * (64 - 6)

SCAN_REPEAT = 1
SCAN_INTERVAL = 0.05


@dataclass(frozen=True)
class ResetRequest:
    mac12: str
    bind_ip: str | None = None
    mask_bits: int = 24
    port: int = PORT
    device_ip_hint: str | None = None
    scan_seconds: float = 2.5
    seed_sweep: int = 60
    write_seq: int = 2
    write_gap: float = 0.004
    ack_wait_sec: float = 0.2
    ignore_self: bool = False
    bf96_step: int = 1
    ack_any_ip: bool = False


@dataclass(frozen=True)
class ResetResult:
    ok: bool
    mac12: str
    device_ip: str | None = None
    scan_hit: bool = False
    ack_seen: bool = False
    error_kind: str = ""
    error_message: str = ""
    error_detail: str = ""


@dataclass(frozen=True)
class BatchResetItem:
    mac12: str
    device_ip_hint: str | None = None


@dataclass(frozen=True)
class BatchResetRequest:
    items: list[BatchResetItem]
    bind_ip: str | None = None
    mask_bits: int = 24
    port: int = PORT
    scan_seconds: float = 2.5
    seed_sweep: int = 60
    write_seq: int = 2
    write_gap: float = 0.004
    ack_wait_sec: float = 0.2
    ignore_self: bool = False
    bf96_step: int = 1
    ack_any_ip: bool = False


@dataclass(frozen=True)
class BatchResetResult:
    ok: bool
    results: dict[str, ResetResult]


def _subproc_hidden_flags():
    if os.name != "nt":
        return {}, {}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
    si.wShowWindow = 0
    return {"creationflags": creationflags, "startupinfo": si}, {"stderr": subprocess.DEVNULL}


def _run_capture_hidden(cmd_list: list[str], *, text=True, encoding="utf-8", errors="ignore") -> str:
    kw, errkw = _subproc_hidden_flags()
    p = subprocess.run(
        cmd_list,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        text=text,
        encoding=encoding,
        errors=errors,
        shell=False,
        **errkw,
        **kw,
    )
    return (p.stdout or "").strip()


def _powershell_json(cmd: str) -> Optional[object]:
    try:
        out = _run_capture_hidden(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                cmd,
            ],
            encoding="utf-8",
            errors="ignore",
        )
        if not out:
            return None
        return json.loads(out)
    except Exception:
        return None


def compute_directed_bcast(ip: str, mask_bits: int) -> str:
    parts = ip.split(".")
    if len(parts) != 4:
        raise ValueError(f"invalid ipv4: {ip}")
    ip_int = 0
    for p in parts:
        ip_int = (ip_int << 8) | int(p)
    mask = (0xFFFFFFFF << (32 - int(mask_bits))) & 0xFFFFFFFF
    bcast = (ip_int & mask) | (~mask & 0xFFFFFFFF)
    return ".".join(str((bcast >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def open_udp_socket(bind_ip: str, port: int, timeout: float = 0.05) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind((bind_ip, port))
    s.settimeout(float(timeout))
    return s


def safe_close_socket(sock: socket.socket | None) -> None:
    if sock is None:
        return
    try:
        sock.close()
    except Exception:
        pass


def get_local_ipv4() -> str:
    try:
        t = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        t.connect(("8.8.8.8", 53))
        ip = t.getsockname()[0]
        t.close()
        return ip
    except Exception:
        return "0.0.0.0"


def autodetect_bind_and_prefix() -> Tuple[str, int]:
    data = _powershell_json(
        "Get-NetIPConfiguration | "
        "Select-Object InterfaceAlias,IPv4Address,IPv4DefaultGateway | "
        "ConvertTo-Json -Depth 4"
    )

    def _iter_items(obj):
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            return [obj]
        return []

    for item in _iter_items(data):
        gw = item.get("IPv4DefaultGateway")
        v4 = item.get("IPv4Address")
        if not gw or not v4:
            continue
        v4_list = v4 if isinstance(v4, list) else [v4]
        for a in v4_list:
            ip = a.get("IPAddress")
            prefix = a.get("PrefixLength")
            if ip and prefix:
                return str(ip), int(prefix)

    ip = get_local_ipv4()
    if ip == "0.0.0.0":
        raise RuntimeError("Failed to auto-detect local IPv4. Use bind explicitly.")
    return ip, 24


def get_all_ipv4_prefixes_windows() -> List[Tuple[str, int]]:
    if os.name != "nt":
        return []

    data = _powershell_json(
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.254.*' } | "
        "Select-Object IPAddress,PrefixLength | "
        "ConvertTo-Json -Depth 3"
    )
    out: List[Tuple[str, int]] = []

    def _iter_items(obj):
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            return [obj]
        return []

    for item in _iter_items(data):
        ip = item.get("IPAddress")
        pr = item.get("PrefixLength")
        if ip and pr:
            out.append((str(ip), int(pr)))

    uniq: List[Tuple[str, int]] = []
    seen = set()
    for ip, pr in out:
        key = (ip, pr)
        if key not in seen:
            uniq.append(key)
            seen.add(key)
    return uniq


def get_local_ipv4_set_windows() -> Set[str]:
    return set(ip for ip, _ in get_all_ipv4_prefixes_windows())


def find_ip_by_mac_windows(mac6: bytes) -> Optional[str]:
    if os.name != "nt":
        return None

    mac = mac6.hex().lower()
    data = _powershell_json(
        "Get-NetNeighbor -AddressFamily IPv4 | "
        "Select-Object IPAddress,LinkLayerAddress,State | "
        "ConvertTo-Json -Depth 3"
    )

    def _iter_items(obj):
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            return [obj]
        return []

    for item in _iter_items(data):
        ll = (item.get("LinkLayerAddress") or "").lower().replace("-", "").replace(":", "")
        ip = item.get("IPAddress")
        st = str(item.get("State", "")).lower()
        if ll == mac and ip and st not in ("unreachable",):
            return str(ip)

    try:
        out = _run_capture_hidden(["arp", "-a"], encoding="utf-8", errors="ignore")
        pat = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F:-]{17})\s+")
        for m in pat.finditer(out):
            ip = m.group(1)
            ll = m.group(2).lower().replace("-", "").replace(":", "")
            if ll == mac:
                return ip
    except Exception:
        pass

    return None


def build_broadcast_destinations(
    *,
    bind_ip: str,
    mask_bits: int,
    port: int,
) -> List[Tuple[str, int]]:
    dst_list: List[Tuple[str, int]] = [(LIMITED_BCAST, port)]

    if bind_ip and bind_ip != "0.0.0.0":
        try:
            dst_list.append((compute_directed_bcast(bind_ip, mask_bits), port))
        except Exception:
            pass

    for ip, pr in get_all_ipv4_prefixes_windows():
        try:
            dst = (compute_directed_bcast(ip, pr), port)
            if dst not in dst_list:
                dst_list.append(dst)
        except Exception:
            pass

    return list(dict.fromkeys(dst_list))


def _aes_ecb_encrypt(block16: bytes) -> bytes:
    try:
        from Crypto.Cipher import AES  # type: ignore
        cipher = AES.new(AES_KEY_16, AES.MODE_ECB)
        return cipher.encrypt(block16)
    except Exception:
        try:
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

            cipher = Cipher(
                algorithms.AES(AES_KEY_16),
                modes.ECB(),
                backend=default_backend(),
            )
            encryptor = cipher.encryptor()
            return encryptor.update(block16) + encryptor.finalize()
        except Exception as exc:
            raise AppError(
                kind="compat",
                message="AES backend unavailable",
                detail=str(exc),
            ) from exc


def _inc_counter_be_16(counter: bytearray) -> None:
    for i in range(15, -1, -1):
        counter[i] = (counter[i] + 1) & 0xFF
        if counter[i] != 0:
            break


def aes_ctr_xcrypt(data: bytes) -> bytes:
    counter = bytearray(CTR_NONCE_8 + b"\x00" * 8)
    out = bytearray(len(data))
    for off in range(0, len(data), 16):
        ks = _aes_ecb_encrypt(bytes(counter))
        blk = data[off:off + 16]
        for i, b in enumerate(blk):
            out[off + i] = b ^ ks[i]
        _inc_counter_be_16(counter)
    return bytes(out)


def msvcrt_rand_bytes(seed_time: int, n: int = 5) -> bytes:
    state = seed_time & 0xFFFFFFFF
    out = bytearray()
    for _ in range(n):
        state = (state * 214013 + 2531011) & 0xFFFFFFFF
        r = (state >> 16) & 0x7FFF
        out.append(r & 0xFF)
    return bytes(out)


def seed_postprocess(seed1_32: bytes, seed_time: int) -> bytes:
    b = bytearray(seed1_32)
    b[0x1A] = 0xFE
    b[0x1B:0x20] = msvcrt_rand_bytes(seed_time, 5)
    for i in range(32):
        b[i] ^= 0x5A
    return bytes(b)


def resetkey_from_seed1(seed1_32: bytes, seed_time: int) -> bytes:
    seed2 = seed_postprocess(seed1_32, seed_time)
    return aes_ctr_xcrypt(seed2)


def parse_mac(mac_hex: str) -> bytes:
    return bytes.fromhex(normalize_mac12(mac_hex))


def pick_devkey_candidates(pkt: bytes) -> List[Tuple[int, bytes]]:
    out: List[Tuple[int, bytes]] = []
    if len(pkt) >= 64:
        out.append((32, pkt[32:64]))
    if len(pkt) >= 32:
        out.append((len(pkt) - 32, pkt[-32:]))
    uniq: List[Tuple[int, bytes]] = []
    seen = set()
    for off, b in out:
        if len(b) == 32 and off not in seen:
            uniq.append((off, b))
            seen.add(off)
    return uniq


def brute_find_devkey_in_pkt(pkt: bytes, target_mac6: bytes, step: int = 1) -> Optional[Tuple[int, bytes, bytes]]:
    n = len(pkt)
    if n < 32:
        return None
    step = max(1, int(step))
    for off in range(0, n - 32 + 1, step):
        devkey = pkt[off:off + 32]
        seed1 = aes_ctr_xcrypt(devkey)
        if seed1[:6] == target_mac6:
            return off, devkey, seed1
    return None


def build_target_req64_v1(mac6: bytes) -> bytes:
    b = bytearray(REQ64_SCAN)
    b[24:28] = b"\x28\x00\x00\x00"
    b[28:34] = mac6
    return bytes(b)


def build_target_req64_v2(mac6: bytes) -> bytes:
    b = bytearray(REQ64_SCAN)
    b[24:30] = mac6
    return bytes(b)


def build_write_req64(mac6: bytes, reset_bin_32: bytes) -> bytes:
    b = bytearray(REQ64_WRITE)
    b[0x14:0x18] = b"\x28\x00\x00\x00"
    b[0x18:0x1E] = mac6
    b[0x1E:0x20] = b"\x00\x00"
    b[0x20:0x40] = reset_bin_32[:32]
    return bytes(b)


def _send_scan_pump(
    sock: socket.socket,
    *,
    destinations: List[Tuple[str, int]],
    reqs: List[bytes],
) -> None:
    for _ in range(SCAN_REPEAT):
        for dst in destinations:
            try:
                sock.sendto(REQ24, dst)
                for req in reqs:
                    sock.sendto(req, dst)
            except OSError:
                continue
        if SCAN_INTERVAL > 0:
            time.sleep(SCAN_INTERVAL)


def wait_for_ack_0415(
    s: socket.socket,
    device_ip: Optional[str],
    port: int,
    timeout_sec: float,
    *,
    stop_requested: Callable[[], bool] | None = None,
) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if stop_requested and stop_requested():
            return False
        try:
            pkt, (src_ip, src_port) = s.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            continue
        if src_port != port:
            continue
        if device_ip and src_ip != device_ip:
            continue
        if len(pkt) < 6 or pkt[:4] != RSP_SIG:
            continue
        if pkt[4] == 0x04 and pkt[5] == 0x15:
            return True
    return False


def send_write_seq(
    s: socket.socket,
    dst: Tuple[str, int],
    write_req: bytes,
    seq_count: int,
    gap_sec: float,
) -> None:
    for _ in range(seq_count):
        s.sendto(write_req, dst)
        s.sendto(REQ24, dst)
        time.sleep(gap_sec)


def scan_for_target(
    s: socket.socket,
    *,
    target_mac6: bytes,
    bind_ip: str,
    port: int,
    mask_bits: int,
    scan_seconds: float,
    scan_repeat: int,
    scan_interval: float,
    ignore_self: bool,
    bf96_step: int,
    stop_requested: Callable[[], bool] | None = None,
) -> Dict[str, object]:
    dst_list = build_broadcast_destinations(bind_ip=bind_ip, mask_bits=mask_bits, port=port)

    treq1 = build_target_req64_v1(target_mac6)
    treq2 = build_target_req64_v2(target_mac6)
    reqs = [treq1, treq2]

    local_ips = get_local_ipv4_set_windows() if ignore_self else set()

    ip_guess = find_ip_by_mac_windows(target_mac6)
    if ip_guess:
        uni_dst = (ip_guess, port)
        for _ in range(3):
            if stop_requested and stop_requested():
                break
            try:
                s.sendto(REQ24, uni_dst)
                s.sendto(treq1, uni_dst)
                s.sendto(treq2, uni_dst)
            except OSError:
                pass
            time.sleep(0.03)

    next_pump = 0.0
    deadline = time.time() + scan_seconds

    while time.time() < deadline:
        if stop_requested and stop_requested():
            break

        now = time.time()
        if now >= next_pump:
            for _ in range(max(1, scan_repeat)):
                for dst in dst_list:
                    try:
                        s.sendto(REQ24, dst)
                        s.sendto(treq1, dst)
                        s.sendto(treq2, dst)
                    except OSError:
                        continue
                time.sleep(scan_interval)
            next_pump = now + 0.35

        try:
            pkt, (src_ip, src_port) = s.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            continue

        if ignore_self and src_ip in local_ips:
            continue
        if src_port != port:
            continue
        if len(pkt) < 64 or not pkt.startswith(RSP_SIG):
            continue

        if len(pkt) >= 96:
            if pkt.find(target_mac6) != -1:
                uni_dst = (src_ip, port)
                for _ in range(2):
                    if stop_requested and stop_requested():
                        break
                    try:
                        s.sendto(REQ24, uni_dst)
                        s.sendto(treq1, uni_dst)
                        s.sendto(treq2, uni_dst)
                    except OSError:
                        pass
                    time.sleep(0.02)

            brute = brute_find_devkey_in_pkt(pkt, target_mac6, step=bf96_step)
            if brute:
                off, devkey, seed1 = brute
                return {"device_ip": src_ip, "off": off, "devkey": devkey, "seed1": seed1, "note": "brute>=96"}

        for off, devkey in pick_devkey_candidates(pkt):
            seed1 = aes_ctr_xcrypt(devkey)
            if seed1[:6] == target_mac6:
                return {"device_ip": src_ip, "off": off, "devkey": devkey, "seed1": seed1, "note": "fixed"}

        brute_any = brute_find_devkey_in_pkt(pkt, target_mac6, step=bf96_step)
        if brute_any:
            off, devkey, seed1 = brute_any
            return {"device_ip": src_ip, "off": off, "devkey": devkey, "seed1": seed1, "note": "brute_any"}

    raise RuntimeError("MISS: target MAC not found in scan window")


def scan_for_target_with_hint(
    sock: socket.socket,
    *,
    target_mac6: bytes,
    bind_ip: str,
    port: int,
    mask_bits: int,
    scan_seconds: float,
    ignore_self: bool,
    bf96_step: int,
    device_ip_hint: str | None,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, object]:
    destinations: list[tuple[str, int]] = []

    hint_ip = (device_ip_hint or "").strip()
    if hint_ip:
        destinations.append((hint_ip, port))

    for dst in build_broadcast_destinations(
        bind_ip=bind_ip,
        mask_bits=mask_bits,
        port=port,
    ):
        if dst not in destinations:
            destinations.append(dst)

    req1 = build_target_req64_v1(target_mac6)
    req2 = build_target_req64_v2(target_mac6)
    reqs = [req1, req2]

    local_ips = get_local_ipv4_set_windows() if ignore_self else set()
    deadline = time.time() + max(0.1, float(scan_seconds))
    next_pump = 0.0

    while time.time() < deadline:
        if stop_requested and stop_requested():
            break

        now = time.time()
        if now >= next_pump:
            _send_scan_pump(sock, destinations=destinations, reqs=reqs)
            next_pump = now + SCAN_INTERVAL

        try:
            pkt, (src_ip, src_port) = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            continue

        if ignore_self and src_ip in local_ips:
            continue
        if src_port != port:
            continue
        if len(pkt) < 64 or not pkt.startswith(RSP_SIG):
            continue

        if len(pkt) >= 96:
            mm = extract_mac_by_marker(pkt)
            if mm:
                _, marker_mac, _ = mm
                if marker_mac == target_mac6:
                    brute = brute_find_devkey_in_pkt(pkt, marker_mac, step=bf96_step)
                    if brute:
                        off, devkey, seed1 = brute
                        return {
                            "device_ip": src_ip,
                            "off": off,
                            "devkey": devkey,
                            "seed1": seed1,
                            "note": "hint-brute>=96",
                        }

        for off, devkey in pick_devkey_candidates(pkt):
            seed1 = aes_ctr_xcrypt(devkey)
            mac6 = seed1[:6]
            if mac6 == target_mac6:
                return {
                    "device_ip": src_ip,
                    "off": off,
                    "devkey": devkey,
                    "seed1": seed1,
                    "note": "hint-fixed",
                }

        brute = brute_find_devkey_in_pkt(pkt, target_mac6, step=bf96_step)
        if brute:
            off, devkey, seed1 = brute
            return {
                "device_ip": src_ip,
                "off": off,
                "devkey": devkey,
                "seed1": seed1,
                "note": "hint-brute_any",
            }

    raise RuntimeError("MISS: target MAC not found in hint scan window")


def scan_targets_batch(
    s: socket.socket,
    *,
    target_mac12_list: List[str],
    bind_ip: str,
    port: int,
    mask_bits: int,
    scan_seconds: float,
    scan_repeat: int,
    scan_interval: float,
    ignore_self: bool,
    bf96_step: int,
    stop_requested: Callable[[], bool] | None = None,
) -> Dict[str, Dict[str, object]]:
    target_mac6_map: Dict[str, bytes] = {
        normalize_mac12(m): parse_mac(m) for m in target_mac12_list
    }
    target_mac6_to_mac12 = {v: k for k, v in target_mac6_map.items()}

    dst_list = build_broadcast_destinations(bind_ip=bind_ip, mask_bits=mask_bits, port=port)

    reqs: List[bytes] = []
    for mac6 in target_mac6_map.values():
        reqs.append(build_target_req64_v1(mac6))
        reqs.append(build_target_req64_v2(mac6))

    local_ips = get_local_ipv4_set_windows() if ignore_self else set()
    hits: Dict[str, Dict[str, object]] = {}

    next_pump = 0.0
    deadline = time.time() + scan_seconds

    while time.time() < deadline and len(hits) < len(target_mac6_map):
        if stop_requested and stop_requested():
            break

        now = time.time()
        if now >= next_pump:
            for _ in range(max(1, scan_repeat)):
                for dst in dst_list:
                    try:
                        s.sendto(REQ24, dst)
                        for req in reqs:
                            s.sendto(req, dst)
                    except OSError:
                        continue
                time.sleep(scan_interval)
            next_pump = now + 0.35

        try:
            pkt, (src_ip, src_port) = s.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            continue

        if ignore_self and src_ip in local_ips:
            continue
        if src_port != port:
            continue
        if len(pkt) < 64 or not pkt.startswith(RSP_SIG):
            continue

        if len(pkt) >= 96:
            mm = extract_mac_by_marker(pkt)
            if mm:
                _, marker_mac, _ = mm
                mac12 = target_mac6_to_mac12.get(marker_mac)
                if mac12 and mac12 not in hits:
                    brute = brute_find_devkey_in_pkt(pkt, marker_mac, step=bf96_step)
                    if brute:
                        off, devkey, seed1 = brute
                        hits[mac12] = {
                            "device_ip": src_ip,
                            "off": off,
                            "devkey": devkey,
                            "seed1": seed1,
                            "note": "brute>=96",
                        }
                        continue

        for off, devkey in pick_devkey_candidates(pkt):
            seed1 = aes_ctr_xcrypt(devkey)
            mac6 = seed1[:6]
            mac12 = target_mac6_to_mac12.get(mac6)
            if mac12 and mac12 not in hits:
                hits[mac12] = {
                    "device_ip": src_ip,
                    "off": off,
                    "devkey": devkey,
                    "seed1": seed1,
                    "note": "fixed",
                }
                break
        else:
            for mac12, mac6 in target_mac6_map.items():
                if mac12 in hits:
                    continue
                brute = brute_find_devkey_in_pkt(pkt, mac6, step=bf96_step)
                if brute:
                    off, devkey, seed1 = brute
                    hits[mac12] = {
                        "device_ip": src_ip,
                        "off": off,
                        "devkey": devkey,
                        "seed1": seed1,
                        "note": "brute_any",
                    }
                    break

    return hits


class TruenResetService:
    def reset(
            self,
            request: ResetRequest,
            *,
            stop_requested: Callable[[], bool] | None = None,
    ) -> ResetResult:
        bind_ip = request.bind_ip
        if not bind_ip:
            try:
                bind_ip, auto_prefix = autodetect_bind_and_prefix()
                mask_bits = int(request.mask_bits or auto_prefix or 24)
            except Exception:
                bind_ip = get_local_ipv4()
                mask_bits = int(request.mask_bits or 24)
        else:
            mask_bits = int(request.mask_bits or 24)

        if not bind_ip or bind_ip == "0.0.0.0":
            return ResetResult(
                ok=False,
                mac12=normalize_mac12(request.mac12),
                error_kind="reset",
                error_message="bind ip unavailable",
                error_detail="local ipv4 not found",
            )

        # 현장 툴 기준으로 너무 짧은 값은 강제로 상향
        scan_seconds = max(float(request.scan_seconds), 12.0)
        seed_sweep = max(int(request.seed_sweep), 320)
        write_seq = max(int(request.write_seq), 4)
        write_gap = max(float(request.write_gap), 0.012)
        ack_wait_sec = max(float(request.ack_wait_sec), 1.8)
        ignore_self = bool(request.ignore_self)
        bf96_step = int(request.bf96_step)
        ack_any_ip = bool(request.ack_any_ip)

        sock = open_udp_socket("0.0.0.0", request.port, timeout=0.05)

        try:
            target_mac12 = normalize_mac12(request.mac12)
            target_mac6 = parse_mac(target_mac12)

            if request.device_ip_hint:
                hit = scan_for_target_with_hint(
                    sock,
                    target_mac6=target_mac6,
                    bind_ip=bind_ip,
                    port=request.port,
                    mask_bits=mask_bits,
                    scan_seconds=scan_seconds,
                    ignore_self=ignore_self,
                    bf96_step=bf96_step,
                    device_ip_hint=request.device_ip_hint,
                    stop_requested=stop_requested,
                )
            else:
                hit = scan_for_target(
                    sock,
                    target_mac6=target_mac6,
                    bind_ip=bind_ip,
                    port=request.port,
                    mask_bits=mask_bits,
                    scan_seconds=scan_seconds,
                    scan_repeat=2,
                    scan_interval=0.12,
                    ignore_self=ignore_self,
                    bf96_step=bf96_step,
                    stop_requested=stop_requested,
                )

            device_ip = str(hit["device_ip"])
            seed1 = hit["seed1"]

            write_destinations = build_broadcast_destinations(
                bind_ip=bind_ip,
                mask_bits=mask_bits,
                port=request.port,
            )
            if (device_ip, request.port) not in write_destinations:
                write_destinations.append((device_ip, request.port))

            seed_center = int(time.time())
            seed_offsets: list[int] = [0]
            for i in range(1, seed_sweep + 1):
                seed_offsets.append(-i)
                seed_offsets.append(i)

            for offset in seed_offsets:
                if stop_requested and stop_requested():
                    break

                seed_time = seed_center + offset
                reset_bin = resetkey_from_seed1(seed1, seed_time)
                write_req = build_write_req64(target_mac6, reset_bin)

                for _ in range(write_seq):
                    for dst in write_destinations:
                        try:
                            sock.sendto(write_req, dst)
                        except OSError:
                            pass
                    time.sleep(write_gap)

                ack_device_ip = None if ack_any_ip else device_ip
                if wait_for_ack_0415(
                        sock,
                        device_ip=ack_device_ip,
                        port=request.port,
                        timeout_sec=ack_wait_sec,
                        stop_requested=stop_requested,
                ):
                    return ResetResult(
                        ok=True,
                        mac12=target_mac12,
                        device_ip=device_ip,
                        scan_hit=True,
                        ack_seen=True,
                    )

            return ResetResult(
                ok=False,
                mac12=target_mac12,
                device_ip=device_ip,
                scan_hit=True,
                ack_seen=False,
                error_kind="reset",
                error_message="no ACK 04 15 in sweep window",
                error_detail="device scanned but reset ACK was not observed",
            )

        except Exception as exc:
            return ResetResult(
                ok=False,
                mac12=normalize_mac12(request.mac12),
                device_ip=request.device_ip_hint,
                scan_hit=False,
                ack_seen=False,
                error_kind="reset",
                error_message="udp reset failed",
                error_detail=str(exc),
            )
        finally:
            safe_close_socket(sock)

    def reset_batch(
            self,
            request: BatchResetRequest,
            *,
            stop_requested: Callable[[], bool] | None = None,
    ) -> BatchResetResult:
        bind_ip = request.bind_ip
        if not bind_ip:
            try:
                bind_ip, auto_prefix = autodetect_bind_and_prefix()
                mask_bits = int(request.mask_bits or auto_prefix or 24)
            except Exception:
                bind_ip = get_local_ipv4()
                mask_bits = int(request.mask_bits or 24)
        else:
            mask_bits = int(request.mask_bits or 24)

        if not bind_ip or bind_ip == "0.0.0.0":
            return BatchResetResult(ok=False, results={})

        # 현장 툴 기준으로 강제 상향
        scan_seconds = max(float(request.scan_seconds), 12.0)
        seed_sweep = max(int(request.seed_sweep), 320)
        write_seq = max(int(request.write_seq), 4)
        write_gap = max(float(request.write_gap), 0.012)
        ack_wait_sec = max(float(request.ack_wait_sec), 1.8)
        ignore_self = bool(request.ignore_self)
        bf96_step = int(request.bf96_step)
        ack_any_ip = bool(request.ack_any_ip)

        results: dict[str, ResetResult] = {
            normalize_mac12(item.mac12): ResetResult(
                ok=False,
                mac12=normalize_mac12(item.mac12),
                error_kind="reset",
                error_message="not processed",
            )
            for item in request.items
        }

        mac12_list = [normalize_mac12(item.mac12) for item in request.items]
        if not mac12_list:
            return BatchResetResult(ok=False, results={})

        item_by_mac12: dict[str, BatchResetItem] = {
            normalize_mac12(item.mac12): item for item in request.items
        }

        sock = open_udp_socket("0.0.0.0", request.port, timeout=0.05)

        try:
            hits = scan_targets_batch(
                sock,
                target_mac12_list=mac12_list,
                bind_ip=bind_ip,
                port=request.port,
                mask_bits=mask_bits,
                scan_seconds=scan_seconds,
                scan_repeat=1,
                scan_interval=0.05,
                ignore_self=ignore_self,
                bf96_step=bf96_step,
                stop_requested=stop_requested,
            )

            pending: dict[str, dict[str, object]] = {}
            ip_to_mac: dict[str, str] = {}

            for mac12 in mac12_list:
                hit = hits.get(mac12)
                if not hit:
                    results[mac12] = ResetResult(
                        ok=False,
                        mac12=mac12,
                        scan_hit=False,
                        ack_seen=False,
                        error_kind="reset",
                        error_message="scan miss",
                        error_detail="target MAC not found in scan window",
                    )
                    continue

                pending[mac12] = hit
                ip_to_mac[str(hit["device_ip"])] = mac12

            if pending:
                write_broadcasts = build_broadcast_destinations(
                    bind_ip=bind_ip,
                    mask_bits=mask_bits,
                    port=request.port,
                )

                seed_center = int(time.time())
                seed_offsets: list[int] = [0]
                for i in range(1, seed_sweep + 1):
                    seed_offsets.append(-i)
                    seed_offsets.append(i)

                for offset in seed_offsets:
                    if stop_requested and stop_requested():
                        break

                    alive = [mac12 for mac12 in pending.keys() if not results[mac12].ok]
                    if not alive:
                        break

                    seed_time = seed_center + offset

                    for _ in range(write_seq):
                        for mac12 in alive:
                            hit = pending[mac12]
                            mac6 = parse_mac(mac12)
                            seed1 = hit["seed1"]
                            device_ip = str(hit["device_ip"])
                            reset_bin = resetkey_from_seed1(seed1, seed_time)
                            write_req = build_write_req64(mac6, reset_bin)

                            for dst in write_broadcasts:
                                try:
                                    sock.sendto(write_req, dst)
                                except OSError:
                                    pass

                            try:
                                sock.sendto(write_req, (device_ip, request.port))
                            except OSError:
                                pass

                        time.sleep(write_gap)

                    end = time.time() + ack_wait_sec
                    while time.time() < end:
                        if stop_requested and stop_requested():
                            break

                        if all(results[mac12].ok for mac12 in pending.keys()):
                            break

                        try:
                            pkt, (src_ip, src_port) = sock.recvfrom(4096)
                        except socket.timeout:
                            continue
                        except OSError:
                            continue

                        if src_port != request.port:
                            continue
                        if len(pkt) < 6 or pkt[:4] != RSP_SIG:
                            continue
                        if not (pkt[4] == 0x04 and pkt[5] == 0x15):
                            continue

                        if ack_any_ip:
                            for mac12 in alive:
                                if not results[mac12].ok:
                                    results[mac12] = ResetResult(
                                        ok=True,
                                        mac12=mac12,
                                        device_ip=src_ip,
                                        scan_hit=True,
                                        ack_seen=True,
                                    )
                                    break
                        else:
                            mac12 = ip_to_mac.get(src_ip)
                            if mac12 and not results[mac12].ok:
                                results[mac12] = ResetResult(
                                    ok=True,
                                    mac12=mac12,
                                    device_ip=src_ip,
                                    scan_hit=True,
                                    ack_seen=True,
                                )

            # batch 실패 장비는 single fallback
            for mac12 in mac12_list:
                if results[mac12].ok:
                    continue

                hit = hits.get(mac12)
                item = item_by_mac12.get(mac12)

                single_req = ResetRequest(
                    mac12=mac12,
                    bind_ip=bind_ip,
                    mask_bits=mask_bits,
                    port=request.port,
                    device_ip_hint=(item.device_ip_hint if item else None) or (str(hit["device_ip"]) if hit else None),
                    scan_seconds=scan_seconds,
                    seed_sweep=seed_sweep,
                    write_seq=write_seq,
                    write_gap=write_gap,
                    ack_wait_sec=ack_wait_sec,
                    ignore_self=ignore_self,
                    bf96_step=bf96_step,
                    ack_any_ip=ack_any_ip,
                )
                results[mac12] = self.reset(single_req, stop_requested=stop_requested)

            return BatchResetResult(
                ok=all(item.ok for item in results.values()) if results else False,
                results=results,
            )
        finally:
            safe_close_socket(sock)