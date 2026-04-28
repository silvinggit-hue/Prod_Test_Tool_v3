from __future__ import annotations

from application.core.device_actor import DeviceActor
from application.core.device_registry import DeviceRegistry
from application.core.task_scheduler import TaskScheduler
from application.core.ui_update_bus import UiUpdateBus
from domain.enums.command import CommandKind, TaskLane
from domain.models.phase1 import Phase1Request, Phase1Response
from domain.models.tasks import TaskSpec


class _RecordingConnectService:
    def connect(self, request: Phase1Request) -> Phase1Response:
        return Phase1Response(
            ok=True,
            base_url=f"https://{request.ip}:443",
            root_path="/httpapi/",
            auth_scheme="digest",
            flavor="legacy",
            sys_version="V1.0.0",
            effective_username="admin",
            effective_password="123",
        )


class _NoopInfoRepository:
    def build_client(self, **kwargs):
        return object()

    def read_info_kv(self, client):
        class Result:
            merged_kv = {"SYS_VERSION": "V1.0.0"}

        return Result()


class _NoopStatusRepository:
    def build_client(self, **kwargs):
        return object()

    def read_status_kv(self, client):
        class Result:
            merged_kv = {}

        return Result()


class _RecordingControlRepository:
    def __init__(self, record: list[str]) -> None:
        self.record = record

    def build_client(self, **kwargs):
        return object()

    def reboot(self, client):
        self.record.append("control:reboot")

        class Result:
            response_text = "ok"

        return Result()


def _build_scheduler_with_actor(record: list[str]) -> tuple[DeviceRegistry, TaskScheduler]:
    registry = DeviceRegistry()
    registry.ensure_device("192.168.10.100")
    ui_bus = UiUpdateBus()

    actor = DeviceActor(
        ip="192.168.10.100",
        registry=registry,
        ui_update_bus=ui_bus,
        connect_service=_RecordingConnectService(),
        info_repository=_NoopInfoRepository(),
        status_repository=_NoopStatusRepository(),
        control_repository=_RecordingControlRepository(record),
        verify_tls=False,
        default_timeout_sec=6.0,
    )
    registry.attach_actor("192.168.10.100", actor)

    scheduler = TaskScheduler(registry=registry)
    return registry, scheduler


def test_scheduler_prefers_control_lane_over_poll() -> None:
    record: list[str] = []
    registry, scheduler = _build_scheduler_with_actor(record)

    # connect first so control can run without session error
    scheduler.enqueue(
        TaskSpec(
            task_id="connect-1",
            device_ip="192.168.10.100",
            command=CommandKind.CONNECT,
            lane=TaskLane.CONNECT,
            priority=10,
            payload={"request": Phase1Request(ip="192.168.10.100")},
        )
    )
    scheduler.run_until_idle()

    scheduler.enqueue(
        TaskSpec(
            task_id="poll-1",
            device_ip="192.168.10.100",
            command=CommandKind.STATUS_POLL,
            lane=TaskLane.POLL_HOT,
            priority=1,
            payload={},
        )
    )
    scheduler.enqueue(
        TaskSpec(
            task_id="control-1",
            device_ip="192.168.10.100",
            command=CommandKind.CONTROL,
            lane=TaskLane.CONTROL,
            priority=1,
            payload={"handler": "reboot", "kwargs": {}},
        )
    )

    # first dispatch should execute control lane before poll_hot
    scheduler.dispatch_once()
    assert record == ["control:reboot"]


def test_scheduler_respects_device_busy_and_requeues() -> None:
    record: list[str] = []
    registry, scheduler = _build_scheduler_with_actor(record)
    actor = registry.get_actor("192.168.10.100")
    assert actor is not None

    fake_busy = TaskSpec(
        task_id="busy-1",
        device_ip="192.168.10.100",
        command=CommandKind.CONNECT,
        lane=TaskLane.CONNECT,
        payload={"request": Phase1Request(ip="192.168.10.100")},
    )
    actor.begin_task(fake_busy)

    queued = TaskSpec(
        task_id="info-1",
        device_ip="192.168.10.100",
        command=CommandKind.INFO_LOAD,
        lane=TaskLane.INFO,
        payload={},
    )
    scheduler.enqueue(queued)

    dispatched = scheduler.dispatch_once()
    assert dispatched is False
    assert scheduler.queue_size(TaskLane.INFO) == 1

    actor.finish_task(message="released")


def test_scheduler_run_until_idle() -> None:
    record: list[str] = []
    _, scheduler = _build_scheduler_with_actor(record)

    scheduler.enqueue(
        TaskSpec(
            task_id="connect-1",
            device_ip="192.168.10.100",
            command=CommandKind.CONNECT,
            lane=TaskLane.CONNECT,
            payload={"request": Phase1Request(ip="192.168.10.100")},
        )
    )
    scheduler.enqueue(
        TaskSpec(
            task_id="control-1",
            device_ip="192.168.10.100",
            command=CommandKind.CONTROL,
            lane=TaskLane.CONTROL,
            payload={"handler": "reboot", "kwargs": {}},
        )
    )

    steps = scheduler.run_until_idle()
    assert steps == 2
    assert record == ["control:reboot"]