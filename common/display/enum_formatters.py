from __future__ import annotations


_SYS_MODE_MAP = {
    "0": "Encoder",
    "1": "Decoder",
    "2": "Duplex",
}

_NET_LOCALIPMODE_MAP = {
    "0": "Fixed IP",
    "1": "DHCP",
}


def format_sys_mode(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return _SYS_MODE_MAP.get(text, text or "-")


def format_local_ip_mode(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return _NET_LOCALIPMODE_MAP.get(text, text or "-")


def format_display_value(key: str, value: object | None) -> str:
    normalized_key = (key or "").strip().upper()

    if value is None:
        return "-"

    if normalized_key == "SYS_MODE":
        return format_sys_mode(value)

    if normalized_key == "NET_LOCALIPMODE":
        return format_local_ip_mode(value)

    text = str(value).strip()
    return text if text else "-"