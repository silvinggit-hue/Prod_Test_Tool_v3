from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FirmwareSettings:
    upload_parallelism_default: int = 16
    upload_parallelism_max: int = 24

    reboot_wait_sec: float = 40.0
    reconnect_interval_sec: float = 2.0
    reconnect_timeout_sec: float = 120.0

    verify_max_attempts: int = 3
    verify_interval_sec: float = 3.0

    upload_timeout_sec: float = 40.0
    probe_timeout_sec: float = 5.0
    verify_read_timeout_sec: float = 10.0

    ui_flush_ms: int = 100
    delay_scheduler_tick_ms: int = 200

    @classmethod
    def load(cls) -> "FirmwareSettings":
        return cls()