from __future__ import annotations

from dataclasses import dataclass, field

from domain.enums.device import DeviceFlavor, DeviceState
from domain.models.device_state import DeviceCommandState, DeviceLiveMetrics


@dataclass(frozen=True)
class DeviceSnapshot:
    ip: str
    port: int = 0

    mac: str = ""
    mac12: str = ""
    model: str = ""
    firmware: str = ""
    lens: str = ""
    note: str = ""

    selected: bool = False
    focused: bool = False

    state: DeviceState = DeviceState.DISCOVERED
    connected: bool = False
    info_loaded: bool = False

    base_url: str = ""
    root_path: str = ""
    auth_scheme: str = ""
    flavor: DeviceFlavor = DeviceFlavor.UNKNOWN

    username: str = ""
    effective_password: str = ""

    default_password_state: bool | None = None
    password_changed: bool | None = None

    board_id: str = ""
    module_type: str = ""
    module_detail: str = ""
    ptz_type: str = ""
    zoom_module: str = ""

    sys_version: str = ""
    last_success_at: float | None = None

    # Step 5 UI용 표시 필드
    sys_mode_text: str = "-"
    module_version: str = "-"
    ptz_fw: str = "-"
    extra_id: str = "-"
    linkdown_num: str = "-"
    local_ip_mode: str = "-"
    power_type: str = "-"
    startup_time: str = "-"
    disk_text: str = "-"
    ai_version: str = "-"
    rcv_version: str = "-"
    air_wiper: str = "-"
    ethernet_speed_rate: str = "-"

    command: DeviceCommandState = field(default_factory=DeviceCommandState)
    metrics: DeviceLiveMetrics = field(default_factory=DeviceLiveMetrics)