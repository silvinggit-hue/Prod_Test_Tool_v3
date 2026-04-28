from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass
from typing import Callable

from domain.errors.app_error import AppError
from infra.discovery.network import build_broadcast_destinations, get_local_ipv4, open_udp_socket, safe_close_socket
from infra.discovery.packet_parser import RSP_SIG, extract_mac_by_marker, is_probable_unicast_mac, normalize_mac12


PORT = 64988
LIMITED_BCAST = "255.255.255.255"

AES_KEY_16 = b"truen is the wor"
CTR_NONCE_8 = b"fprintf("

REQ24 = bytes.fromhex("34 52 34 87 01 05") + b"\x00" * (24 - 6)
REQ64_SCAN = bytes.fromhex("34 52 34 87 03 05") + b"\x00" * (64 - 6)
REQ64_WRITE = bytes.fromhex("34 52 34 87 04 05") + b"\x00" * (64 - 6)

MAC_MARKERS = [b"\x48\x00\x00\x00\x00"]


@dataclass(frozen=True)
class ResetRequest:
    mac12: str
    bind_ip: str | None = None
    mask_bits: int = 24
    port: int = PORT
    device_ip_hint: str | None = None
    scan_seconds: float = 2.0
    seed_sweep: int = 120
    write_seq: int = 3
    write_gap: float = 0.01
    ack_wait_sec: float = 1.0
    ignore_self: bool = True
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
    scan_seconds: float = 2.0
    seed_sweep: int = 120
    write_seq: int = 3
    write_gap: float = 0.01
    ack_wait_sec: float = 1.0
    ignore_self: bool = True
    bf96_step: int = 1
    ack_any_ip: bool = False


@dataclass(frozen=True)
class BatchResetResult:
    ok: bool
    results: dict[str, ResetResult]


def parse_mac(mac12: str) -> bytes:
    return bytes.fromhex(normalize_mac12(mac12))


def _aes_ecb_encrypt(block16: bytes) -> bytes:
    try:
        from Crypto.Cipher import AES  # type: ignore

        cipher = AES.new(AES_KEY_16, AES.MODE_ECB)
        return cipher.encrypt(block16)
    except Exception:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend

            cipher = Cipher(algorithms.AES(AES_KEY_16), modes.ECB(), backend=default_backend())
            encryptor = cipher.encryptor()
            return encryptor.update(block16) + encryptor.finalize()
        except Exception as exc:
            raise AppError(kind="compat", message="AES backend unavailable", detail=str(exc)) from exc


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
        blk = data[off : off + 16]
        for i, value in enumerate(blk):
            out[off + i] = value ^ ks[i]
        _inc_counter_be_16(counter)
    return bytes(out)


def pick_devkey_candidates(pkt: bytes) -> list[tuple[int, bytes]]:
    out: list[tuple[int, bytes]] = []
    if len(pkt) >= 64:
        out.append((32, pkt[32:64]))
    if len(pkt) >= 32:
        out.append((len(pkt) - 32, pkt[-32:]))

    uniq: list[tuple[int, bytes]] = []
    seen: set[int] = set()
    for off, data in out:
        if len(data) == 32 and off not in seen:
            uniq.append((off, data))
            seen.add(off)
    return uniq


def brute_find_devkey_in_pkt(pkt: bytes, target_mac6: bytes, step: int = 1) -> tuple[int, bytes, bytes] | None:
    n = len(pkt)
    if n < 32:
        return None

    step = max(1, int(step))
    for off in range(0, n - 32 + 1, step):
        devkey = pkt[off : off + 32]
        seed1 = aes_ctr_xcrypt(devkey)
        if seed1[:6] == target_mac6:
            return off, devkey, seed1
    return None


def build_target_req64_v1(mac6: bytes) -> bytes:
    packet = bytearray(REQ64_SCAN)
    packet[24:28] = b"\x28\x00\x00\x00"
    packet[28:34] = mac6
    return bytes(packet)


def build_target_req64_v2(mac6: bytes) -> bytes:
    packet = bytearray(REQ64_SCAN)
    packet[24:30] = mac6
    return bytes(packet)


def msvcrt_rand_bytes(seed_time: int, n: int = 5) -> bytes:
    state = seed_time & 0xFFFFFFFF
    out = bytearray()
    for _ in range(n):
        state = (state * 214013 + 2531011) & 0xFFFFFFFF
        r = (state >> 16) & 0x7FFF
        out.append(r & 0xFF)
    return bytes(out)


def seed_postprocess(seed1_32: bytes, seed_time: int) -> bytes:
    buffer = bytearray(seed1_32)
    buffer[0x1A] = 0xFE
    buffer[0x1B:0x20] = msvcrt_rand_bytes(seed_time, 5)
    for idx in range(32):
        buffer[idx] ^= 0x5A
    return bytes(buffer)


def resetkey_from_seed1(seed1_32: bytes, seed_time: int) -> bytes:
    seed2 = seed_postprocess(seed1_32, seed_time)
    return aes_ctr_xcrypt(seed2)


