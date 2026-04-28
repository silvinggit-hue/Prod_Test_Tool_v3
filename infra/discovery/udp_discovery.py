from __future__ import annotations

import time
from dataclasses import dataclass

from infra.discovery.network import (
    compute_directed_broadcast,
    get_local_ipv4,
    open_udp_socket,
    safe_close_socket,
)
from infra.discovery.packet_parser import REQ24, ParsedDiscoveryPacket, parse_discovery_packet


DEFAULT_PORT = 64988
LIMITED_BCAST = "255.255.255.255"


@dataclass(frozen=True)
class UdpDiscoveryDevice:
    ip: str
    mac: str
    mac12: str
    model: str
    firmware: str
    lens: str
    note: str


def _build_destinations(bind_ip: str | None, mask_bits: int, port: int) -> list[tuple[str, int]]:
    dsts: list[tuple[str, int]] = [(LIMITED_BCAST, port)]

    if bind_ip:
        try:
            dsts.append((compute_directed_broadcast(bind_ip, mask_bits), port))
        except Exception:
            pass

    uniq: list[tuple[str, int]] = []
    seen = set()
    for d in dsts:
        if d not in seen:
            uniq.append(d)
            seen.add(d)
    return uniq


def run_udp_discovery(
    *,
    bind_ip: str | None = None,
    mask_bits: int = 24,
    port: int = DEFAULT_PORT,
    seconds: float = 4.0,
    repeat: int = 4,
    interval: float = 0.12,
    ignore_self: bool = True,
) -> tuple[str | None, list[UdpDiscoveryDevice]]:
    bind_ip = bind_ip or get_local_ipv4()
    sock = open_udp_socket("0.0.0.0", port, timeout=0.05)

    found: dict[str, UdpDiscoveryDevice] = {}
    dsts = _build_destinations(bind_ip, mask_bits, port)

    try:
        deadline = time.time() + max(0.5, float(seconds))

        while time.time() < deadline:
            for _ in range(max(1, int(repeat))):
                for dst in dsts:
                    sock.sendto(REQ24, dst)
                time.sleep(max(0.01, float(interval)))

            rx_end = time.time() + max(0.2, float(interval) * 3.0)
            while time.time() < rx_end:
                try:
                    pkt, (src_ip, src_port) = sock.recvfrom(4096)
                except TimeoutError:
                    continue
                except OSError:
                    continue

                if src_port != port:
                    continue
                if ignore_self and bind_ip and src_ip == bind_ip:
                    continue

                parsed = parse_discovery_packet(pkt, src_ip)
                if parsed is None:
                    continue

                found[parsed.mac12] = UdpDiscoveryDevice(
                    ip=parsed.ip,
                    mac=parsed.mac,
                    mac12=parsed.mac12,
                    model=parsed.model or "-",
                    firmware=parsed.firmware or "-",
                    lens=parsed.lens or "-",
                    note=parsed.note or "-",
                )

            time.sleep(0.02)

        return bind_ip, list(found.values())

    finally:
        safe_close_socket(sock)