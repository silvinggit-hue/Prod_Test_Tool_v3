from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class VideoProfile:
    key: str
    url: str


def is_tcs_multi_channel_model(model_name: str) -> bool:
    normalized = (model_name or "").strip().upper().replace(" ", "")
    return normalized.startswith("TCS-400") or normalized.startswith("TCS400") or normalized.startswith("TCS-410") or normalized.startswith("TCS410")


def _safe_rtsp_port(rtsp_port: int | str | None) -> int:
    try:
        value = int(str(rtsp_port).strip())
        return value if value > 0 else 554
    except Exception:
        return 554


def _build_rtsp_prefix(
    *,
    ip: str,
    username: str,
    password: str,
    rtsp_port: int | str | None,
) -> str:
    port = _safe_rtsp_port(rtsp_port)
    user_q = quote(username or "", safe="")
    pass_q = quote(password or "", safe="")
    return f"rtsp://{user_q}:{pass_q}@{ip}:{port}/"


def build_rtsp_profiles(
    *,
    ip: str,
    username: str,
    password: str,
    rtsp_port: int | str | None,
    model_name: str = "",
) -> dict[str, str]:
    prefix = _build_rtsp_prefix(
        ip=ip,
        username=username,
        password=password,
        rtsp_port=rtsp_port,
    )

    if is_tcs_multi_channel_model(model_name):
        return {
            "ch1_primary": prefix + "video1+audio1",
            "ch1_secondary1": prefix + "video1s+audio1",
            "ch2_primary": prefix + "video2+audio1",
            "ch2_secondary1": prefix + "video2s+audio1",
            "ch3_primary": prefix + "video3+audio1",
            "ch3_secondary1": prefix + "video3s+audio1",
            "ch4_primary": prefix + "video4+audio1",
            "ch4_secondary1": prefix + "video4s+audio1",
        }

    return {
        "primary": prefix + "video1+audio1",
        "secondary1": prefix + "video1s1+audio1",
        "secondary2": prefix + "video1s2+audio1",
        "secondary3": prefix + "video1s3+audio1",
    }


def default_rtsp_profile(model_name: str) -> str:
    return "ch1_primary" if is_tcs_multi_channel_model(model_name) else "primary"


def available_profile_keys(model_name: str) -> list[str]:
    if is_tcs_multi_channel_model(model_name):
        return [
            "ch1_primary",
            "ch1_secondary1",
            "ch2_primary",
            "ch2_secondary1",
            "ch3_primary",
            "ch3_secondary1",
            "ch4_primary",
            "ch4_secondary1",
        ]

    return [
        "primary",
        "secondary1",
        "secondary2",
        "secondary3",
    ]


class VideoProfileRepository:
    def build_profiles(
        self,
        *,
        ip: str,
        username: str,
        password: str,
        rtsp_port: int | str | None,
        model_name: str = "",
    ) -> dict[str, str]:
        return build_rtsp_profiles(
            ip=ip,
            username=username,
            password=password,
            rtsp_port=rtsp_port,
            model_name=model_name,
        )

    def default_profile(self, model_name: str) -> str:
        return default_rtsp_profile(model_name)

    def available_keys(self, model_name: str) -> list[str]:
        return available_profile_keys(model_name)