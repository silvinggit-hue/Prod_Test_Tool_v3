from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchedulerSettings:
    scheduler_tick_ms: int = 50
    retry_tick_ms: int = 100

    global_http_max: int = 16

    control_max: int = 6
    connect_max: int = 4
    info_manual_max: int = 4
    poll_hot_max: int = 4
    poll_warm_max: int = 2
    firmware_max: int = 1
    udp_admin_max: int = 1

    max_inflight_per_device: int = 1

    hot_poll_interval_sec: float = 1.0
    warm_poll_interval_sec: float = 15.0
    hot_page_size: int = 10

    @classmethod
    def load(cls) -> "SchedulerSettings":
        return cls()