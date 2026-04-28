from __future__ import annotations

from domain.models.device_snapshot import DeviceSnapshot


STATUS_FIELDS: tuple[tuple[str, str], ...] = (
    ("CDS", "cds"),
    ("Current Y", "current_y"),
    ("Primary", "primary"),
    ("Secondary", "secondary"),
    ("RTC Time", "rtc_time"),
    ("Ethernet", "ethernet"),
    ("Board Temp", "board_temp"),
    ("Fan Status", "fan_status"),
    ("Air Wiper", "air_wiper"),
    ("Ethernet Speed Rate", "ethernet_speed_rate"),
)


def _safe_attr(obj: object, name: str, default: str = "-") -> str:
    value = getattr(obj, name, default)
    text = str(value).strip() if value is not None else ""
    return text if text else default


def map_status_summary(snapshot: DeviceSnapshot | None) -> dict[str, str]:
    if snapshot is None:
        return {label: "-" for label, _ in STATUS_FIELDS}

    metrics = snapshot.metrics
    source = {
        "cds": metrics.cds_text or "-",
        "current_y": metrics.current_y_text or "-",
        "primary": metrics.rate1_text or "-",
        "secondary": metrics.rate2_text or "-",
        "rtc_time": metrics.rtc_text or "-",
        "ethernet": metrics.eth_text or "-",
        "board_temp": metrics.temp_text or "-",
        "fan_status": metrics.fan_text or "-",
        "air_wiper": _safe_attr(snapshot, "air_wiper"),
        "ethernet_speed_rate": _safe_attr(snapshot, "ethernet_speed_rate", metrics.eth_text or "-"),
    }

    return {label: str(source.get(key, "-") or "-") for label, key in STATUS_FIELDS}