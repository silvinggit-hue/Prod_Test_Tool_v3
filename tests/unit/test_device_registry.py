from __future__ import annotations

from application.core.device_registry import DeviceRegistry
from domain.enums.app_mode import AppMode
from domain.enums.device import DeviceState


def test_registry_tracks_devices_selection_and_focus() -> None:
    registry = DeviceRegistry()

    registry.ensure_device("192.168.10.10")
    registry.ensure_device("192.168.10.11")

    registry.set_selected("192.168.10.10", True)
    registry.set_focused("192.168.10.11")

    assert registry.ordered_ips == ["192.168.10.10", "192.168.10.11"]
    assert "192.168.10.10" in registry.selected_ips
    assert registry.focused_ip == "192.168.10.11"

    snap = registry.get_snapshot("192.168.10.11")
    assert snap is not None
    assert snap.focused is True


def test_registry_build_app_snapshot_counts() -> None:
    registry = DeviceRegistry()
    registry.ensure_device("192.168.10.10")
    registry.ensure_device("192.168.10.11")

    registry.update_snapshot("192.168.10.10", connected=True, state=DeviceState.READY)
    registry.update_snapshot("192.168.10.11", state=DeviceState.AUTH_FAILED)

    app = registry.build_app_snapshot(
        current_video_page=0,
        video_page_size=10,
        visible_video_ips=("192.168.10.10",),
        app_mode=AppMode.NORMAL,
    )

    assert app.total_count == 2
    assert app.connected_count == 1
    assert app.failed_count == 1
    assert app.visible_video_ips == ("192.168.10.10",)