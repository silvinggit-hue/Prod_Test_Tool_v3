from __future__ import annotations

from common.display.display_names import display_name
from common.display.enum_formatters import (
    format_display_value,
    format_local_ip_mode,
    format_sys_mode,
)


def test_display_name_known_key() -> None:
    assert display_name("SYS_VERSION") == "Firmware"
    assert display_name("NET_RTSPPORT") == "RTSP Port"
    assert display_name("CAM_READMODULEVERSION") == "Module Version"


def test_display_name_unknown_key_fallback() -> None:
    assert display_name("SOME_UNKNOWN_KEY") == "Some Unknown Key"
    assert display_name("") == "-"


def test_enum_formatters() -> None:
    assert format_sys_mode("0") == "Encoder"
    assert format_sys_mode("1") == "Decoder"
    assert format_sys_mode("2") == "Duplex"

    assert format_local_ip_mode("0") == "Fixed IP"
    assert format_local_ip_mode("1") == "DHCP"

    assert format_display_value("SYS_MODE", "2") == "Duplex"
    assert format_display_value("NET_LOCALIPMODE", "1") == "DHCP"
    assert format_display_value("SYS_VERSION", "V1.2.3") == "V1.2.3"