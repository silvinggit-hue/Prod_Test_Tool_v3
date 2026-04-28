
from __future__ import annotations

from infra.device.status_repository import (
    build_missing_keys,
    build_rate_text,
    build_status_summary_map,
    merge_nonempty_kv,
)


def test_build_rate_text() -> None:
    kv = {
        "GRS_VENCBITRATE1": "4096",
        "GRS_VENCFRAME1": "30",
    }
    assert build_rate_text(kv, 1) == "4096kbps / 30fps"
    assert build_rate_text({}, 1) == "-"


def test_build_status_summary_map() -> None:
    kv = {
        "GIS_CDS": "88",
        "CAM_HI_CURRENT_Y": "123",
        "GRS_VENCBITRATE1": "2048",
        "GRS_VENCFRAME1": "25",
        "SYS_CURRENTTIME": "2026/04/27 10:01:02",
        "SYS_BOARDTEMP": "45",
        "SYS_FANSTATUS": "ON",
        "ETHTOOL": "1000Mbps",
        "GRS_AENCBITRATE1": "64",
        "GRS_ADECBITRATE1": "64",
        "GRS_ADECALGORITHM1": "AAC",
        "GRS_ADECSAMPLERATE1": "48000",
    }

    summary = build_status_summary_map(kv)

    assert summary["cds"] == "88"
    assert summary["current_y"] == "123"
    assert summary["rate1"] == "2048kbps / 25fps"
    assert summary["rtc"] == "2026/04/27 10:01:02"
    assert summary["temp"] == "45"
    assert summary["fan"] == "ON"
    assert summary["eth"] == "1000Mbps"
    assert summary["audio_dec_algorithm"] == "AAC"


def test_merge_nonempty_status_kv() -> None:
    a = {"SYS_BOARDTEMP": "40", "ETHTOOL": ""}
    b = {"ETHTOOL": "100M", "GIS_CDS": "77"}
    merged = merge_nonempty_kv(a, b)

    assert merged["SYS_BOARDTEMP"] == "40"
    assert merged["ETHTOOL"] == "100M"
    assert merged["GIS_CDS"] == "77"


def test_build_missing_keys() -> None:
    missing = build_missing_keys(("A", "B"), {"A": "1", "B": ""})
    assert missing == ("B",)