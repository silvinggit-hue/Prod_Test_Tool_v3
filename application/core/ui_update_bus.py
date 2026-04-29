from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class UiUpdateBatch:
    dirty_device_ids: tuple[str, ...] = ()
    dirty_app_flags: tuple[str, ...] = ()
    has_changes: bool = False


class UiUpdateBus:
    def __init__(self) -> None:
        self._dirty_device_ids: set[str] = set()
        self._dirty_app_flags: set[str] = set()
        self._lock = threading.RLock()

    def mark_device_dirty(self, ip: str) -> None:
        if not ip:
            return
        with self._lock:
            self._dirty_device_ids.add(ip)

    def mark_devices_dirty(self, ips: list[str] | tuple[str, ...]) -> None:
        with self._lock:
            for ip in ips:
                if ip:
                    self._dirty_device_ids.add(ip)

    def mark_app_dirty(self, flag: str) -> None:
        if not flag:
            return
        with self._lock:
            self._dirty_app_flags.add(flag)

    def flush(self) -> UiUpdateBatch:
        with self._lock:
            devices = tuple(sorted(self._dirty_device_ids))
            app_flags = tuple(sorted(self._dirty_app_flags))
            self._dirty_device_ids.clear()
            self._dirty_app_flags.clear()

        return UiUpdateBatch(
            dirty_device_ids=devices,
            dirty_app_flags=app_flags,
            has_changes=bool(devices or app_flags),
        )