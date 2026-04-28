from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass
from typing import Callable

from infra.discovery.network import (
    build_broadcast_destinations,
    get_local_ipv4,
    open_udp_socket,
    safe_close_socket,
    send_udp_many,
)
from infra.discovery.packet_parser import ParsedDiscoveryPacket, REQ24, parse_discovery_packet


DEFAULT_PORT = 64988


@dataclass(frozen=True)
class UdpDiscoveryDevice:
    ip: str
    mac: str
    mac12: str
    model: str
    firmware: str
    lens: str
    note: str


def _sort_devices(devices: list[UdpDiscoveryDevice]) -> list[UdpDiscoveryDevice]:
    def sort_key(item: UdpDiscoveryDevice):
        try:
            return (
                0,
                int(ipaddress.ip_address(item.ip)),
                (item.mac12 or "").strip().upper(),
            )
        except Exception:
            return (1, item.ip, (item.mac12 or "").strip().upper())

    return sorted(devices, key=sort_key)


def run_udp_discovery(
    *,
    bind_ip: str | None = None,
    mask_bits: int = 24,
    port: int = DEFAULT_PORT,
    seconds: float = 4.0,
    repeat: int = 4,
    interval: float = 0.12,
    ignore_self: bool = True,
    min_wait: float = 0.25,
    quiet_exit: float = 0.18,
    stop_requested: Callable[[], bool] | None = None,
) -> tuple[str | None, list[UdpDiscoveryDevice]]:
    bind_ip = bind_ip or get_local_ipv4()
    destinations = build_broadcast_destinations(bind_ip=bind_ip, mask_bits=mask_bits, port=port)
    sock = open_udp_socket("0.0.0.0", port, timeout=0.05)

    # 핵심:
    # discovery 단계에서는 IP가 같아도 MAC이 다르면 다른 장비다.
    # 따라서 dedupe는 MAC 기준만 한다.
    found_by_mac: dict[str, UdpDiscoveryDevice] = {}

    started_at = time.time()
    deadline = started_at + max(0.5, float(seconds))
    last_packet_at: float | None = None

    try:
        while time.time() < deadline:
            if stop_requested and stop_requested():
                break

            send_udp_many(
                sock,
                payload=REQ24,
                destinations=destinations,
                repeat=max(1, int(repeat)),
                gap_sec=max(0.01, float(interval)),
                stop_requested=stop_requested,
            )

            if stop_requested and stop_requested():
                break

            rx_end = time.time() + max(0.20, float(interval) * 3.0)
            while time.time() < rx_end:
                if stop_requested and stop_requested():
                    break

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

                parsed: ParsedDiscoveryPacket | None = parse_discovery_packet(pkt, src_ip)
                if parsed is None:
                    continue

                last_packet_at = time.time()

                device = UdpDiscoveryDevice(
                    ip=parsed.ip,
                    mac=parsed.mac,
                    mac12=parsed.mac12,
                    model=parsed.model or "-",
                    firmware=parsed.firmware or "-",
                    lens=parsed.lens or "-",
                    note=parsed.note or "-",
                )

                # 같은 MAC이면 최신 응답으로 갱신
                # 같은 IP라도 MAC이 다르면 별도 장비로 유지
                found_by_mac[(device.mac12 or "").strip().upper()] = device

            elapsed = time.time() - started_at
            if elapsed >= max(0.0, float(min_wait)) and found_by_mac:
                if last_packet_at is not None and (time.time() - last_packet_at) >= max(0.0, float(quiet_exit)):
                    break

            time.sleep(0.02)

        return bind_ip, _sort_devices(list(found_by_mac.values()))
    finally:
        safe_close_socket(sock)