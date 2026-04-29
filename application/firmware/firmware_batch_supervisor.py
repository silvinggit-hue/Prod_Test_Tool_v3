from __future__ import annotations

import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from config.firmware_settings import FirmwareSettings
from domain.enums.firmware import FirmwareFailureCode, FirmwareJobState
from domain.errors.app_error import AppError
from domain.models.firmware_models import FirmwareBatchSnapshot, FirmwareJob, FirmwareTarget
from infra.firmware.firmware_repository import FirmwareRepository, UploadResult

from application.firmware.firmware_job_registry import FirmwareJobRegistry


class FirmwareBatchSupervisor:
    RECONNECT_INTERVAL_SEC = 5.0
    RECONNECT_TIMEOUT_SEC = 180.0
    MAX_RECONNECT_ATTEMPTS = 36

    def __init__(
        self,
        *,
        repository: FirmwareRepository | None = None,
        settings: FirmwareSettings | None = None,
    ) -> None:
        self.repository = repository or FirmwareRepository()
        self.settings = settings or FirmwareSettings.load()
        self.registry = FirmwareJobRegistry()

        self._upload_parallelism = max(
            1,
            min(
                int(self.settings.upload_parallelism_default),
                int(self.settings.upload_parallelism_max),
            ),
        )

        self._runtime_lock = threading.RLock()
        self._runtime: dict[str, dict[str, Any]] = {}

        self._log_lock = threading.RLock()
        self._pending_logs: list[str] = []

        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._upload_executor = ThreadPoolExecutor(
            max_workers=self._upload_parallelism,
            thread_name_prefix="firmware-upload",
        )

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="FirmwareBatchSupervisor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()

        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        try:
            self._upload_executor.shutdown(wait=False, cancel_futures=False)
        except Exception:
            pass

    def wake(self) -> None:
        self._wake_event.set()

    def current_batch_id(self) -> str | None:
        return self.registry.current_batch_id()

    def list_jobs(self, batch_id: str | None = None) -> list[FirmwareJob]:
        return self.registry.list_jobs(batch_id)

    def failed_jobs(self, batch_id: str | None = None) -> list[FirmwareJob]:
        return self.registry.failed_jobs(batch_id)

    def current_batch_snapshot(self) -> FirmwareBatchSnapshot | None:
        snap = self.registry.batch_snapshot()
        if snap is None:
            return None
        return FirmwareBatchSnapshot(
            batch_id=snap.batch_id,
            total_count=snap.total_count,
            queued_count=snap.queued_count,
            upload_pending_count=snap.upload_pending_count,
            uploading_count=snap.uploading_count,
            rebooting_count=snap.rebooting_count,
            reconnecting_count=snap.reconnecting_count,
            verifying_count=0,
            success_count=snap.success_count,
            failed_count=snap.failed_count,
            started_at=snap.started_at,
            finished_at=snap.finished_at,
            upload_parallelism=self._upload_parallelism,
            upload_slots_in_use=snap.upload_slots_in_use,
            is_terminal=snap.is_terminal,
        )

    def drain_logs(self) -> list[str]:
        with self._log_lock:
            items = list(self._pending_logs)
            self._pending_logs.clear()
        return items

    def can_start_batch(self) -> bool:
        snap = self.current_batch_snapshot()
        return snap is None or snap.is_terminal

    def start_batch(
        self,
        *,
        targets: list[FirmwareTarget],
        firmware_path: str,
        verify_tls: bool = False,
    ) -> str:
        if not targets:
            raise AppError(kind="param", message="firmware target list is empty")
        if not firmware_path or not os.path.isfile(firmware_path):
            raise AppError(kind="param", message="firmware file not found", detail=firmware_path)
        if not self.can_start_batch():
            raise AppError(kind="busy", message="firmware batch is already running")

        batch_id = self.registry.create_batch(
            targets=targets,
            firmware_path=firmware_path,
            verify_tls=verify_tls,
            reconnect_interval_sec=self.RECONNECT_INTERVAL_SEC,
            reconnect_timeout_sec=self.RECONNECT_TIMEOUT_SEC,
        )
        self._append_log(f"펌웨어 작업 시작: {len(targets)}대 / {batch_id}")
        self.wake()
        return batch_id

    def retry_failed_only(
        self,
        *,
        firmware_path: str,
        verify_tls: bool = False,
    ) -> str:
        if not firmware_path or not os.path.isfile(firmware_path):
            raise AppError(kind="param", message="firmware file not found", detail=firmware_path)
        if not self.can_start_batch():
            raise AppError(kind="busy", message="firmware batch is already running")

        failed = self.failed_jobs()
        if not failed:
            raise AppError(kind="param", message="실패 장비가 없습니다.")

        batch_id = self.registry.create_retry_batch(
            failed_jobs=failed,
            firmware_path=firmware_path,
            verify_tls=verify_tls,
            reconnect_interval_sec=self.RECONNECT_INTERVAL_SEC,
            reconnect_timeout_sec=self.RECONNECT_TIMEOUT_SEC,
        )
        self._append_log(f"실패 장비 재시도 시작: {len(failed)}대 / {batch_id}")
        self.wake()
        return batch_id

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                progressed = False
                progressed = self._promote_queued_jobs() or progressed
                progressed = self._submit_uploads() or progressed
                progressed = self._collect_upload_results() or progressed
                progressed = self._process_reconnect_jobs() or progressed

                if not progressed:
                    self._wake_event.wait(timeout=max(0.05, self.settings.delay_scheduler_tick_ms / 1000.0))
                    self._wake_event.clear()
            except Exception as exc:
                self._append_log(f"펌웨어 supervisor 오류: {exc}")
                time.sleep(0.1)

    def _promote_queued_jobs(self) -> bool:
        progressed = False
        for job in self.registry.list_jobs():
            if job.state == FirmwareJobState.QUEUED:
                self.registry.update_job(
                    job.job_id,
                    state=FirmwareJobState.UPLOAD_PENDING,
                    started_at=time.time(),
                    last_log_message="업로드 준비",
                )
                progressed = True
        return progressed

    def _active_upload_count(self) -> int:
        with self._runtime_lock:
            count = 0
            for runtime in self._runtime.values():
                future = runtime.get("future")
                if isinstance(future, Future) and not future.done():
                    count += 1
            return count

    def _submit_uploads(self) -> bool:
        free_slots = self._upload_parallelism - self._active_upload_count()
        if free_slots <= 0:
            return False

        progressed = False
        pending_jobs = [job for job in self.registry.list_jobs() if job.state == FirmwareJobState.UPLOAD_PENDING]
        for job in pending_jobs[:free_slots]:
            with self._runtime_lock:
                runtime = self._runtime.setdefault(
                    job.job_id,
                    {
                        "future": None,
                        "disconnect_observed": False,
                    },
                )
                if isinstance(runtime.get("future"), Future):
                    continue
                future = self._upload_executor.submit(self._run_upload_job, job)
                runtime["future"] = future

            self.registry.update_job(
                job.job_id,
                state=FirmwareJobState.UPLOADING,
                last_log_message="업로드 중",
            )
            self._append_log(f"{job.target.ip} 업로드 시작")
            progressed = True

        return progressed

    def _collect_upload_results(self) -> bool:
        progressed = False

        with self._runtime_lock:
            items = list(self._runtime.items())

        for job_id, runtime in items:
            future = runtime.get("future")
            if not isinstance(future, Future) or not future.done():
                continue

            progressed = True
            try:
                result = future.result()
                runtime["future"] = None
                runtime["disconnect_observed"] = bool(result.get("disconnect_observed", False))

                now = time.time()
                self.registry.update_job(
                    job_id,
                    state=FirmwareJobState.REBOOTING,
                    reconnect_deadline=now + self.RECONNECT_TIMEOUT_SEC,
                    next_due_at=now + self.RECONNECT_INTERVAL_SEC,
                    reconnect_attempts_done=0,
                    last_log_message="재부팅 중",
                )
                job = self.registry.get_job(job_id)
                if job is not None:
                    self._append_log(f"{job.target.ip} 업로드 완료")
            except AppError as exc:
                self._mark_upload_failure(job_id, exc)
            except Exception as exc:
                self._mark_failed(
                    job_id,
                    failure_code=FirmwareFailureCode.UNEXPECTED_ERROR,
                    message="업로드 중 오류",
                    detail=str(exc),
                )

        return progressed

    def _process_reconnect_jobs(self) -> bool:
        progressed = False
        now = time.time()

        for job in self.registry.list_jobs():
            if job.state not in (FirmwareJobState.REBOOTING, FirmwareJobState.RECONNECTING):
                continue

            deadline = float(job.reconnect_deadline or 0.0)
            next_due_at = float(job.next_due_at or 0.0)

            if deadline and now > deadline:
                self._mark_failed(
                    job.job_id,
                    failure_code=FirmwareFailureCode.RECONNECT_TIMEOUT,
                    message="다시 연결 안 됨",
                    detail="180초 내 다시 연결되지 않음",
                )
                progressed = True
                continue

            if next_due_at and now < next_due_at:
                continue

            attempt = int(job.reconnect_attempts_done) + 1
            total_attempts = self.MAX_RECONNECT_ATTEMPTS

            probe = self.repository.try_probe_reconnect(
                target=job.target,
                verify_tls=job.verify_tls,
                timeout_sec=float(self.settings.probe_timeout_sec),
            )
            progressed = True

            with self._runtime_lock:
                runtime = self._runtime.setdefault(
                    job.job_id,
                    {
                        "future": None,
                        "disconnect_observed": False,
                    },
                )

            if probe.ok:
                if runtime.get("disconnect_observed", False):
                    self.registry.mark_success(job.job_id, message="장비가 다시 연결됨")
                    self._append_log(f"{job.target.ip} 완료")
                else:
                    self.registry.update_job(
                        job.job_id,
                        state=FirmwareJobState.RECONNECTING,
                        reconnect_attempts_done=attempt,
                        next_due_at=time.time() + self.RECONNECT_INTERVAL_SEC,
                        last_log_message=f"다시 연결 확인 중 ({attempt}/{total_attempts})",
                    )
                continue

            runtime["disconnect_observed"] = True
            self.registry.update_job(
                job.job_id,
                state=FirmwareJobState.RECONNECTING,
                reconnect_attempts_done=attempt,
                next_due_at=time.time() + self.RECONNECT_INTERVAL_SEC,
                last_log_message=f"다시 연결 확인 중 ({attempt}/{total_attempts})",
            )

        return progressed

    def _run_upload_job(self, job: FirmwareJob) -> dict[str, Any]:
        client = self.repository.build_client_from_target(
            job.target,
            timeout_sec=float(self.settings.upload_timeout_sec),
            verify_tls=job.verify_tls,
        )

        self.repository.write_remote_upgrade_userinfo(client, job.firmware_path)
        upload_result = self.repository.upload_firmware_progress_html(
            base_url=job.target.base_url,
            root_path=job.target.root_path,
            username=job.target.username,
            password=job.target.password,
            auth_scheme=job.target.auth_scheme,
            firmware_path=job.firmware_path,
            verify_tls=job.verify_tls,
            timeout_sec=float(self.settings.upload_timeout_sec),
            try_flipped_scheme=True,
        )

        return {
            "upload_result": upload_result,
            "disconnect_observed": self._detect_disconnect(upload_result),
        }

    @staticmethod
    def _detect_disconnect(result: UploadResult) -> bool:
        text = " ".join((result.body_tail or "").split()).lower()
        if "remotedisconnected" in text:
            return True
        if "remote end closed connection" in text:
            return True
        if "connection aborted" in text:
            return True
        if "connection reset" in text:
            return True
        return False

    def _mark_upload_failure(self, job_id: str, exc: AppError) -> None:
        kind = (exc.kind or "").strip().lower()
        if kind == "auth":
            code = FirmwareFailureCode.UPLOAD_AUTH_FAILED
            msg = "업로드 인증 실패"
        elif kind == "param":
            code = FirmwareFailureCode.UPLOAD_FILE_NOT_FOUND
            msg = "펌웨어 파일 오류"
        elif kind == "http":
            code = FirmwareFailureCode.UPLOAD_HTTP_FAILED
            msg = "업로드 통신 실패"
        elif kind in ("network", "timeout", "ssl"):
            code = FirmwareFailureCode.UPLOAD_NETWORK_FAILED
            msg = "업로드 연결 실패"
        else:
            code = FirmwareFailureCode.UNEXPECTED_ERROR
            msg = "업로드 중 오류"

        self._mark_failed(job_id, failure_code=code, message=msg, detail=exc.detail or exc.message)

    def _mark_failed(
        self,
        job_id: str,
        *,
        failure_code: FirmwareFailureCode,
        message: str,
        detail: str = "",
    ) -> None:
        job = self.registry.get_job(job_id)
        if job is not None:
            self._append_log(f"{job.target.ip} {message}")
        self.registry.mark_failed(
            job_id,
            failure_code=failure_code,
            failure_message=message,
            failure_detail=detail,
        )

    def _append_log(self, text: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {text}"
        with self._log_lock:
            self._pending_logs.append(line)