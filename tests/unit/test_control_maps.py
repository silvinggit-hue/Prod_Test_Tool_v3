from __future__ import annotations

from infra.device.control_repository import (
    FOCUS_MAP,
    ICR_MAP,
    PT_DIR_MAP,
    TDN_MAP,
    ZOOM_MAP,
    parse_pt_speed,
)


def test_pt_dir_map_contains_expected_actions() -> None:
    assert PT_DIR_MAP["up"] == "up"
    assert PT_DIR_MAP["stop"] == "stop"
    assert PT_DIR_MAP["leftdown"] == "leftdown"


def test_zoom_and_focus_maps() -> None:
    assert ZOOM_MAP["in"] == "zoomin,-1"
    assert ZOOM_MAP["1x"] is None
    assert FOCUS_MAP["near"] == "focusnear,-1"
    assert FOCUS_MAP["auto"] is None


def test_tdn_icr_maps() -> None:
    assert TDN_MAP["auto"] == "0"
    assert TDN_MAP["day"] == "2"
    assert ICR_MAP["auto"] == "0"
    assert ICR_MAP["on"] == "1"
    assert ICR_MAP["off"] == "2"


def test_parse_pt_speed_bounds() -> None:
    assert parse_pt_speed(None) == 5
    assert parse_pt_speed("0") == 1
    assert parse_pt_speed("9") == 8
    assert parse_pt_speed("3") == 3