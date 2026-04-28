from __future__ import annotations

import socket
import time
from typing import Callable


LIMITED_BCAST = "255.255.255.255"


def get_local_ipv4() -> str | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass

    return None


def compute_directed_broadcast(ip: str, mask_bits: int) -> str:
    parts = ip.split(".")
    if len(parts) != 4:
        raise ValueError("bind ip must be IPv4 like 192.168.10.2")

    ip_int = 0
    for part in parts:
        ip_int = (ip_int << 8) | int(part)

    mask = (0xFFFFFFFF << (32 - mask_bits)) & 0xFFFFFFFF
    bcast = (ip_int & mask) | (~mask & 0xFFFFFFFF)
    return ".".join(str((bcast >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def build_broadcast_destinations(
    *,
    bind_ip: str | None,
    mask_bits: int,
    port: int,
) -> list[tuple[str, int]]:
    destinations: list[tuple[str, int]] = [(LIMITED_BCAST, port)]

    if bind_ip:
        try:
            destinations.append((compute_directed_broadcast(bind_ip, mask_bits), port))
        except Exception:
            pass

    unique: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for dst in destinations:
        if dst not in seen:
            unique.append(dst)
            seen.add(dst)
    return unique


def open_udp_socket(
    bind_ip: str,
    port: int,
    *,
    timeout: float = 0.05,
) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((bind_ip, port))
    sock.settimeout(timeout)
    return sock


def safe_close_socket(sock: socket.socket | None) -> None:
    if sock is None:
        return
    try:
        sock.close()
    except Exception:
        pass


def send_udp_many(
    sock: socket.socket,
    *,
    payload: bytes,
    destinations: list[tuple[str, int]],
    repeat: int = 1,
    gap_sec: float = 0.01,
    stop_requested: Callable[[], bool] | None = None,
) -> None:
    total = max(1, int(repeat))
    gap = max(0.0, float(gap_sec))

    for _ in range(total):
        if stop_requested and stop_requested():
            return

        for dst in destinations:
            if stop_requested and stop_requested():
                return
            try:
                sock.sendto(payload, dst)
            except OSError:
                continue

        if gap > 0:
            time.sleep(gap)