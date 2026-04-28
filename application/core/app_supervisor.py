from __future__ import annotations

import logging
import threading
import time

from application.core.command_factory import CommandFactory
from application.core.device_actor import DeviceActor
from application.core.device_registry import DeviceRegistry
from application.core.poll_coordinator import PollCoordinator
from application.core.task_scheduler import TaskScheduler
from application.core.ui_update_bus import UiUpdateBatch, UiUpdateBus
from application.services.connect_service import CameraConnectService
from config.app_settings import AppSettings
from config.ui_settings import UiSettings
from domain.enums.app_mode import AppMode
from domain.models.app_snapshot import AppSnapshot
from domain.models.phase1 import Phase1Request
from infra.device.control_repository import ControlRepository
from infra.device.info_repository import InfoRepository
from infra.device.status_repository import StatusRepository

log = logging.getLogger(__name__)


class AppSupervisor:
    def __init__(
        self,
        *,
        settings: AppSettings | None = None,
        ui_settings: UiSettings | None = None,
        connect_service: CameraConnectService | None = None,
        info_repository: InfoRepository | None = None,
        status_repository: StatusRepository | None = None,
        control_repository: ControlRepository | None = None,
    ) -> None:
        self.settings = settings or AppSettings.load()
        self.ui_settings = ui_settings or UiSettings.load()

        self.registry = DeviceRegistry()
        self.ui_update_bus = UiUpdateBus()
        self.poll_coordinator = PollCoordinator(page_size=self.ui_settings.device_page_size)

        self.connect_service = connect_service or CameraConnectService(settings=self.settings)
        self.info_repository = info_repository or InfoRepository()
        self.status_repository = status_repository or StatusRepository()
        self.control_repository = control_repository or ControlRepository()

        self.scheduler = TaskScheduler(registry=self.registry)

        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._scheduler_thread: threading.Thread | None = None

    def start(self) -> None:
        if self._scheduler_thread is not None and self._scheduler_thread.is_alive():
            return

        self._stop_event.clear()
        self._wake_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="TaskSchedulerThread",
            daemon=True,
        )
        self._scheduler_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()

        thread = self._scheduler_thread
        self._scheduler_thread = None

        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def wake_scheduler(self) -> None:
        self._wake_event.set()

    def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            progressed = False

            try:
                progressed = self.scheduler.dispatch_once()
            except Exception:
                log.exception("scheduler dispatch failed")

            if progressed:
                continue

            self._wake_event.wait(timeout=0.05)
            self._wake_event.clear()

    def add_device(self, ip: str, *, port: int = 0, note: str = "") -> None:
        self.registry.ensure_device(ip, port=port, note=note)
        actor = self.registry.get_actor(ip)
        if actor is None:
            actor = DeviceActor(
                ip=ip,
                registry=self.registry,
                ui_update_bus=self.ui_update_bus,
                connect_service=self.connect_service,
                info_repository=self.info_repository,
                status_repository=self.status_repository,
                control_repository=self.control_repository,
                verify_tls=self.settings.verify_tls,
                default_timeout_sec=self.settings.timeout.read_sec,
            )
            self.registry.attach_actor(ip, actor)

        self.ui_update_bus.mark_device_dirty(ip)
        self.ui_update_bus.mark_app_dirty("devices")

    def add_devices(self, ips: list[str]) -> None:
        for ip in ips:
            self.add_device(ip)

    def set_selected(self, ip: str, selected: bool) -> None:
        self.registry.set_selected(ip, selected)
        self.ui_update_bus.mark_device_dirty(ip)
        self.ui_update_bus.mark_app_dirty("selection")

    def set_focused(self, ip: str | None) -> None:
        old_focused = self.registry.focused_ip
        self.registry.set_focused(ip)
        if old_focused:
            self.ui_update_bus.mark_device_dirty(old_focused)
        if ip:
            self.ui_update_bus.mark_device_dirty(ip)
        self.ui_update_bus.mark_app_dirty("focus")

    def set_current_video_page(self, page_index: int) -> None:
        self.poll_coordinator.set_current_page(page_index)
        poll_sets = self.poll_coordinator.compute_sets(self.registry)
        self.ui_update_bus.mark_devices_dirty(list(poll_sets.hot_ips))
        self.ui_update_bus.mark_app_dirty("video_page")

    def enqueue_connect(self, device_ip: str, request: Phase1Request) -> None:
        task = CommandFactory.connect(device_ip, request)
        self.scheduler.enqueue(task)
        self.ui_update_bus.mark_device_dirty(device_ip)
        self.wake_scheduler()

    def enqueue_info_load(self, device_ip: str) -> None:
        task = CommandFactory.info_load(device_ip)
        self.scheduler.enqueue(task)
        self.ui_update_bus.mark_device_dirty(device_ip)
        self.wake_scheduler()

    def enqueue_status_poll(self, device_ip: str, *, hot: bool) -> None:
        task = CommandFactory.status_poll(device_ip, hot=hot)
        self.scheduler.enqueue(task)
        self.ui_update_bus.mark_device_dirty(device_ip)
        self.wake_scheduler()

    def enqueue_control(self, device_ip: str, *, handler: str, kwargs: dict | None = None) -> None:
        task = CommandFactory.control(device_ip, handler=handler, kwargs=kwargs)
        self.scheduler.enqueue(task)
        self.ui_update_bus.mark_device_dirty(device_ip)
        self.wake_scheduler()

    def enqueue_hot_polls_for_visible_page(self) -> None:
        poll_sets = self.poll_coordinator.compute_sets(self.registry)
        for ip in poll_sets.hot_ips:
            self.enqueue_status_poll(ip, hot=True)
        for ip in poll_sets.warm_ips:
            self.enqueue_status_poll(ip, hot=False)

    def flush_ui_updates(self) -> UiUpdateBatch:
        return self.ui_update_bus.flush()

    def get_snapshot(self, ip: str):
        return self.registry.get_snapshot(ip)

    def get_app_snapshot(self) -> AppSnapshot:
        visible = self.poll_coordinator.visible_page_ips()
        return self.registry.build_app_snapshot(
            current_video_page=self.poll_coordinator.current_page,
            video_page_size=self.poll_coordinator.page_size,
            visible_video_ips=visible,
            app_mode=AppMode.NORMAL,
            firmware_window_open=False,
            video_window_open=False,
        )