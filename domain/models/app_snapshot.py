from __future__ import annotations

from dataclasses import dataclass, field

from domain.enums.app_mode import AppMode
from domain.models.device_snapshot import DeviceSnapshot


@dataclass(frozen=True)
class AppSnapshot:
    devices: dict[str, DeviceSnapshot] = field(default_factory=dict)
    ordered_ips: tuple[str, ...] = ()
    selected_ips: tuple[str, ...] = ()
    focused_ip: str | None = None

    total_count: int = 0
    connected_count: int = 0
    busy_count: int = 0
    failed_count: int = 0
    selected_count: int = 0

    current_video_page: int = 0
    video_page_size: int = 10
    visible_video_ips: tuple[str, ...] = ()

    app_mode: AppMode = AppMode.NORMAL
    firmware_window_open: bool = False
    video_window_open: bool = False