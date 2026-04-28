from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from infra.discovery.udp_discovery import UdpDiscoveryDevice, run_udp_discovery


@dataclass(frozen=True)
class DiscoveryServiceRequest:
    bind_ip: str | None = None
    mask_bits: int = 24
    port: int = 64988
    seconds: float = 4.0
    repeat: int = 4
    interval: float = 0.12
    ignore_self: bool = True
    min_wait: float = 0.25
    quiet_exit: float = 0.18


@dataclass(frozen=True)
class DiscoveryServiceResult:
    bind_ip: str | None
    devices: list[UdpDiscoveryDevice]
    stopped: bool
    elapsed_sec: float


class DiscoveryService:
    def discover(
        self,
        request: DiscoveryServiceRequest,
        *,
        stop_requested: Callable[[], bool] | None = None,
    ) -> DiscoveryServiceResult:
        started = time.time()
        bind_ip, devices = run_udp_discovery(
            bind_ip=request.bind_ip,
            mask_bits=request.mask_bits,
            port=request.port,
            seconds=request.seconds,
            repeat=request.repeat,
            interval=request.interval,
            ignore_self=request.ignore_self,
            min_wait=request.min_wait,
            quiet_exit=request.quiet_exit,
            stop_requested=stop_requested,
        )
        stopped = bool(stop_requested and stop_requested())
        return DiscoveryServiceResult(
            bind_ip=bind_ip,
            devices=devices,
            stopped=stopped,
            elapsed_sec=max(0.0, time.time() - started),
        )