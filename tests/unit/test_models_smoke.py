from __future__ import annotations

from domain.enums.app_mode import AppMode
from domain.enums.device import DeviceFlavor, DeviceState
from domain.enums.firmware import FirmwareFailureCode, FirmwareJobState
from domain.models.app_snapshot import AppSnapshot
from domain.models.device_snapshot import DeviceSnapshot
from domain.models.firmware_models import (
    FirmwareBatchSnapshot,
    FirmwareJob,
    FirmwareJobResult,
    FirmwareTarget,
)
from domain.models.phase1 import Phase1Request, Phase1Response
from domain.models.tasks import TaskSpec
from domain.enums.command import CommandKind, TaskLane


def test_device_snapshot_smoke() -> None:
    snapshot = DeviceSnapshot(
        ip="192.168.10.100",
        state=DeviceState.READY,
        connected=True,
        model="TRN-1000",
        firmware="V1.0.0",
        flavor=DeviceFlavor.LEGACY,
    )

    assert snapshot.ip == "192.168.10.100"
    assert snapshot.state == DeviceState.READY
    assert snapshot.connected is True
    assert snapshot.model == "TRN-1000"


def test_app_snapshot_smoke() -> None:
    app = AppSnapshot(
        total_count=3,
        connected_count=2,
        selected_count=1,
        app_mode=AppMode.NORMAL,
    )

    assert app.total_count == 3
    assert app.connected_count == 2
    assert app.app_mode == AppMode.NORMAL


def test_firmware_models_smoke() -> None:
    target = FirmwareTarget(
        ip="192.168.10.101",
        port=443,
        base_url="https://192.168.10.101:443",
        root_path="/httpapi/",
        auth_scheme="digest",
        username="admin",
        password="!camera1108",
        model="TRN-2000",
        current_version_hint="V1.0.0",
    )

    job = FirmwareJob(
        job_id="job-1",
        batch_id="batch-1",
        target=target,
        firmware_path="C:/fw/progress.html",
        verify_tls=False,
        state=FirmwareJobState.UPLOAD_PENDING,
    )

    result = FirmwareJobResult(
        ok=False,
        job_id="job-1",
        batch_id="batch-1",
        ip=target.ip,
        final_state=FirmwareJobState.FAILED,
        failure_code=FirmwareFailureCode.VERSION_UNCHANGED,
        message="version unchanged",
    )

    batch = FirmwareBatchSnapshot(
        batch_id="batch-1",
        total_count=1,
        queued_count=0,
        upload_pending_count=1,
        uploading_count=0,
        rebooting_count=0,
        reconnecting_count=0,
        verifying_count=0,
        success_count=0,
        failed_count=0,
    )

    assert job.target.ip == "192.168.10.101"
    assert job.state == FirmwareJobState.UPLOAD_PENDING
    assert result.failure_code == FirmwareFailureCode.VERSION_UNCHANGED
    assert batch.total_count == 1


def test_phase1_models_smoke() -> None:
    req = Phase1Request(ip="192.168.10.100")
    resp = Phase1Response(
        ok=True,
        base_url="https://192.168.10.100:443",
        root_path="/httpapi/",
        auth_scheme="digest",
        flavor="legacy",
        sys_version="V1.0.0",
        effective_username="admin",
        effective_password="!camera1108",
    )

    assert req.username == "admin"
    assert req.password == "123"
    assert req.sec3_username == "TruenTest"
    assert resp.ok is True
    assert resp.sys_version == "V1.0.0"


def test_task_spec_smoke() -> None:
    task = TaskSpec(
        task_id="task-1",
        device_ip="192.168.10.100",
        command=CommandKind.CONNECT,
        lane=TaskLane.CONNECT,
        priority=10,
    )

    assert task.task_id == "task-1"
    assert task.command == CommandKind.CONNECT
    assert task.lane == TaskLane.CONNECT