def build_write_req64(mac6: bytes, reset_bin_32: bytes) -> bytes:
    packet = bytearray(REQ64_WRITE)
    packet[0x14:0x18] = b"\x28\x00\x00\x00"
    packet[0x18:0x1E] = mac6
    packet[0x1E:0x20] = b"\x00\x00"
    packet[0x20:0x40] = reset_bin_32[:32]
    return bytes(packet)


def wait_for_ack_0415(
    sock: socket.socket,
    *,
    device_ip: str | None,
    port: int,
    timeout_sec: float,
    stop_requested: Callable[[], bool] | None = None,
) -> bool:
    deadline = time.time() + max(0.1, float(timeout_sec))
    while time.time() < deadline:
        if stop_requested and stop_requested():
            return False
        try:
            pkt, (src_ip, src_port) = sock.recvfrom(4096)
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


def scan_for_target(
    sock: socket.socket,
    *,
    target_mac6: bytes,
    bind_ip: str,
    port: int,
    mask_bits: int,
    scan_seconds: float,
    ignore_self: bool,
    bf96_step: int,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, object]:
    destinations = build_broadcast_destinations(bind_ip=bind_ip, mask_bits=mask_bits, port=port)

    req1 = build_target_req64_v1(target_mac6)
    req2 = build_target_req64_v2(target_mac6)
    deadline = time.time() + max(0.1, float(scan_seconds))

    while time.time() < deadline:
        if stop_requested and stop_requested():
            break

        for dst in destinations:
            try:
                sock.sendto(REQ24, dst)
                sock.sendto(req1, dst)
                sock.sendto(req2, dst)
            except OSError:
                continue

        try:
            pkt, (src_ip, src_port) = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            continue

        if ignore_self and src_ip == bind_ip:
            continue
        if src_port != port:
            continue
        if len(pkt) < 64 or not pkt.startswith(RSP_SIG):
            continue

        marker_mac = None
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
                            "note": "brute>=96",
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
                    "note": "fixed",
                }

        brute = brute_find_devkey_in_pkt(pkt, target_mac6, step=bf96_step)
        if brute:
            off, devkey, seed1 = brute
            return {
                "device_ip": src_ip,
                "off": off,
                "devkey": devkey,
                "seed1": seed1,
                "note": "brute_any",
            }

    raise RuntimeError("MISS: target MAC not found in hint scan window")


