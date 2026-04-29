from __future__ import annotations

import socket
import time
from ipaddress import IPv4Address
from typing import Callable

from domain.errors.app_error import AppError
from infra.discovery.network import build_broadcast_destinations, open_udp_socket, safe_close_socket, send_udp_many
from infra.discovery.packet_parser import REQ24, RSP_SIG, normalize_mac12


PORT = 64988
LIMITED_BCAST = "255.255.255.255"

TEMPLATE_508_HEX = (
    "34523487020500000000000000000000000000004800000000"
    "1c63d41380"
    "000000000000"
    "640aa8c0"
    "010aa8c0"
    "00ffffff"
    "ae0800005000"
    "00000000000000000000"
    "61646d696e00"
    "c3d33f9f8b3f01000300"
    "313233340000"
    "aa8d3f3f3f0100030000"
)

MAC_OLD = bytes.fromhex("00 1c 63 d4 13 80")
IPGWMSK_OLD = bytes.fromhex(
    "64 0a a8 c0"
    "01 0a a8 c0"
    "00 ff ff ff"
)


def mac12_to_bytes(mac12: str) -> bytes:
    return bytes.fromhex(normalize_mac12(mac12))


def ip_le(ip: str) -> bytes:
    return int(IPv4Address(ip)).to_bytes(4, byteorder="little", signed=False)


def le_to_ip(b4: bytes) -> str:
    return str(IPv4Address(int.from_bytes(b4, byteorder="little", signed=False)))


def parse_template_hex(hexstr: str) -> bytes:
    hs = "".join((hexstr or "").split()).lower()
    if hs.startswith("0x"):
        hs = hs[2:]
    payload = bytes.fromhex(hs)
    if len(payload) != 96:
        raise AppError(kind="param", message=f"template must be 96 bytes, got {len(payload)}")
    return payload


def default_template96() -> bytes:
    return parse_template_hex(TEMPLATE_508_HEX)


def extract_ipgwmsk_from_template(template96: bytes) -> tuple[str, str, str]:
    idx = bytes(template96).find(IPGWMSK_OLD)
    if idx < 0:
        raise AppError(kind="compat", message="IP/GW/MASK block not found in template")
    ip = le_to_ip(template96[idx : idx + 4])
    gw = le_to_ip(template96[idx + 4 : idx + 8])
    mask = le_to_ip(template96[idx + 8 : idx + 12])
    return ip, gw, mask


def build_payload_from_template(
    template96: bytes,
    *,
    target_mac12: str,
    new_ip: str | None,
    gw: str | None,
    netmask: str | None,
) -> bytes:
    payload = bytearray(template96)

    idx_mac = bytes(payload).find(MAC_OLD)
    if idx_mac < 0:
        raise AppError(kind="compat", message="MAC block not found in template")

    idx_ip = bytes(payload).find(IPGWMSK_OLD)
    if idx_ip < 0:
        raise AppError(kind="compat", message="IP/GW/MASK block not found in template")

    old_ip, old_gw, old_mask = extract_ipgwmsk_from_template(template96)
    payload[idx_mac : idx_mac + 6] = mac12_to_bytes(target_mac12)
    payload[idx_ip : idx_ip + 4] = ip_le((new_ip or "").strip() or old_ip)
    payload[idx_ip + 4 : idx_ip + 8] = ip_le((gw or "").strip() or old_gw)
    payload[idx_ip + 8 : idx_ip + 12] = ip_le((netmask or "").strip() or old_mask)

    return bytes(payload)


def is_ack_packet(pkt: bytes) -> bool:
    return len(pkt) >= 6 and pkt[:4] == RSP_SIG and pkt[5] == 0x15


def is_announce_0115(pkt: bytes) -> bool:
    return len(pkt) >= 6 and pkt[:4] == RSP_SIG and pkt[4] == 0x01 and pkt[5] == 0x15


def wait_ack(
    sock: socket.socket,
    *,
    port: int,
    timeout_sec: float,
    stop_requested: Callable[[], bool] | None = None,
) -> bool:
    deadline = time.time() + max(0.1, float(timeout_sec))
    while time.time() < deadline:
        if stop_requested and stop_requested():
            return False
        try:
            pkt, (_src_ip, src_port) = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            continue

        if src_port != port:
            continue
        if is_ack_packet(pkt):
            return True
    return False


