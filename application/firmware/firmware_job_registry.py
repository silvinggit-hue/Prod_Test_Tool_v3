from __future__ import annotations

import threading
import time
import uuid
from dataclasses import replace
from typing import Iterable

from domain.enums.firmware import FirmwareFailureCode, FirmwareJobState
from domain.models.firmware_models import FirmwareBatchSnapshot, FirmwareJob, FirmwareTarget


def _new_batch_id() -> str:
    return f"fw-batch-{uuid.uuid4().hex[:8]}"


def _new_job_id() -> str:
    return f"fw-job-{uuid.uuid4().hex[:10]}"


class FirmwareJobRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs_by_id: dict[str, FirmwareJob] = {}
        self._job_ids_by_batch: dict[str, list[str]] = {}
        self._current_batch_id: str | None = None

    def current_batch_id(self) -> str | None:
        with self._lock:
            return self._current_batch_id

    def set_current_batch_id(self, batch_id: str | None) -> None:
        with self._lock:
            self._current_batch_id = batch_id

    def create_batch(
        self,
        *,
        targets: Iterable[FirmwareTarget],
        firmware_path: str,
        verify_tls: bool,
        reconnect_interval_sec: float,
        reconnect_timeout_sec: float,
    ) -> str:
        now = time.time()
        batch_id = _new_batch_id()
        job_ids: list[str] = []

        with self._lock:
            for target in targets:
                job = FirmwareJob(
                    job_id=_new_job_id(),
                    batch_id=batch_id,
                    target=target,
                    firmware_path=firmware_path,
                    verify_tls=verify_tls,
                    state=FirmwareJobState.QUEUED,
                    reconnect_interval_sec=float(reconnect_interval_sec),
                    reconnect_timeout_sec=float(reconnect_timeout_sec),
                    verify_attempts_done=0,
                    verify_attempts_max=0,
                    started_at=None,
                    finished_at=None,
                    last_updated_at=now,
                    last_log_message="시작 대기",
                )
                self._jobs_by_id[job.job_id] = job
                job_ids.append(job.job_id)

            self._job_ids_by_batch[batch_id] = job_ids
            self._current_batch_id = batch_id

        return batch_id

    def create_retry_batch(
        self,
        *,
        failed_jobs: Iterable[FirmwareJob],
        firmware_path: str,
        verify_tls: bool,
        reconnect_interval_sec: float,
        reconnect_timeout_sec: float,
    ) -> str:
        now = time.time()
        batch_id = _new_batch_id()
        job_ids: list[str] = []

        with self._lock:
            for failed in failed_jobs:
                job = FirmwareJob(
                    job_id=_new_job_id(),
                    batch_id=batch_id,
                    target=failed.target,
                    firmware_path=firmware_path,
                    verify_tls=verify_tls,
                    state=FirmwareJobState.QUEUED,
                    reconnect_interval_sec=float(reconnect_interval_sec),
                    reconnect_timeout_sec=float(reconnect_timeout_sec),
                    verify_attempts_done=0,
                    verify_attempts_max=0,
                    started_at=None,
                    finished_at=None,
                    last_updated_at=now,
                    last_log_message="재시작 대기",
                    retry_of_job_id=failed.job_id,
                )
                self._jobs_by_id[job.job_id] = job
                job_ids.append(job.job_id)

            self._job_ids_by_batch[batch_id] = job_ids
            self._current_batch_id = batch_id

        return batch_id

    def get_job(self, job_id: str) -> FirmwareJob | None:
        with self._lock:
            return self._jobs_by_id.get(job_id)

    def list_jobs(self, batch_id: str | None = None) -> list[FirmwareJob]:
        with self._lock:
            use_batch = batch_id or self._current_batch_id
            if not use_batch:
                return []
            job_ids = self._job_ids_by_batch.get(use_batch, [])
            return [self._jobs_by_id[job_id] for job_id in job_ids if job_id in self._jobs_by_id]

    def failed_jobs(self, batch_id: str | None = None) -> list[FirmwareJob]:
        return [job for job in self.list_jobs(batch_id) if job.state == FirmwareJobState.FAILED]

    def update_job(self, job_id: str, **changes) -> FirmwareJob:
        with self._lock:
            current = self._jobs_by_id.get(job_id)
            if current is None:
                raise KeyError(f"firmware job not found: {job_id}")

            if "last_updated_at" not in changes:
                changes["last_updated_at"] = time.time()

            updated = replace(current, **changes)
            self._jobs_by_id[job_id] = updated
            return updated

    def mark_failed(
        self,
        job_id: str,
        *,
        failure_code: FirmwareFailureCode,
        failure_message: str,
        failure_detail: str = "",
    ) -> FirmwareJob:
        return self.update_job(
            job_id,
            state=FirmwareJobState.FAILED,
            finished_at=time.time(),
            failure_code=failure_code,
            failure_message=failure_message,
            failure_detail=failure_detail,
            last_log_message=failure_message,
        )

    def mark_success(self, job_id: str, *, message: str) -> FirmwareJob:
        return self.update_job(
            job_id,
            state=FirmwareJobState.SUCCESS,
            finished_at=time.time(),
            failure_code=None,
            failure_message="",
            failure_detail="",
            last_log_message=message,
        )

    def batch_snapshot(self, batch_id: str | None = None) -> FirmwareBatchSnapshot | None:
        jobs = self.list_jobs(batch_id)
        use_batch = batch_id or self.current_batch_id()
        if not use_batch:
            return None

        total = len(jobs)
        queued = sum(1 for job in jobs if job.state == FirmwareJobState.QUEUED)
        upload_pending = sum(1 for job in jobs if job.state == FirmwareJobState.UPLOAD_PENDING)
        uploading = sum(1 for job in jobs if job.state == FirmwareJobState.UPLOADING)
        rebooting = sum(1 for job in jobs if job.state == FirmwareJobState.REBOOTING)
        reconnecting = sum(1 for job in jobs if job.state == FirmwareJobState.RECONNECTING)
        success = sum(1 for job in jobs if job.state == FirmwareJobState.SUCCESS)
        failed = sum(1 for job in jobs if job.state == FirmwareJobState.FAILED)

        started_candidates = [job.started_at for job in jobs if job.started_at is not None]
        finished_candidates = [job.finished_at for job in jobs if job.finished_at is not None]

        is_terminal = total > 0 and all(
            job.state in (FirmwareJobState.SUCCESS, FirmwareJobState.FAILED)
            for job in jobs
        )

        return FirmwareBatchSnapshot(
            batch_id=use_batch,
            total_count=total,
            queued_count=queued,
            upload_pending_count=upload_pending,
            uploading_count=uploading,
            rebooting_count=rebooting,
            reconnecting_count=reconnecting,
            verifying_count=0,
            success_count=success,
            failed_count=failed,
            started_at=min(started_candidates) if started_candidates else None,
            finished_at=max(finished_candidates) if is_terminal and finished_candidates else None,
            upload_parallelism=0,
            upload_slots_in_use=uploading,
            is_terminal=is_terminal,
        )