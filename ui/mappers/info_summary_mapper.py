from __future__ import annotations

from domain.models.device_snapshot import DeviceSnapshot


INFO_FIELDS: tuple[tuple[str, str], ...] = (
    ("MAC address", "mac"),
    ("Model", "model"),
    ("Firmware", "firmware"),
    ("Type", "type_text"),
    ("Module version", "module_version"),
    ("PTZ F/W", "ptz_fw"),
    ("LD", "linkdown_num"),
    ("Local IP mode", "local_ip_mode"),
    ("Power Type", "power_type"),
    ("Start up time", "startup_time"),
    ("Disk", "disk_text"),
    ("AI version", "ai_version"),
    ("RCV version", "rcv_version"),
)


def _safe_attr(obj: object, name: str, default: str = "-") -> str:
    value = getattr(obj, name, default)
    text = str(value).strip() if value is not None else ""
    return text if text else default


def map_info_summary(snapshot: DeviceSnapshot | None) -> dict[str, str]:
    if snapshot is None:
        return {label: "-" for label, _ in INFO_FIELDS}

    source = {
        "mac": snapshot.mac or "-",
        "model": snapshot.model or "-",
        "firmware": snapshot.firmware or snapshot.sys_version or "-",
        "type_text": _safe_attr(snapshot, "sys_mode_text"),
        "module_version": _safe_attr(snapshot, "module_version"),
        "ptz_fw": _safe_attr(snapshot, "ptz_fw"),
        "linkdown_num": _safe_attr(snapshot, "linkdown_num"),
        "local_ip_mode": _safe_attr(snapshot, "local_ip_mode"),
        "power_type": _safe_attr(snapshot, "power_type"),
        "startup_time": _safe_attr(snapshot, "startup_time"),
        "disk_text": _safe_attr(snapshot, "disk_text"),
        "ai_version": _safe_attr(snapshot, "ai_version"),
        "rcv_version": _safe_attr(snapshot, "rcv_version"),
    }
    return {label: str(source.get(key, "-") or "-") for label, key in INFO_FIELDS}