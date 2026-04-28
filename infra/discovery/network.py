from __future__ import annotations

import socket


def get_local_ipv4() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
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
    for p in parts:
        ip_int = (ip_int << 8) | int(p)

    mask = (0xFFFFFFFF << (32 - mask_bits)) & 0xFFFFFFFF
    bcast = (ip_int & mask) | (~mask & 0xFFFFFFFF)

    return ".".join(str((bcast >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def open_udp_socket(bind_ip: str, port: int, timeout: float = 0.05) -> socket.socket:
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