from __future__ import annotations

import math
from dataclasses import dataclass

from application.core.device_registry import DeviceRegistry
from domain.models.device_snapshot import DeviceSnapshot
from infra.device.video_profile_repository import (
    VideoProfileRepository,
    default_rtsp_profile,
    is_tcs_multi_channel_model,
)


@dataclass(frozen=True)
class VideoStreamItem:
    ip: str
    model: str
    username: str
    password: str
    rtsp_port: int
    rtsp_profiles: dict[str, str]
    default_profile: str


@dataclass(frozen=True)
class VideoPagePlan:
    mode_label: str
    target_count: int
    current_page: int
    page_count: int
    visible_ips: tuple[str, ...]
    items: tuple[VideoStreamItem, ...]


class VideoCoordinator:
    def __init__(self, *, page_size: int = 10, profile_repository: VideoProfileRepository | None = None) -> None:
        self.page_size = max(1, int(page_size))
        self.profile_repository = profile_repository or VideoProfileRepository()

    def build_plan(
        self,
        *,
        registry: DeviceRegistry,
        checked_ips: list[str],
        selected_ips: list[str],
        focused_ip: str | None,
        page_index: int,
    ) -> VideoPagePlan:
        mode_label, targets = self._resolve_targets(
            registry=registry,
            checked_ips=checked_ips,
            selected_ips=selected_ips,
            focused_ip=focused_ip,
        )

        all_items = [self._build_stream_item(snapshot, mode_label=mode_label) for snapshot in targets]
        target_count = len(all_items)

        if target_count <= 0:
            return VideoPagePlan(
                mode_label=mode_label,
                target_count=0,
                current_page=0,
                page_count=1,
                visible_ips=(),
                items=(),
            )

        page_count = max(1, math.ceil(target_count / self.page_size))
        current_page = max(0, min(int(page_index), page_count - 1))

        start = current_page * self.page_size
        end = start + self.page_size
        items = tuple(all_items[start:end])

        return VideoPagePlan(
            mode_label=mode_label,
            target_count=target_count,
            current_page=current_page,
            page_count=page_count,
            visible_ips=tuple(item.ip for item in items),
            items=items,
        )

    def _resolve_targets(
        self,
        *,
        registry: DeviceRegistry,
        checked_ips: list[str],
        selected_ips: list[str],
        focused_ip: str | None,
    ) -> tuple[str, list[DeviceSnapshot]]:
        by_ip = {snapshot.ip: snapshot for snapshot in registry.list_snapshots()}

        checked_targets = [
            by_ip[ip]
            for ip in checked_ips
            if ip in by_ip and self._is_video_ready(by_ip[ip])
        ]
        if checked_targets:
            return "체크 장비", checked_targets

        selected_targets = [
            by_ip[ip]
            for ip in selected_ips
            if ip in by_ip and self._is_video_ready(by_ip[ip])
        ]
        if selected_targets:
            return "현재 장비", selected_targets[:1]

        if focused_ip and focused_ip in by_ip and self._is_video_ready(by_ip[focused_ip]):
            return "현재 장비", [by_ip[focused_ip]]

        return "현재 장비", []

    @staticmethod
    def _is_video_ready(snapshot: DeviceSnapshot) -> bool:
        return bool(
            snapshot.connected
            and (snapshot.username or "").strip()
            and (snapshot.effective_password or "").strip()
        )

    @staticmethod
    def _pick_rtsp_port(snapshot: DeviceSnapshot) -> int:
        for attr_name in ("net_rtspport", "rtsp_port", "rtsp_port_text"):
            raw = getattr(snapshot, attr_name, None)
            if raw not in (None, ""):
                try:
                    value = int(str(raw).strip())
                    if value > 0:
                        return value
                except Exception:
                    pass
        return 554

    @staticmethod
    def _select_default_profile(*, model_name: str, mode_label: str) -> str:
        if mode_label == "체크 장비":
            if is_tcs_multi_channel_model(model_name):
                return "ch1_secondary1"
            return "secondary1"
        return default_rtsp_profile(model_name)

    def _build_stream_item(self, snapshot: DeviceSnapshot, *, mode_label: str) -> VideoStreamItem:
        model_name = (snapshot.model or "").strip()
        rtsp_port = self._pick_rtsp_port(snapshot)

        profiles = self.profile_repository.build_profiles(
            ip=snapshot.ip,
            username=snapshot.username,
            password=snapshot.effective_password,
            rtsp_port=rtsp_port,
            model_name=model_name,
        )

        default_profile = self._select_default_profile(
            model_name=model_name,
            mode_label=mode_label,
        )
        if default_profile not in profiles:
            default_profile = self.profile_repository.default_profile(model_name)
            if default_profile not in profiles and profiles:
                default_profile = next(iter(profiles.keys()))

        return VideoStreamItem(
            ip=snapshot.ip,
            model=model_name or "-",
            username=snapshot.username,
            password=snapshot.effective_password,
            rtsp_port=rtsp_port,
            rtsp_profiles=profiles,
            default_profile=default_profile,
        )