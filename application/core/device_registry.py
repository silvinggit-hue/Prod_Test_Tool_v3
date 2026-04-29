from __future__ import annotations

import threading
from dataclasses import replace
from typing import TYPE_CHECKING

from domain.enums.app_mode import AppMode
from domain.enums.device import DeviceState
from domain.models.app_snapshot import AppSnapshot
from domain.models.device_snapshot import DeviceSnapshot

if TYPE_CHECKING:
    from application.core.device_actor import DeviceActor


class DeviceRegistry:
    def __init__(self) -> None:
        self.actors_by_ip: dict[str, DeviceActor] = {}
        self.snapshots_by_ip: dict[str, DeviceSnapshot] = {}
        self.ordered_ips: list[str] = []
        self.selected_ips: set[str] = set()
        self.focused_ip: str | None = None
        self._lock = threading.RLock()

    def has_device(self, ip: str) -> bool:
        with self._lock:
            return ip in self.snapshots_by_ip

    def ensure_device(self, ip: str, *, port: int = 0, note: str = "") -> DeviceSnapshot:
        with self._lock:
            if ip in self.snapshots_by_ip:
                return self.snapshots_by_ip[ip]

            snapshot = DeviceSnapshot(
                ip=ip,
                port=port,
                note=note,
                state=DeviceState.DISCOVERED,
                connected=False,
                info_loaded=False,
            )
            self.snapshots_by_ip[ip] = snapshot
            self.ordered_ips.append(ip)
            return snapshot

    def attach_actor(self, ip: str, actor: "DeviceActor") -> None:
        with self._lock:
            self.actors_by_ip[ip] = actor

    def get_actor(self, ip: str) -> "DeviceActor | None":
        with self._lock:
            return self.actors_by_ip.get(ip)

    def get_snapshot(self, ip: str) -> DeviceSnapshot | None:
        with self._lock:
            return self.snapshots_by_ip.get(ip)

    def require_snapshot(self, ip: str) -> DeviceSnapshot:
        with self._lock:
            snapshot = self.snapshots_by_ip.get(ip)
            if snapshot is None:
                raise KeyError(f"device not found: {ip}")
            return snapshot

    def upsert_snapshot(self, snapshot: DeviceSnapshot) -> DeviceSnapshot:
        with self._lock:
            if snapshot.ip not in self.snapshots_by_ip:
                self.ordered_ips.append(snapshot.ip)

            self.snapshots_by_ip[snapshot.ip] = snapshot

            if snapshot.selected:
                self.selected_ips.add(snapshot.ip)
            else:
                self.selected_ips.discard(snapshot.ip)

            if snapshot.focused:
                self.focused_ip = snapshot.ip
            elif self.focused_ip == snapshot.ip and not snapshot.focused:
                self.focused_ip = None

            return snapshot

    def update_snapshot(self, ip: str, **changes) -> DeviceSnapshot:
        with self._lock:
            current = self.snapshots_by_ip.get(ip)
            if current is None:
                raise KeyError(f"device not found: {ip}")
            updated = replace(current, **changes)
            return self.upsert_snapshot(updated)

    def set_selected(self, ip: str, selected: bool) -> DeviceSnapshot:
        with self._lock:
            snapshot = self.snapshots_by_ip.get(ip)
            if snapshot is None:
                raise KeyError(f"device not found: {ip}")
            updated = replace(snapshot, selected=bool(selected))
            return self.upsert_snapshot(updated)

    def set_selected_many(self, ips: list[str], selected: bool) -> None:
        for ip in ips:
            if self.has_device(ip):
                self.set_selected(ip, selected)

    def clear_selection(self) -> None:
        with self._lock:
            ips = list(self.selected_ips)
        for ip in ips:
            self.set_selected(ip, False)

    def set_focused(self, ip: str | None) -> None:
        with self._lock:
            current = self.focused_ip

        if current and current != ip and self.has_device(current):
            old_snapshot = self.require_snapshot(current)
            self.upsert_snapshot(replace(old_snapshot, focused=False))

        with self._lock:
            self.focused_ip = None

        if ip and self.has_device(ip):
            snapshot = self.require_snapshot(ip)
            self.upsert_snapshot(replace(snapshot, focused=True))
            with self._lock:
                self.focused_ip = ip

    def list_snapshots(self) -> list[DeviceSnapshot]:
        with self._lock:
            ordered = list(self.ordered_ips)
            snapshots = dict(self.snapshots_by_ip)
        return [snapshots[ip] for ip in ordered if ip in snapshots]

    def iter_connected_ips(self) -> list[str]:
        with self._lock:
            ordered = list(self.ordered_ips)
            snapshots = dict(self.snapshots_by_ip)
        return [
            ip
            for ip in ordered
            if ip in snapshots and snapshots[ip].connected
        ]

    def build_app_snapshot(
        self,
        *,
        current_video_page: int = 0,
        video_page_size: int = 10,
        visible_video_ips: tuple[str, ...] = (),
        app_mode: AppMode = AppMode.NORMAL,
        firmware_window_open: bool = False,
        video_window_open: bool = False,
    ) -> AppSnapshot:
        with self._lock:
            devices = dict(self.snapshots_by_ip)
            ordered = tuple(self.ordered_ips)
            selected = tuple(ip for ip in self.ordered_ips if ip in self.selected_ips)
            focused_ip = self.focused_ip

        total_count = len(devices)
        connected_count = sum(1 for s in devices.values() if s.connected)
        busy_count = sum(1 for s in devices.values() if s.command.inflight or s.command.queued_count > 0)
        failed_count = sum(
            1
            for s in devices.values()
            if s.state in (DeviceState.AUTH_FAILED, DeviceState.BACKOFF, DeviceState.DISCONNECTED)
        )

        return AppSnapshot(
            devices=devices,
            ordered_ips=ordered,
            selected_ips=selected,
            focused_ip=focused_ip,
            total_count=total_count,
            connected_count=connected_count,
            busy_count=busy_count,
            failed_count=failed_count,
            selected_count=len(selected),
            current_video_page=current_video_page,
            video_page_size=video_page_size,
            visible_video_ips=visible_video_ips,
            app_mode=app_mode,
            firmware_window_open=firmware_window_open,
            video_window_open=video_window_open,
        )

    def remove_device(self, ip: str) -> bool:
        with self._lock:
            existed = ip in self.snapshots_by_ip or ip in self.actors_by_ip
            if not existed:
                return False

            self.snapshots_by_ip.pop(ip, None)
            self.actors_by_ip.pop(ip, None)

            if ip in self.ordered_ips:
                self.ordered_ips = [item for item in self.ordered_ips if item != ip]

            self.selected_ips.discard(ip)

            if self.focused_ip == ip:
                self.focused_ip = None

            return True