def wait_announce_from_ip(
    sock: socket.socket,
    *,
    port: int,
    ip: str,
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
        if src_ip != ip:
            continue
        if is_announce_0115(pkt) or pkt[:4] == RSP_SIG:
            return True
    return False


def run_setip(
    *,
    bind_ip: str | None,
    mask_bits: int,
    port: int,
    target_mac12: str,
    new_ip: str,
    gw: str | None,
    netmask: str | None,
    retries: int,
    ack_wait_sec: float,
    confirm_announce_sec: float,
    template96: bytes,
    stop_requested: Callable[[], bool] | None = None,
) -> tuple[bool, bool, bool, str | None]:
    if not new_ip:
        raise AppError(kind="param", message="new_ip is empty")

    payload = build_payload_from_template(
        template96,
        target_mac12=target_mac12,
        new_ip=new_ip,
        gw=gw,
        netmask=netmask,
    )

    destinations = build_broadcast_destinations(
        bind_ip=bind_ip,
        mask_bits=mask_bits,
        port=port,
    )
    sock = open_udp_socket("0.0.0.0", port, timeout=0.05)

    ack_seen = False
    announce_seen = False
    announced_ip: str | None = None

    try:
        for _attempt in range(1, max(1, int(retries)) + 1):
            if stop_requested and stop_requested():
                break

            send_udp_many(
                sock,
                payload=REQ24,
                destinations=destinations,
                repeat=1,
                gap_sec=0.01,
                stop_requested=stop_requested,
            )

            for dst in destinations:
                if stop_requested and stop_requested():
                    break
                try:
                    sock.sendto(payload, dst)
                except OSError:
                    continue

            if wait_ack(sock, port=port, timeout_sec=ack_wait_sec, stop_requested=stop_requested):
                ack_seen = True

                if confirm_announce_sec > 0:
                    if wait_announce_from_ip(
                        sock,
                        port=port,
                        ip=new_ip,
                        timeout_sec=confirm_announce_sec,
                        stop_requested=stop_requested,
                    ):
                        announce_seen = True
                        announced_ip = new_ip
                        return True, ack_seen, announce_seen, announced_ip

                    return True, ack_seen, announce_seen, announced_ip

                return True, ack_seen, announce_seen, announced_ip

            time.sleep(0.12)

        return False, ack_seen, announce_seen, announced_ip
    finally:
        safe_close_socket(sock)


def run_setip_batch(
    *,
    bind_ip: str | None,
    mask_bits: int,
    port: int,
    targets: list[dict[str, str | None]],
    retries: int,
    ack_wait_sec: float,
    confirm_announce_sec: float,
    template96: bytes,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, bool]:
    destinations = build_broadcast_destinations(
        bind_ip=bind_ip,
        mask_bits=mask_bits,
        port=port,
    )

    pending: dict[str, dict[str, object]] = {}
    ip_to_mac: dict[str, str] = {}

    for item in targets:
        mac12 = normalize_mac12(str(item["mac12"]))
        new_ip = str(item["new_ip"] or "").strip()
        payload = build_payload_from_template(
            template96,
            target_mac12=mac12,
            new_ip=new_ip,
            gw=item.get("gw"),
            netmask=item.get("netmask"),
        )
        pending[mac12] = {
            "payload": payload,
            "new_ip": new_ip,
            "ok": False,
        }
        if new_ip:
            ip_to_mac[new_ip] = mac12

    if not pending:
        return {}

    rx_window_sec = max(float(ack_wait_sec), float(confirm_announce_sec))
    sock = open_udp_socket("0.0.0.0", port, timeout=0.05)

    try:
        for _attempt in range(1, max(1, int(retries)) + 1):
            if stop_requested and stop_requested():
                break

            remain = [mac12 for mac12, info in pending.items() if not bool(info["ok"])]
            if not remain:
                break

            send_udp_many(
                sock,
                payload=REQ24,
                destinations=destinations,
                repeat=1,
                gap_sec=0.01,
                stop_requested=stop_requested,
            )

            for mac12 in remain:
                payload = pending[mac12]["payload"]
                for dst in destinations:
                    if stop_requested and stop_requested():
                        break
                    try:
                        sock.sendto(payload, dst)
                    except OSError:
                        continue

            end = time.time() + rx_window_sec
            while time.time() < end:
                if stop_requested and stop_requested():
                    break

                if all(bool(info["ok"]) for info in pending.values()):
                    break

                try:
                    pkt, (src_ip, src_port) = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError:
                    continue

                if src_port != port or len(pkt) < 6 or pkt[:4] != RSP_SIG:
                    continue

                if is_announce_0115(pkt) or is_ack_packet(pkt):
                    mac12 = ip_to_mac.get(src_ip)
                    if mac12 and mac12 in pending and not bool(pending[mac12]["ok"]):
                        pending[mac12]["ok"] = True

        return {mac12: bool(info["ok"]) for mac12, info in pending.items()}
    finally:
        safe_close_socket(sock)