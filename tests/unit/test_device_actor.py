from __future__ import annotations

from dataclasses import dataclass

from application.core.device_actor import DeviceActor
from application.core.device_registry import DeviceRegistry
from application.core.ui_update_bus import UiUpdateBus
from domain.enums.command import CommandKind, TaskLane
from domain.enums.device import DeviceState
from domain.models.phase1 import Phase1Request, Phase1Response
from domain.models.tasks import TaskSpec


@dataclass
class _FakeConnectService:
    response: Phase1Response

    def connect(self, request: Phase1Request) -> Phase1Response:
        return self.response


class _FakeInfoRepository:
    def build_client(self, **kwargs):
        return object()

    def read_info_kv(self, client):
        class Result:
            merged_kv = {
                "NET_MAC": "AA:BB:CC:DD:EE:FF",
                "SYS_MODELNAME_ID": "TRN-1000",
                "SYS_VERSION": "V1.2.3",
                "SYS_BOARDID": "BOARD-1",
                "SYS_MODULE_TYPE": "CAM",
                "SYS_MODULE_DETAIL": "4M",
                "SYS_PTZ_TYPE": "NONE",
                "SYS_ZOOMMODULE": "NO",
            }

        return Result()


class _FakeStatusRepository:
    def build_client(self, **kwargs):
        return object()

    def read_status_kv(self, client):
        class Result:
            merged_kv = {
                "SYS_CURRENTTIME": "2026/04/28 10:00:00",
                "SYS_BOARDTEMP": "44",
                "ETHTOOL": "1000M",
                "GRS_VENCBITRATE1": "4096",
                "GRS_VENCFRAME1": "30",
                "GIS_SENSOR1": "1",
                "GIS_ALARM1": "0",
            }

        return Result()


class _FakeControlRepository:
    def build_client(self, **kwargs):
        return object()

    def reboot(self, client):
        class Result:
            response_text = "SYS_REBOOT=1"

        return Result()


def _build_actor() -> tuple[DeviceRegistry, UiUpdateBus, DeviceActor]:
    registry = DeviceRegistry()
    registry.ensure_device("192.168.10.100")
    ui_bus = UiUpdateBus()

    response = Phase1Response(
        ok=True,
        base_url="https://192.168.10.100:443",
        root_path="/httpapi/",
        auth_scheme="digest",
        flavor="legacy",
        sys_version="V1.0.0",
        effective_username="admin",
        effective_password="123",
    )

    actor = DeviceActor(
        ip="192.168.10.100",
        registry=registry,
        ui_update_bus=ui_bus,
        connect_service=_FakeConnectService(response=response),
        info_repository=_FakeInfoRepository(),
        status_repository=_FakeStatusRepository(),
        control_repository=_FakeControlRepository(),
        verify_tls=False,
        default_timeout_sec=6.0,
    )
    registry.attach_actor("192.168.10.100", actor)
    return registry, ui_bus, actor


def test_device_actor_connect_creates_session_and_updates_snapshot() -> None:
    registry, ui_bus, actor = _build_actor()

    task = TaskSpec(
        task_id="connect-1",
        device_ip="192.168.10.100",
        command=CommandKind.CONNECT,
        lane=TaskLane.CONNECT,
        payload={"request": Phase1Request(ip="192.168.10.100")},
    )

    actor.execute_task(task)

    snapshot = registry.require_snapshot("192.168.10.100")
    assert actor.session is not None
    assert snapshot.connected is True
    assert snapshot.state == DeviceState.READY
    assert snapshot.sys_version == "V1.0.0"

    batch = ui_bus.flush()
    assert "192.168.10.100" in batch.dirty_device_ids


def test_device_actor_per_device_inflight_one() -> None:
    registry, _, actor = _build_actor()

    task = TaskSpec(
        task_id="connect-1",
        device_ip="192.168.10.100",
        command=CommandKind.CONNECT,
        lane=TaskLane.CONNECT,
        payload={"request": Phase1Request(ip="192.168.10.100")},
    )

    assert actor.can_accept_task(task) is True
    actor.begin_task(task)
    assert actor.can_accept_task(task) is False
    actor.finish_task(message="done")
    assert actor.can_accept_task(task) is True


def test_device_actor_info_status_control_flow() -> None:
    registry, _, actor = _build_actor()

    connect_task = TaskSpec(
        task_id="connect-1",
        device_ip="192.168.10.100",
        command=CommandKind.CONNECT,
        lane=TaskLane.CONNECT,
        payload={"request": Phase1Request(ip="192.168.10.100")},
    )
    actor.execute_task(connect_task)

    info_task = TaskSpec(
        task_id="info-1",
        device_ip="192.168.10.100",
        command=CommandKind.INFO_LOAD,
        lane=TaskLane.INFO,
        payload={},
    )
    actor.execute_task(info_task)

    status_task = TaskSpec(
        task_id="poll-1",
        device_ip="192.168.10.100",
        command=CommandKind.STATUS_POLL,
        lane=TaskLane.POLL_HOT,
        payload={"hot": True},
    )
    actor.execute_task(status_task)

    control_task = TaskSpec(
        task_id="control-1",
        device_ip="192.168.10.100",
        command=CommandKind.CONTROL,
        lane=TaskLane.CONTROL,
        payload={"handler": "reboot", "kwargs": {}},
    )
    actor.execute_task(control_task)

    snapshot = registry.require_snapshot("192.168.10.100")
    assert snapshot.info_loaded is True
    assert snapshot.model == "TRN-1000"
    assert snapshot.metrics.temp_text == "44"
    assert snapshot.command.last_message == "reboot completed"