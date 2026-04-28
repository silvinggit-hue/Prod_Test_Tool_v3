from __future__ import annotations

from dataclasses import replace
from ipaddress import IPv4Address
from typing import Callable

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from application.services.discovery_service import (
    DiscoveryService,
    DiscoveryServiceRequest,
    DiscoveryServiceResult,
)
from application.services.reset_service import (
    BatchResetItem,
    BatchResetRequest,
    ResetService,
)
from application.services.setip_service import (
    BatchSetIpRequest,
    SetIpItem,
    SetIpService,
)
from ui.discovery.window import DiscoveryRow, DiscoveryWindow


class DiscoveryScanWorker(QObject):
    finished = pyqtSignal(object, object, bool)  # bind_ip, rows, stopped
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        service: DiscoveryService,
        request: DiscoveryServiceRequest,
    ) -> None:
        super().__init__()
        self._service = service
        self._request = request
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            result: DiscoveryServiceResult = self._service.discover(
                self._request,
                stop_requested=lambda: self._stop_requested,
            )

            rows = [
                DiscoveryRow(
                    selected=True,
                    selection_order=None,
                    ip=device.ip,
                    new_ip="",
                    model=device.model or "-",
                    firmware=device.firmware or "-",
                    mac=device.mac or "-",
                    mac12=device.mac12 or "-",
                    status="검색됨",
                    note="자동 발견",
                )
                for device in result.devices
            ]
            self.finished.emit(result.bind_ip, rows, result.stopped)
        except Exception as exc:
            self.failed.emit(str(exc))


