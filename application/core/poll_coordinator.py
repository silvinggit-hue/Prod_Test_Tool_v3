from __future__ import annotations

from dataclasses import dataclass

from application.core.device_registry import DeviceRegistry


@dataclass(frozen=True)
class PollSets:
    hot_ips: tuple[str, ...]
    warm_ips: tuple[str, ...]


class PollCoordinator:
    def __init__(self, *, page_size: int = 10) -> None:
        self.page_size = int(page_size)
        self.current_page = 0
        self.hot_ips: tuple[str, ...] = ()
        self.warm_ips: tuple[str, ...] = ()

    def set_current_page(self, page_index: int) -> None:
        self.current_page = max(0, int(page_index))

    def compute_sets(self, registry: DeviceRegistry) -> PollSets:
        connected = registry.iter_connected_ips()
        start = self.current_page * self.page_size
        end = start + self.page_size

        hot = tuple(connected[start:end])
        hot_set = set(hot)
        warm = tuple(ip for ip in connected if ip not in hot_set)

        self.hot_ips = hot
        self.warm_ips = warm
        return PollSets(hot_ips=hot, warm_ips=warm)

    def visible_page_ips(self) -> tuple[str, ...]:
        return self.hot_ips