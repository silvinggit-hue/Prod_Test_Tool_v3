from __future__ import annotations

from infra.device.info_repository import (
    build_disk_text,
    build_info_summary_map,
    build_missing_keys,
    merge_nonempty_kv,
)


def test_merge_nonempty_kv_prefers_nonempty_later_values() -> None:
    a = {"SYS_VERSION": "V1.0.0", "SYS_MODELNAME": ""}
    b = {"SYS_MODELNAME": "ABC-1000", "SYS_BOARDID": "12"}
    merged = merge_nonempty_kv(a, b)

    assert merged["SYS_VERSION"] == "V1.0.0"
    assert merged["SYS_MODELNAME"] == "ABC-1000"
    assert merged["SYS_BOARDID"] == "12"


def test_build_disk_text() -> None:
    kv = {
        "REC_DISKTYPE": "SD",
        "REC_DISKSIZE": "64GB",
        "REC_DISKAVAILABLE": "32GB",
    }
    assert build_disk_text(kv) == "SD 32GB / 64GB"


def test_build_info_summary_map() -> None:
    kv = {
        "NET_MAC": "AA:BB:CC:DD:EE:FF",
        "SYS_MODELNAME_ID": "TRN-1000",
        "SYS_VERSION": "V1.2.3",
        "SYS_MODE": "0",
        "CAM_READMODULEVERSION": "M-1.0",
        "CAM_READMECAVERSION": "P-2.0",
        "NET_LOCALIPMODE": "1",
        "TEST_Power_CheckString": "POE",
        "SYS_STARTTIME": "2026/04/27 10:00:00",
        "REC_DISKTYPE": "SD",
        "REC_DISKSIZE": "128GB",
        "REC_DISKAVAILABLE": "100GB",
        "SYS_AI_VERSION": "AI-1.0",
        "SYS_RCV_VERSION": "RCV-2.0",
    }

    summary = build_info_summary_map(kv)

    assert summary["mac"] == "AA:BB:CC:DD:EE:FF"
    assert summary["sys_modelname"] == "TRN-1000"
    assert summary["sys_version"] == "V1.2.3"
    assert summary["sys_mode"] == "Encoder"
    assert summary["local_ip_mode"] == "DHCP"
    assert summary["disk"] == "SD 100GB / 128GB"


def test_build_missing_keys() -> None:
    missing = build_missing_keys(("A", "B", "C"), {"A": "1", "B": ""})
    assert missing == ("B", "C")