class SetIpBatchWorker(QObject):
    finished = pyqtSignal(object)  # BatchSetIpResult
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        service: SetIpService,
        request: BatchSetIpRequest,
    ) -> None:
        super().__init__()
        self._service = service
        self._request = request
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            result = self._service.change_ip_batch(
                self._request,
                stop_requested=lambda: self._stop_requested,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class ResetBatchWorker(QObject):
    finished = pyqtSignal(object)  # BatchResetResult
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        service: ResetService,
        request: BatchResetRequest,
    ) -> None:
        super().__init__()
        self._service = service
        self._request = request
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            result = self._service.reset_batch(
                self._request,
                stop_requested=lambda: self._stop_requested,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class DiscoveryController:
    def __init__(
        self,
        *,
        window: DiscoveryWindow,
        on_rows_added: Callable[[list[dict]], None],
        on_log: Callable[[str], None] | None = None,
        discovery_service: DiscoveryService | None = None,
        setip_service: SetIpService | None = None,
        reset_service: ResetService | None = None,
    ) -> None:
        self.window = window
        self.on_rows_added = on_rows_added
        self.on_log = on_log

        self.discovery_service = discovery_service or DiscoveryService()
        self.setip_service = setip_service or SetIpService()
        self.reset_service = reset_service or ResetService()

        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._busy_kind: str | None = None

        self._selection_order_counter = 0
        self._prev_selected_map: dict[str, bool] = {}

    # ---------------------------------------------------------
    # bind
    # ---------------------------------------------------------
    def bind(self) -> None:
        self.window.scan_requested.connect(self._on_scan_requested)
        self.window.stop_requested.connect(self._on_stop_requested)

        self.window.auto_fill_ip_requested.connect(self._on_auto_fill_ip_requested)
        self.window.setip_requested.connect(self._on_setip_requested)
        self.window.reset_requested.connect(self._on_reset_requested)

        self.window.add_selected_requested.connect(self._on_add_selected_requested)
        self.window.add_all_requested.connect(self._on_add_all_requested)

        self.window.select_all_toggled.connect(self._on_select_all_toggled)
        self.window.table_model.rows_changed.connect(self._on_rows_changed)

    # ---------------------------------------------------------
    # log / dialogs
    # ---------------------------------------------------------
    def _log(self, text: str) -> None:
        if self.on_log is not None:
            self.on_log(text)

    def _info(self, title: str, message: str) -> None:
        QMessageBox.information(self.window, title, message)

    def _warn(self, title: str, message: str) -> None:
        QMessageBox.warning(self.window, title, message)

    def _confirm(self, title: str, message: str) -> bool:
        return QMessageBox.question(
            self.window,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

    # ---------------------------------------------------------
    # busy helpers
    # ---------------------------------------------------------
    def _set_busy(self, kind: str | None) -> None:
        self._busy_kind = kind
        scanning = kind == "scan"
        admin_busy = kind in {"setip", "reset"}

        self.window.set_scanning(scanning)
        self.window.set_admin_busy(admin_busy)

    def _cleanup_worker(self) -> None:
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None
        self._set_busy(None)

    # ---------------------------------------------------------
    # row helpers
    # ---------------------------------------------------------
    @staticmethod
    def _sort_key_ip(ip: str):
        try:
            return (0, int(IPv4Address(ip)))
        except Exception:
            return (1, ip)

    @staticmethod
    def _sort_key_mac(row: DiscoveryRow):
        return ((row.mac12 or "").strip().upper(), DiscoveryController._sort_key_ip(row.ip))

    def _rows(self) -> list[DiscoveryRow]:
        return self.window.all_results()

    def _selected_rows(self) -> list[DiscoveryRow]:
        return self.window.selected_results()

    def _apply_rows(self, rows: list[DiscoveryRow]) -> None:
        self.window.update_rows(rows)

    def _sync_previous_selected_map(self, rows: list[DiscoveryRow]) -> None:
        self._prev_selected_map = {
            (row.mac12 or "").strip().upper(): bool(row.selected)
            for row in rows
        }

    def _recompact_selection_order(self, rows: list[DiscoveryRow]) -> list[DiscoveryRow]:
        selected = [row for row in rows if row.selected]
        unselected = [row for row in rows if not row.selected]

        if self.window.order_mode() == "mac":
            ordered_selected = sorted(selected, key=self._sort_key_mac)
        else:
            ordered_selected = sorted(
                selected,
                key=lambda row: (
                    999999 if row.selection_order is None else int(row.selection_order),
                    self._sort_key_mac(row),
                ),
            )

        order_map: dict[str, int] = {}
        for seq, row in enumerate(ordered_selected, start=1):
            order_map[(row.mac12 or "").strip().upper()] = seq

        out: list[DiscoveryRow] = []
        for row in rows:
            mac12 = (row.mac12 or "").strip().upper()
            if row.selected:
                out.append(replace(row, selection_order=order_map.get(mac12)))
            else:
                out.append(replace(row, selection_order=None))
        return out

    def _apply_mac_order(self, rows: list[DiscoveryRow]) -> list[DiscoveryRow]:
        selected = sorted([row for row in rows if row.selected], key=self._sort_key_mac)
        mac_to_order = {
            (row.mac12 or "").strip().upper(): idx
            for idx, row in enumerate(selected, start=1)
        }

        out: list[DiscoveryRow] = []
        for row in rows:
            mac12 = (row.mac12 or "").strip().upper()
            if row.selected:
                out.append(replace(row, selection_order=mac_to_order.get(mac12)))
            else:
                out.append(replace(row, selection_order=None))
        return out

    def _ordered_selected_rows(self, rows: list[DiscoveryRow]) -> list[DiscoveryRow]:
        selected = [row for row in rows if row.selected]

        if self.window.order_mode() == "selection":
            return sorted(
                selected,
                key=lambda row: (
                    999999 if row.selection_order is None else int(row.selection_order),
                    self._sort_key_mac(row),
                ),
            )

        return sorted(selected, key=self._sort_key_mac)

    # ---------------------------------------------------------
    # selection flow
    # ---------------------------------------------------------
    def _on_rows_changed(self) -> None:
        rows = self._rows()
        changed = False

        current_selected_map = {
            (row.mac12 or "").strip().upper(): bool(row.selected)
            for row in rows
        }

        updated_rows = rows[:]

        for idx, row in enumerate(updated_rows):
            mac12 = (row.mac12 or "").strip().upper()
            prev_selected = self._prev_selected_map.get(mac12, False)

            if row.selected and not prev_selected:
                self._selection_order_counter += 1
                updated_rows[idx] = replace(row, selection_order=self._selection_order_counter)
                changed = True

            elif (not row.selected) and prev_selected:
                updated_rows[idx] = replace(row, selection_order=None)
                changed = True

        if self.window.order_mode() == "mac":
            recomputed = self._apply_mac_order(updated_rows)
        else:
            recomputed = self._recompact_selection_order(updated_rows)

        if recomputed != rows:
            self._apply_rows(recomputed)
            self._sync_previous_selected_map(recomputed)
            return

        self._sync_previous_selected_map(current_selected_map_to_rows(rows))

    def _on_select_all_toggled(self, selected: bool) -> None:
        rows = self._rows()
        if not rows:
            return

        if selected:
            rows = self._apply_mac_order(rows)
        else:
            rows = [replace(row, selection_order=None) for row in rows]

        self._apply_rows(rows)
        self._sync_previous_selected_map(rows)

    # ---------------------------------------------------------
    # discovery
    # ---------------------------------------------------------
    def _on_scan_requested(self) -> None:
        if self._thread is not None:
            self._warn("장비 검색", "이미 검색이 진행 중입니다.")
            return

        self.window.clear_results()
        self.window.set_status_text("장비 검색 중...")
        self._set_busy("scan")

        request = DiscoveryServiceRequest(
            bind_ip=None,
            mask_bits=24,
            port=64988,
            seconds=4.0,
            repeat=4,
            interval=0.12,
            ignore_self=True,
            min_wait=0.25,
            quiet_exit=0.18,
        )

        self._thread = QThread()
        self._worker = DiscoveryScanWorker(
            service=self.discovery_service,
            request=request,
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)

        self._thread.start()
        self._log("장비 검색 시작")

    def _on_stop_requested(self) -> None:
        if self._worker is None:
            return
        stop = getattr(self._worker, "stop", None)
        if callable(stop):
            stop()
            self.window.set_status_text("중지 요청됨...")
            self._log("검색 중지 요청")

    def _on_scan_finished(self, bind_ip: str | None, rows: list[DiscoveryRow], stopped: bool) -> None:
        self.window.set_bind_ip(bind_ip)

        # 기본: 검색 결과는 전부 체크 상태로 보여주되,
        # 순번은 MAC 오름차순 기준으로 매긴다.
        normalized = rows[:]
        normalized = self._apply_mac_order(normalized)

        self.window.set_results(normalized)
        self._sync_previous_selected_map(normalized)

        if bind_ip and not self.window.base_ip_text():
            parts = (bind_ip or "").split(".")
            if len(parts) == 4:
                self.window.set_base_ip(f"{parts[0]}.{parts[1]}.{parts[2]}.100")

        if stopped:
            self.window.set_status_text("중지됨")
            self._log(f"검색 중지: {len(rows)}대 확인")
        else:
            self.window.set_status_text("검색 완료")
            self._log(f"검색 완료: {len(rows)}대 발견")

    def _on_scan_failed(self, message: str) -> None:
        self.window.set_status_text("검색 실패")
        self._warn("장비 검색", f"검색 중 오류가 발생했습니다.\n{message}")
        self._log(f"검색 실패: {message}")

    # ---------------------------------------------------------
    # auto fill
    # ---------------------------------------------------------
    def _on_auto_fill_ip_requested(self) -> None:
        rows = self._rows()
        selected_rows = [row for row in rows if row.selected]
        if not selected_rows:
            self._warn("IP 자동 채우기", "선택된 장비가 없습니다.")
            return

        base_ip_text = self.window.base_ip_text()
        if not self.window.is_valid_ipv4(base_ip_text):
            self._warn("IP 자동 채우기", "시작 IP를 올바르게 입력하세요.")
            return

        ordered = self._ordered_selected_rows(rows)
        base_int = int(IPv4Address(base_ip_text))

        ip_map: dict[str, str] = {}
        for offset, row in enumerate(ordered):
            ip_map[(row.mac12 or "").strip().upper()] = str(IPv4Address(base_int + offset))

        updated: list[DiscoveryRow] = []
        for row in rows:
            mac12 = (row.mac12 or "").strip().upper()
            if row.selected:
                updated.append(
                    replace(
                        row,
                        new_ip=ip_map.get(mac12, row.new_ip),
                        status="변경 준비",
                    )
                )
            else:
                updated.append(row)

        if self.window.order_mode() == "mac":
            updated = self._apply_mac_order(updated)
        else:
            updated = self._recompact_selection_order(updated)

        self._apply_rows(updated)
        self._sync_previous_selected_map(updated)
        self.window.set_status_text("IP 자동 채우기 완료")
        self._log(f"IP 자동 채우기 완료: {len(ordered)}대")

    # ---------------------------------------------------------
    # setip
    # ---------------------------------------------------------
    def _on_setip_requested(self) -> None:
        if self._thread is not None:
            self._warn("IP 변경", "다른 작업이 진행 중입니다.")
            return

        rows = self._rows()
        ordered = self._ordered_selected_rows(rows)
        if not ordered:
            self._warn("IP 변경", "선택된 장비가 없습니다.")
            return

        for row in ordered:
            if not self.window.is_valid_ipv4(row.new_ip):
                self._warn("IP 변경", f"변경할 IP가 올바르지 않습니다.\n대상: {row.ip}")
                return

        if not self._confirm("IP 변경", f"선택된 {len(ordered)}대의 IP를 변경하시겠습니까?"):
            return

        request = BatchSetIpRequest(
            items=[
                SetIpItem(
                    mac12=row.mac12,
                    new_ip=row.new_ip,
                    gw=None,
                    netmask=None,
                )
                for row in ordered
            ],
            bind_ip=None,
            mask_bits=24,
            port=64988,
            retries=2,
            ack_wait_sec=1.0,
            confirm_announce_sec=0.8,
        )

        self._thread = QThread()
        self._worker = SetIpBatchWorker(
            service=self.setip_service,
            request=request,
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_setip_finished)
        self._worker.failed.connect(self._on_setip_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)

        # 상태를 먼저 "변경 중"으로
        busy_rows: list[DiscoveryRow] = []
        target_mac12 = {(row.mac12 or "").strip().upper() for row in ordered}
        for row in rows:
            mac12 = (row.mac12 or "").strip().upper()
            if mac12 in target_mac12:
                busy_rows.append(replace(row, status="변경 중"))
            else:
                busy_rows.append(row)
        self._apply_rows(busy_rows)

        self.window.set_status_text("IP 변경 실행 중...")
        self._set_busy("setip")
        self._thread.start()
        self._log(f"IP 변경 실행: {len(ordered)}대")

    def _on_setip_finished(self, result) -> None:
        rows = self._rows()
        updated: list[DiscoveryRow] = []

        raw_results = getattr(result, "results", {}) or {}

        ok_count = 0
        fail_count = 0

        for row in rows:
            mac12 = (row.mac12 or "").strip().upper()
            item = raw_results.get(mac12)
            if item is None:
                updated.append(row)
                continue

            if bool(getattr(item, "ok", False)):
                ok_count += 1
                new_ip = (getattr(item, "announced_ip", None) or row.new_ip or row.ip).strip()
                updated.append(
                    replace(
                        row,
                        ip=new_ip,
                        status="IP 변경 완료",
                        note="IP 변경 성공",
                    )
                )
            else:
                fail_count += 1
                error_message = (getattr(item, "error_message", "") or "").strip() or "실패"
                updated.append(
                    replace(
                        row,
                        status="IP 변경 실패",
                        note=error_message,
                    )
                )

        self._apply_rows(updated)
        self._sync_previous_selected_map(updated)

        self.window.set_status_text("IP 변경 완료")
        self._log(f"IP 변경 완료: 성공 {ok_count}대 / 실패 {fail_count}대")

    def _on_setip_failed(self, message: str) -> None:
        self.window.set_status_text("IP 변경 실패")
        self._warn("IP 변경", f"IP 변경 중 오류가 발생했습니다.\n{message}")
        self._log(f"IP 변경 실패: {message}")

    # ---------------------------------------------------------
    # reset
    # ---------------------------------------------------------
    def _on_reset_requested(self) -> None:
        if self._thread is not None:
            self._warn("선택 초기화", "다른 작업이 진행 중입니다.")
            return

        rows = self._rows()
        selected = [row for row in rows if row.selected]
        if not selected:
            self._warn("선택 초기화", "선택된 장비가 없습니다.")
            return

        if not self._confirm("선택 초기화", f"선택된 {len(selected)}대를 초기화하시겠습니까?"):
            return

        request = BatchResetRequest(
            items=[
                BatchResetItem(
                    mac12=row.mac12,
                    device_ip_hint=row.ip,
                )
                for row in selected
            ],
            bind_ip=None,
            mask_bits=24,
            port=64988,
            scan_seconds=2.0,
            seed_sweep=120,
            write_seq=3,
            write_gap=0.01,
            ack_wait_sec=1.0,
            ignore_self=True,
            bf96_step=1,
            ack_any_ip=False,
        )

        self._thread = QThread()
        self._worker = ResetBatchWorker(
            service=self.reset_service,
            request=request,
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_reset_finished)
        self._worker.failed.connect(self._on_reset_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)

        target_mac12 = {(row.mac12 or "").strip().upper() for row in selected}
        busy_rows: list[DiscoveryRow] = []
        for row in rows:
            mac12 = (row.mac12 or "").strip().upper()
            if mac12 in target_mac12:
                busy_rows.append(replace(row, status="초기화 중"))
            else:
                busy_rows.append(row)
        self._apply_rows(busy_rows)

        self.window.set_status_text("선택 초기화 실행 중...")
        self._set_busy("reset")
        self._thread.start()
        self._log(f"선택 초기화 실행: {len(selected)}대")

    def _on_reset_finished(self, result) -> None:
        rows = self._rows()
        updated: list[DiscoveryRow] = []

        raw_results = getattr(result, "results", {}) or {}
        ok_count = 0
        fail_count = 0

        for row in rows:
            mac12 = (row.mac12 or "").strip().upper()
            item = raw_results.get(mac12)
            if item is None:
                updated.append(row)
                continue

            if bool(getattr(item, "ok", False)):
                ok_count += 1
                updated.append(
                    replace(
                        row,
                        status="초기화 완료",
                        note="초기화 성공",
                    )
                )
            else:
                fail_count += 1
                error_message = (getattr(item, "error_message", "") or "").strip() or "실패"
                updated.append(
                    replace(
                        row,
                        status="초기화 실패",
                        note=error_message,
                    )
                )

        self._apply_rows(updated)
        self._sync_previous_selected_map(updated)

        self.window.set_status_text("선택 초기화 완료")
        self._log(f"선택 초기화 완료: 성공 {ok_count}대 / 실패 {fail_count}대")

    def _on_reset_failed(self, message: str) -> None:
        self.window.set_status_text("선택 초기화 실패")
        self._warn("선택 초기화", f"초기화 중 오류가 발생했습니다.\n{message}")
        self._log(f"선택 초기화 실패: {message}")

    # ---------------------------------------------------------
    # main reflect
    # ---------------------------------------------------------
    def _to_main_rows(self, rows: list[DiscoveryRow]) -> list[dict]:
        out: list[dict] = []
        seen_ips: set[str] = set()

        for row in rows:
            ip = (row.ip or "").strip()
            if not ip or ip in seen_ips:
                continue
            seen_ips.add(ip)

            out.append(
                {
                    "ip": ip,
                    "port": 0,
                    "note": "discovery",
                    "mac": row.mac,
                    "mac12": row.mac12,
                    "model": row.model,
                    "firmware": row.firmware,
                    "lens": "-",
                    "probe": None,
                }
            )
        return out

    def _on_add_selected_requested(self) -> None:
        rows = self.window.selected_results()
        if not rows:
            self._warn("메인 반영", "선택된 장비가 없습니다.")
            return

        self.on_rows_added(self._to_main_rows(rows))
        self._log(f"선택 항목 추가: {len(rows)}대")

    def _on_add_all_requested(self) -> None:
        rows = self.window.all_results()
        if not rows:
            self._warn("메인 반영", "추가할 장비가 없습니다.")
            return

        self.on_rows_added(self._to_main_rows(rows))
        self._log(f"전체 추가: {len(rows)}대")


def current_selected_map_to_rows(rows: list[DiscoveryRow]) -> dict[str, bool]:
    return {
        (row.mac12 or "").strip().upper(): bool(row.selected)
        for row in rows
    }