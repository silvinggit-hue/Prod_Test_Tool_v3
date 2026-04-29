from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

from application.firmware.firmware_batch_supervisor import FirmwareBatchSupervisor
from domain.enums.firmware import FirmwareJobState
from domain.errors.app_error import AppError
from domain.models.firmware_models import FirmwareTarget
from ui.firmware.row_mapper import map_firmware_row
from ui.firmware.window import FirmwareWindow


class FirmwareWindowController:
    def __init__(
        self,
        *,
        window: FirmwareWindow,
        firmware_supervisor: FirmwareBatchSupervisor,
        checked_ips_provider: Callable[[], list[str]],
        selected_ips_provider: Callable[[], list[str]],
        focused_ip_provider: Callable[[], str | None],
        snapshot_provider: Callable[[str], object | None],
        refresh_main_callback: Callable[[], None] | None = None,
        enqueue_info_load_callback: Callable[[str], None] | None = None,
        on_log: Callable[[str], None] | None = None,
        on_result: Callable[[str], None] | None = None,
    ) -> None:
        self.window = window
        self.firmware_supervisor = firmware_supervisor
        self.checked_ips_provider = checked_ips_provider
        self.selected_ips_provider = selected_ips_provider
        self.focused_ip_provider = focused_ip_provider
        self.snapshot_provider = snapshot_provider
        self.refresh_main_callback = refresh_main_callback
        self.enqueue_info_load_callback = enqueue_info_load_callback
        self.on_log = on_log
        self.on_result = on_result

        self._ui_timer = QTimer(self.window)
        self._ui_timer.setInterval(200)
        self._ui_timer.timeout.connect(self._on_ui_tick)

        self._last_terminal_batch_id: str | None = None

    def bind(self) -> None:
        self.window.browse_button.clicked.connect(self._on_browse_clicked)
        self.window.start_button.clicked.connect(self._on_start_clicked)
        self.window.retry_failed_button.clicked.connect(self._on_retry_failed_clicked)
        self.window.close_requested.connect(self._on_close_requested)
        self.window.destroyed.connect(lambda *_: self.shutdown())

        self.firmware_supervisor.start()
        self._ui_timer.start()

        self._refresh_targets()
        self._refresh_table_and_summary()

    def shutdown(self) -> None:
        try:
            self._ui_timer.stop()
        except Exception:
            pass
        try:
            self.firmware_supervisor.stop()
        except Exception:
            pass

    def open_window(self) -> None:
        self._refresh_targets()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _append_log(self, text: str) -> None:
        if self.on_log is not None:
            self.on_log(text)

    def _append_result(self, text: str) -> None:
        if self.on_result is not None:
            self.on_result(text)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.warning(self.window, title, message)

    def _resolve_target_ips(self) -> list[str]:
        checked = list(self.checked_ips_provider() or [])
        if checked:
            return checked

        selected = list(self.selected_ips_provider() or [])
        if selected:
            return selected

        focused = self.focused_ip_provider()
        if focused:
            return [focused]

        return []

    def _build_targets(self) -> list[FirmwareTarget]:
        targets: list[FirmwareTarget] = []
        seen: set[str] = set()

        for ip in self._resolve_target_ips():
            if ip in seen:
                continue
            seen.add(ip)

            snapshot = self.snapshot_provider(ip)
            if snapshot is None:
                continue

            if not bool(getattr(snapshot, "connected", False)):
                continue

            base_url = str(getattr(snapshot, "base_url", "") or "").strip()
            root_path = str(getattr(snapshot, "root_path", "") or "").strip()
            auth_scheme = str(getattr(snapshot, "auth_scheme", "") or "").strip()
            username = str(getattr(snapshot, "username", "") or "").strip()
            password = str(getattr(snapshot, "effective_password", "") or "").strip()

            if not (base_url and root_path and auth_scheme and username and password):
                continue

            targets.append(
                FirmwareTarget(
                    ip=ip,
                    port=int(getattr(snapshot, "port", 0) or 0),
                    base_url=base_url,
                    root_path=root_path,
                    auth_scheme=auth_scheme,
                    username=username,
                    password=password,
                    model=str(getattr(snapshot, "model", "") or ""),
                    current_version_hint=str(getattr(snapshot, "sys_version", "") or "") or None,
                )
            )

        return targets

    def _refresh_targets(self) -> None:
        current_snapshot = self.firmware_supervisor.current_batch_snapshot()
        if current_snapshot is not None and not current_snapshot.is_terminal:
            self.window.set_target_count(current_snapshot.total_count)
            return
        self.window.set_target_count(len(self._build_targets()))

    def _refresh_table_and_summary(self) -> None:
        snapshot = self.firmware_supervisor.current_batch_snapshot()
        self.window.update_summary(snapshot)

        jobs = self.firmware_supervisor.list_jobs()
        rows = [map_firmware_row(job) for job in jobs]
        self.window.set_rows(rows)

    def _on_ui_tick(self) -> None:
        self._refresh_targets()
        self._refresh_table_and_summary()

        logs = self.firmware_supervisor.drain_logs()
        if logs:
            self.window.append_logs(logs)

        snapshot = self.firmware_supervisor.current_batch_snapshot()
        if snapshot is not None and snapshot.is_terminal and snapshot.batch_id != self._last_terminal_batch_id:
            self._last_terminal_batch_id = snapshot.batch_id
            self._append_result(
                f"펌웨어 완료: 전체 {snapshot.total_count}대 / 완료 {snapshot.success_count} / 실패 {snapshot.failed_count}"
            )
            self._refresh_main_after_finish()

    def _refresh_main_after_finish(self) -> None:
        jobs = self.firmware_supervisor.list_jobs()
        if self.enqueue_info_load_callback is not None:
            for job in jobs:
                self.enqueue_info_load_callback(job.target.ip)
        if self.refresh_main_callback is not None:
            self.refresh_main_callback()

    def _on_browse_clicked(self) -> None:
        path = self.window.choose_firmware_file()
        if path:
            self._append_log(f"펌웨어 파일 선택: {path}")

    def _on_start_clicked(self) -> None:
        targets = self._build_targets()
        if not targets:
            self._show_error("Firmware", "펌웨어 대상 장비가 없습니다.")
            return

        firmware_path = self.window.firmware_path()
        if not firmware_path:
            self._show_error("Firmware", "펌웨어 파일을 선택하세요.")
            return

        try:
            batch_id = self.firmware_supervisor.start_batch(
                targets=targets,
                firmware_path=firmware_path,
                verify_tls=False,
            )
        except AppError as exc:
            self._show_error("Firmware", exc.message)
            return

        self._last_terminal_batch_id = None
        self._append_log(f"펌웨어 작업 시작: {batch_id}")
        self._append_result(f"펌웨어 시작: {len(targets)}대")

    def _on_retry_failed_clicked(self) -> None:
        firmware_path = self.window.firmware_path()
        if not firmware_path:
            self._show_error("Firmware", "펌웨어 파일을 선택하세요.")
            return

        try:
            batch_id = self.firmware_supervisor.retry_failed_only(
                firmware_path=firmware_path,
                verify_tls=False,
            )
        except AppError as exc:
            self._show_error("Firmware", exc.message)
            return

        self._last_terminal_batch_id = None
        self._append_log(f"실패 장비 재시도 시작: {batch_id}")
        self._append_result("실패 장비 재시도 시작")

    def _on_close_requested(self) -> None:
        snapshot = self.firmware_supervisor.current_batch_snapshot()
        if snapshot is not None and not snapshot.is_terminal:
            if not self.window.confirm_hide_while_running():
                return

        self.window.hide()