def scan_targets_batch(
    sock: socket.socket,
    *,
    target_mac12_list: list[str],
    bind_ip: str,
    port: int,
    mask_bits: int,
    scan_seconds: float,
    ignore_self: bool,
    bf96_step: int,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, dict[str, object]]:
    target_mac6_map: dict[str, bytes] = {
        normalize_mac12(mac12): parse_mac(mac12) for mac12 in target_mac12_list
    }
    target_mac6_to_mac12 = {mac6: mac12 for mac12, mac6 in target_mac6_map.items()}

    destinations = build_broadcast_destinations(bind_ip=bind_ip, mask_bits=mask_bits, port=port)
    reqs: list[bytes] = []
    for mac6 in target_mac6_map.values():
        reqs.append(build_target_req64_v1(mac6))
        reqs.append(build_target_req64_v2(mac6))

    hits: dict[str, dict[str, object]] = {}
    deadline = time.time() + max(0.1, float(scan_seconds))

    while time.time() < deadline and len(hits) < len(target_mac6_map):
        if stop_requested and stop_requested():
            break

        for dst in destinations:
            try:
                sock.sendto(REQ24, dst)
                for req in reqs:
                    sock.sendto(req, dst)
            except OSError:
                continue

        try:
            pkt, (src_ip, src_port) = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            continue

        if ignore_self and src_ip == bind_ip:
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
        bind_ip = request.bind_ip or get_local_ipv4()
        if not bind_ip:
            return ResetResult(
                ok=False,
                mac12=normalize_mac12(request.mac12),
                error_kind="reset",
                error_message="bind ip unavailable",
                error_detail="local ipv4 not found",
            )

        sock = open_udp_socket("0.0.0.0", request.port, timeout=0.05)

        try:
            target_mac12 = normalize_mac12(request.mac12)
            target_mac6 = parse_mac(target_mac12)

            if request.device_ip_hint:
                hit = scan_for_target(
                    sock,
                    target_mac6=target_mac6,
                    bind_ip=bind_ip,
                    port=request.port,
                    mask_bits=request.mask_bits,
                    scan_seconds=request.scan_seconds,
                    ignore_self=request.ignore_self,
                    bf96_step=request.bf96_step,
                    stop_requested=stop_requested,
                )
            else:
                hit = scan_for_target(
                    sock,
                    target_mac6=target_mac6,
                    bind_ip=bind_ip,
                    port=request.port,
                    mask_bits=request.mask_bits,
                    scan_seconds=request.scan_seconds,
                    ignore_self=request.ignore_self,
                    bf96_step=request.bf96_step,
                    stop_requested=stop_requested,
                )

            device_ip = str(hit["device_ip"])
            seed1 = hit["seed1"]

            seed_center = int(time.time())
            seed_offsets: list[int] = [0]
            for i in range(1, max(1, int(request.seed_sweep)) + 1):
                seed_offsets.append(-i)
                seed_offsets.append(i)

            for offset in seed_offsets:
                if stop_requested and stop_requested():
                    break

                seed_time = seed_center + offset
                write_req = build_write_req64(target_mac6, resetkey_from_seed1(seed1, seed_time))

                for _ in range(max(1, int(request.write_seq))):
                    try:
                        sock.sendto(write_req, (LIMITED_BCAST, request.port))
                        sock.sendto(write_req, (device_ip, request.port))
                        for dst in build_broadcast_destinations(
                            bind_ip=bind_ip,
                            mask_bits=request.mask_bits,
                            port=request.port,
                        ):
                            sock.sendto(write_req, dst)
                    except OSError:
                        pass
                    time.sleep(max(0.001, float(request.write_gap)))

                ack_device_ip = None if request.ack_any_ip else device_ip
                if wait_for_ack_0415(
                    sock,
                    device_ip=ack_device_ip,
                    port=request.port,
                    timeout_sec=request.ack_wait_sec,
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
        bind_ip = request.bind_ip or get_local_ipv4()
        if not bind_ip:
            return BatchResetResult(ok=False, results={})

        results: dict[str, ResetResult] = {
            normalize_mac12(item.mac12): ResetResult(
                ok=False,
                mac12=normalize_mac12(item.mac12),
                error_kind="reset",
                error_message="not processed",
            )
            for item in request.items
        }

        no_hint_items: list[BatchResetItem] = []
        for item in request.items:
            mac12 = normalize_mac12(item.mac12)
            if item.device_ip_hint:
                results[mac12] = self.reset(
                    ResetRequest(
                        mac12=mac12,
                        bind_ip=bind_ip,
                        mask_bits=request.mask_bits,
                        port=request.port,
                        device_ip_hint=item.device_ip_hint,
                        scan_seconds=request.scan_seconds,
                        seed_sweep=request.seed_sweep,
                        write_seq=request.write_seq,
                        write_gap=request.write_gap,
                        ack_wait_sec=request.ack_wait_sec,
                        ignore_self=request.ignore_self,
                        bf96_step=request.bf96_step,
                        ack_any_ip=request.ack_any_ip,
                    ),
                    stop_requested=stop_requested,
                )
            else:
                no_hint_items.append(item)

        if not no_hint_items:
            return BatchResetResult(
                ok=all(item.ok for item in results.values()) if results else False,
                results=results,
            )

        mac12_list = [normalize_mac12(item.mac12) for item in no_hint_items]
        sock = open_udp_socket("0.0.0.0", request.port, timeout=0.05)

        try:
            hits = scan_targets_batch(
                sock,
                target_mac12_list=mac12_list,
                bind_ip=bind_ip,
                port=request.port,
                mask_bits=request.mask_bits,
                scan_seconds=request.scan_seconds,
                ignore_self=request.ignore_self,
                bf96_step=request.bf96_step,
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

            if not pending:
                return BatchResetResult(
                    ok=all(item.ok for item in results.values()) if results else False,
                    results=results,
                )

            seed_center = int(time.time())
            seed_offsets: list[int] = [0]
            for i in range(1, max(1, int(request.seed_sweep)) + 1):
                seed_offsets.append(-i)
                seed_offsets.append(i)

            for offset in seed_offsets:
                if stop_requested and stop_requested():
                    break

                alive = [mac12 for mac12 in pending.keys() if not results[mac12].ok]
                if not alive:
                    break

                seed_time = seed_center + offset

                for _ in range(max(1, int(request.write_seq))):
                    for mac12 in alive:
                        hit = pending[mac12]
                        mac6 = parse_mac(mac12)
                        seed1 = hit["seed1"]
                        device_ip = str(hit["device_ip"])
                        write_req = build_write_req64(mac6, resetkey_from_seed1(seed1, seed_time))

                        try:
                            sock.sendto(write_req, (LIMITED_BCAST, request.port))
                            sock.sendto(write_req, (device_ip, request.port))
                        except OSError:
                            pass

                    time.sleep(max(0.001, float(request.write_gap)))

                end = time.time() + max(0.1, float(request.ack_wait_sec))
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

                    mac12 = ip_to_mac.get(src_ip)
                    if mac12 and not results[mac12].ok:
                        results[mac12] = ResetResult(
                            ok=True,
                            mac12=mac12,
                            device_ip=src_ip,
                            scan_hit=True,
                            ack_seen=True,
                        )

            for mac12, hit in pending.items():
                if results[mac12].ok:
                    continue
                results[mac12] = ResetResult(
                    ok=False,
                    mac12=mac12,
                    device_ip=str(hit["device_ip"]),
                    scan_hit=True,
                    ack_seen=False,
                    error_kind="reset",
                    error_message="no ACK 04 15 in sweep window",
                    error_detail="device scanned but reset ACK was not observed",
                )

            return BatchResetResult(
                ok=all(item.ok for item in results.values()) if results else False,
                results=results,
            )
        finally:
            safe_close_socket(sock)