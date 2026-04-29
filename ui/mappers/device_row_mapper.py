from __future__ import annotations

from dataclasses import dataclass

from domain.models.device_snapshot import DeviceSnapshot
from ui.mappers.result_text_mapper import map_result_text


@dataclass(frozen=True)
class DeviceRow:
    selected: bool
    ip: str
    connected: str
    state: str

    mac_address: str
    model: str
    firmware: str
    type_text: str
    module_version: str
    ptz_fw: str
    linkdown_num: str
    local_ip_mode: str
    power_type: str
    startup_time: str
    disk: str
    ai_version: str
    rcv_version: str

    cds: str
    current_y: str
    primary: str
    secondary: str
    rtc_time: str
    ethernet: str
    board_temp: str
    fan_status: str
    air_wiper: str
    ethernet_speed_rate: str

    sensor_text: str
    sensor_raw: tuple[bool, bool, bool, bool]
    alarm_text: str
    alarm_raw: tuple[bool, bool, bool, bool]

    result: str


def _leds_to_text(values: tuple[bool, bool, bool, bool]) -> str:
    on_count = sum(1 for value in values if value)
    return f"{on_count}/4"


def _safe_attr(obj: object, name: str, default: str = "-") -> str:
    value = getattr(obj, name, default)
    text = str(value).strip() if value is not None else ""
    return text if text else default


def _primary_rate(snapshot: DeviceSnapshot) -> str:
    return snapshot.metrics.rate1_text or "-"


def _secondary_rate(snapshot: DeviceSnapshot) -> str:
    return snapshot.metrics.rate2_text or "-"


def map_device_row(snapshot: DeviceSnapshot) -> DeviceRow:
    metrics = snapshot.metrics

    return DeviceRow(
        selected=bool(snapshot.selected),
        ip=snapshot.ip,
        connected="Y" if snapshot.connected else "",
        state=snapshot.state.value,

        mac_address=snapshot.mac or "-",
        model=snapshot.model or "-",
        firmware=snapshot.firmware or snapshot.sys_version or "-",
        type_text=_safe_attr(snapshot, "sys_mode_text"),
        module_version=_safe_attr(snapshot, "module_version"),
        ptz_fw=_safe_attr(snapshot, "ptz_fw"),
        linkdown_num=_safe_attr(snapshot, "linkdown_num"),
        local_ip_mode=_safe_attr(snapshot, "local_ip_mode"),
        power_type=_safe_attr(snapshot, "power_type"),
        startup_time=_safe_attr(snapshot, "startup_time"),
        disk=_safe_attr(snapshot, "disk_text"),
        ai_version=_safe_attr(snapshot, "ai_version"),
        rcv_version=_safe_attr(snapshot, "rcv_version"),

        cds=metrics.cds_text or "-",
        current_y=metrics.current_y_text or "-",
        primary=_primary_rate(snapshot),
        secondary=_secondary_rate(snapshot),
        rtc_time=metrics.rtc_text or "-",
        ethernet=metrics.eth_text or "-",
        board_temp=metrics.temp_text or "-",
        fan_status=metrics.fan_text or "-",
        air_wiper=_safe_attr(snapshot, "air_wiper"),
        ethernet_speed_rate=_safe_attr(snapshot, "ethernet_speed_rate", metrics.eth_text or "-"),

        sensor_text=_leds_to_text(metrics.sensor_leds),
        sensor_raw=metrics.sensor_leds,
        alarm_text=_leds_to_text(metrics.alarm_leds),
        alarm_raw=metrics.alarm_leds,

        result=map_result_text(snapshot),
    )