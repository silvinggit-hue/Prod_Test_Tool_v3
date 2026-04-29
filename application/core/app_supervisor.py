from __future__ import annotations

import logging
import queue
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

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
from domain.enums.command import CommandKind
from domain.errors.app_error import AppError
from domain.models.app_snapshot import AppSnapshot
from domain.models.phase1 import Phase1Request
from domain.models.tasks import TaskSpec
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

        self._connect_executor: ThreadPoolExecutor | None = None
        self._default_executor: ThreadPoolExecutor | None = None

        self._completion_queue: queue.Queue[tuple[TaskSpec, bool, str]] = queue.Queue()
        self._batch_lock = threading.RLock()
        self._connect_batches: dict[str, dict] = {}

    def start(self) -> None:
        if self._scheduler_thread is not None and self._scheduler_thread.is_alive():
            return

        if self._connect_executor is None:
            self._connect_executor = ThreadPoolExecutor(
                max_workers=8,
                thread_name_prefix="connect-worker",
            )

        if self._default_executor is None:
            self._default_executor = ThreadPoolExecutor(
                max_workers=4,
                thread_name_prefix="default-worker",
            )

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

        if self._connect_executor is not None:
            self._connect_executor.shutdown(wait=False, cancel_futures=False)
            self._connect_executor = None

        if self._default_executor is not None:
            self._default_executor.shutdown(wait=False, cancel_futures=False)
            self._default_executor = None

    def wake_scheduler(self) -> None:
        self._wake_event.set()

    def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._drain_completion_queue()
            except Exception:
                log.exception("completion drain failed")

            dispatched_any = False

            try:
                tasks = self.scheduler.dispatch_ready_tasks(
                    connect_limit=8,
                    other_limit=4,
                )
            except Exception:
                log.exception("scheduler dispatch failed")
                tasks = []

            for task in tasks:
                try:
                    self._submit_task(task)
                    dispatched_any = True
                except Exception:
                    log.exception("task submit failed")
                    self.scheduler.mark_task_finished(task.device_ip)

            if dispatched_any:
                continue

            self._wake_event.wait(timeout=0.05)
            self._wake_event.clear()

    def _submit_task(self, task: TaskSpec) -> None:
        if task.command == CommandKind.CONNECT:
            executor = self._connect_executor
        else:
            executor = self._default_executor

        if executor is None:
            raise RuntimeError("executor is not started")

        executor.submit(self._run_task, task)

    def _run_task(self, task: TaskSpec) -> None:
        message = ""
        ok = True

        try:
            if not task.device_ip:
                raise AppError(kind="param", message="task missing device_ip")

            actor = self.registry.get_actor(task.device_ip)
            if actor is None:
                raise AppError(kind="state", message="actor not found", detail=task.device_ip)

            actor.execute_task(task)

        except Exception as exc:
            ok = False
            message = str(exc)

        finally:
            self._completion_queue.put((task, ok, message))
            self._wake_event.set()

    def _drain_completion_queue(self) -> None:
        while True:
            try:
                task, ok, message = self._completion_queue.get_nowait()
            except queue.Empty:
                break

            self.scheduler.mark_task_finished(task.device_ip)

            if task.device_ip:
                self.ui_update_bus.mark_device_dirty(task.device_ip)

            if task.command == CommandKind.CONNECT:
                self._handle_connect_completion(task, ok, message)

    def _handle_connect_completion(self, task: TaskSpec, ok: bool, message: str) -> None:
        batch_id = str((task.payload or {}).get("_connect_batch_id") or "").strip()
        if not batch_id:
            return

        device_ip = (task.device_ip or "").strip()
        if not device_ip:
            return

        success_ips: list[str] = []
        auto_info = False
        finished_now = False

        with self._batch_lock:
            state = self._connect_batches.get(batch_id)
            if state is None:
                return

            remaining = int(state.get("remaining", 0))
            if remaining > 0:
                state["remaining"] = remaining - 1

            if ok:
                state.setdefault("success_ips", []).append(device_ip)
            else:
                state.setdefault("failed_ips", []).append(device_ip)
                state.setdefault("last_error_messages", {})[device_ip] = message

            if int(state.get("remaining", 0)) <= 0:
                finished_now = True
                auto_info = bool(state.get("auto_info", False))
                success_ips = list(dict.fromkeys(state.get("success_ips", [])))
                self._connect_batches.pop(batch_id, None)

        if not finished_now:
            return

        self.ui_update_bus.mark_app_dirty("connect_batch")

        if auto_info:
            for ip in success_ips:
                snapshot = self.get_snapshot(ip)
                actor = self.registry.get_actor(ip)

                if snapshot is None or not snapshot.connected:
                    continue

                if actor is not None and hasattr(actor, "has_session") and not actor.has_session():
                    continue

                # 1) 제품 정보 다시 읽기
                self.enqueue_info_load(ip)

                # 2) 상태 poll도 같이 수행
                self.enqueue_status_poll(ip, hot=True)

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

    def enqueue_connect_batch(
        self,
        requests: list[tuple[str, Phase1Request]],
        *,
        auto_info: bool = True,
    ) -> str:
        batch_id = uuid.uuid4().hex

        with self._batch_lock:
            self._connect_batches[batch_id] = {
                "remaining": len(requests),
                "success_ips": [],
                "failed_ips": [],
                "auto_info": bool(auto_info),
            }

        for device_ip, request in requests:
            task = CommandFactory.connect(device_ip, request)
            payload = dict(task.payload or {})
            payload["_connect_batch_id"] = batch_id
            task = replace(task, payload=payload)

            self.scheduler.enqueue(task)
            self.ui_update_bus.mark_device_dirty(device_ip)

        self.ui_update_bus.mark_app_dirty("connect_batch")
        self.wake_scheduler()
        return batch_id

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

    def remove_device(self, ip: str) -> bool:
        actor = self.registry.get_actor(ip)
        if actor is not None and hasattr(actor, "disconnect"):
            try:
                actor.disconnect(reason="행 삭제")
            except Exception:
                pass

        removed = self.registry.remove_device(ip)
        if removed:
            self.ui_update_bus.mark_app_dirty("devices")
        return removed

    def remove_devices(self, ips: list[str]) -> int:
        removed_count = 0
        for ip in list(dict.fromkeys(ips)):
            if self.remove_device(ip):
                removed_count += 1
        return removed_count