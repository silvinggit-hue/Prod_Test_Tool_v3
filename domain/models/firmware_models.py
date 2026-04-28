from __future__ import annotations

from dataclasses import dataclass

from domain.enums.firmware import FirmwareFailureCode, FirmwareJobState


@dataclass(frozen=True)
class FirmwareTarget:
    ip: str
    port: int
    base_url: str
    root_path: str
    auth_scheme: str
    username: str
    password: str
    model: str = ""
    current_version_hint: str | None = None


@dataclass(frozen=True)
class FirmwareJobResult:
    ok: bool
    job_id: str
    batch_id: str
    ip: str

    before_version: str | None = None
    after_version: str | None = None

    final_state: FirmwareJobState = FirmwareJobState.FAILED
    failure_code: FirmwareFailureCode | None = None
    message: str = ""
    detail: str = ""

    started_at: float | None = None
    finished_at: float | None = None


@dataclass(frozen=True)
class FirmwareJob:
    job_id: str
    batch_id: str
    target: FirmwareTarget

    firmware_path: str
    verify_tls: bool

    state: FirmwareJobState = FirmwareJobState.QUEUED

    before_version: str | None = None
    after_version: str | None = None

    verify_attempts_done: int = 0
    verify_attempts_max: int = 3

    reconnect_attempts_done: int = 0
    reconnect_interval_sec: float = 2.0
    reconnect_timeout_sec: float = 120.0

    reboot_wait_sec: float = 40.0
    reboot_wait_until: float | None = None
    reconnect_deadline: float | None = None
    next_due_at: float | None = None

    started_at: float | None = None
    finished_at: float | None = None
    last_updated_at: float | None = None

    failure_code: FirmwareFailureCode | None = None
    failure_message: str = ""
    failure_detail: str = ""

    last_log_message: str = ""
    retry_of_job_id: str | None = None


@dataclass(frozen=True)
class FirmwareBatchSnapshot:
    batch_id: str

    total_count: int
    queued_count: int
    upload_pending_count: int
    uploading_count: int
    rebooting_count: int
    reconnecting_count: int
    verifying_count: int
    success_count: int
    failed_count: int

    started_at: float | None = None
    finished_at: float | None = None

    upload_parallelism: int = 16
    upload_slots_in_use: int = 0

    is_terminal: bool = False


@dataclass(frozen=True)
class FirmwareRowModel:
    ip: str
    model: str
    state_text: str

    before_version: str
    after_version: str

    progress_text: str
    result_text: str
    failure_code_text: str

    updated_at_text: str
    elapsed_text: str

    retry_candidate: bool