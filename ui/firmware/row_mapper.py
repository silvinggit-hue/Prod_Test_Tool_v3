from __future__ import annotations

import time

from domain.enums.firmware import FirmwareFailureCode, FirmwareJobState
from domain.models.firmware_models import FirmwareJob, FirmwareRowModel


STATE_TEXT = {
    FirmwareJobState.QUEUED: "대기",
    FirmwareJobState.UPLOAD_PENDING: "업로드 준비",
    FirmwareJobState.UPLOADING: "업로드 중",
    FirmwareJobState.REBOOTING: "재부팅 중",
    FirmwareJobState.RECONNECTING: "다시 연결 확인 중",
    FirmwareJobState.SUCCESS: "완료",
    FirmwareJobState.FAILED: "실패",
    FirmwareJobState.VERIFYING: "확인 중",
}

FAILURE_TEXT = {
    FirmwareFailureCode.UPLOAD_AUTH_FAILED: "업로드 인증 실패",
    FirmwareFailureCode.UPLOAD_FILE_NOT_FOUND: "펌웨어 파일 오류",
    FirmwareFailureCode.UPLOAD_HTTP_FAILED: "업로드 통신 실패",
    FirmwareFailureCode.UPLOAD_NETWORK_FAILED: "업로드 연결 실패",
    FirmwareFailureCode.RECONNECT_TIMEOUT: "다시 연결 안 됨",
    FirmwareFailureCode.BEFORE_VERSION_UNAVAILABLE: "기존 버전 읽기 실패",
    FirmwareFailureCode.VERSION_READ_FAILED: "연결 확인 실패",
    FirmwareFailureCode.VERSION_UNCHANGED: "버전 변경 없음",
    FirmwareFailureCode.UNEXPECTED_ERROR: "예상치 못한 오류",
}


def _fmt_time(ts: float | None) -> str:
    if ts is None:
        return "-"
    try:
        return time.strftime("%H:%M:%S", time.localtime(ts))
    except Exception:
        return "-"


def _fmt_elapsed(started_at: float | None, finished_at: float | None) -> str:
    if started_at is None:
        return "-"
    end = finished_at if finished_at is not None else time.time()
    try:
        delta = max(0, int(end - started_at))
    except Exception:
        return "-"
    m, s = divmod(delta, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _progress_text(job: FirmwareJob) -> str:
    if job.state == FirmwareJobState.QUEUED:
        return "시작 대기"
    if job.state == FirmwareJobState.UPLOAD_PENDING:
        return "업로드 순서 대기 중"
    if job.state == FirmwareJobState.UPLOADING:
        return "파일을 장비에 올리는 중"
    if job.state == FirmwareJobState.REBOOTING:
        return "장비가 다시 시작되는 중"
    if job.state == FirmwareJobState.RECONNECTING:
        total = max(1, int(job.reconnect_timeout_sec // job.reconnect_interval_sec))
        attempt = max(1, int(job.reconnect_attempts_done))
        return f"다시 연결 확인 중 ({attempt}/{total})"
    if job.state == FirmwareJobState.SUCCESS:
        return "장비가 다시 연결됨"
    if job.state == FirmwareJobState.FAILED:
        return job.failure_message or "실패"
    return job.last_log_message or "-"


def _result_text(job: FirmwareJob) -> str:
    if job.state == FirmwareJobState.SUCCESS:
        return "완료"
    if job.state == FirmwareJobState.FAILED:
        return job.failure_message or "실패"
    return "-"


def map_firmware_row(job: FirmwareJob) -> FirmwareRowModel:
    return FirmwareRowModel(
        ip=job.target.ip,
        model=job.target.model or "-",
        state_text=STATE_TEXT.get(job.state, job.state.value),
        before_version="-",
        after_version="-",
        progress_text=_progress_text(job),
        result_text=_result_text(job),
        failure_code_text=FAILURE_TEXT.get(job.failure_code, "") if job.failure_code else "",
        updated_at_text=_fmt_time(job.last_updated_at),
        elapsed_text=_fmt_elapsed(job.started_at, job.finished_at),
        retry_candidate=(job.state == FirmwareJobState.FAILED),
    )