from __future__ import annotations

from infra.device.video_profile_repository import (
    available_profile_keys,
    build_rtsp_profiles,
    default_rtsp_profile,
    is_tcs_multi_channel_model,
)


def test_normal_device_profiles() -> None:
    profiles = build_rtsp_profiles(
        ip="192.168.10.100",
        username="admin",
        password="123",
        rtsp_port=554,
        model_name="TRN-1000",
    )

    assert set(profiles.keys()) == {"primary", "secondary1", "secondary2", "secondary3"}
    assert profiles["primary"].startswith("rtsp://admin:123@192.168.10.100:554/")
    assert default_rtsp_profile("TRN-1000") == "primary"
    assert available_profile_keys("TRN-1000") == ["primary", "secondary1", "secondary2", "secondary3"]


def test_tcs_multi_channel_profiles() -> None:
    profiles = build_rtsp_profiles(
        ip="192.168.10.200",
        username="admin",
        password="!camera1108",
        rtsp_port=8554,
        model_name="TCS-400",
    )

    assert is_tcs_multi_channel_model("TCS-400") is True
    assert "ch1_primary" in profiles
    assert "ch4_secondary1" in profiles
    assert default_rtsp_profile("TCS-400") == "ch1_primary"
    assert available_profile_keys("TCS-400")[0] == "ch1_primary"