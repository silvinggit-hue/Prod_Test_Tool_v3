from __future__ import annotations

import ipaddress
from contextlib import contextmanager

from PyQt5.QtCore import QItemSelection, QItemSelectionModel, QModelIndex, QSignalBlocker, QTimer
from PyQt5.QtWidgets import QMessageBox

from application.core.app_supervisor import AppSupervisor
from domain.enums.device import DeviceFlavor
from domain.models.phase1 import Phase1Request
from ui.add_device.controller import AddDeviceController
from ui.add_device.window import AddDeviceWindow
from ui.discovery.controller import DiscoveryController
from ui.discovery.window import DiscoveryWindow
from ui.main.window import MainWindow


class MainWindowController:

    @staticmethod
    def _sort_snapshots_asc_by_ip(snapshots):
        def sort_key(snapshot):
            ip = getattr(snapshot, "ip", "")
            try:
                return (0, int(ipaddress.ip_address(ip)))
            except Exception:
                return (1, ip)

        return sorted(snapshots, key=sort_key)

    def __init__(self, *, window: MainWindow, supervisor: AppSupervisor) -> None:
        self.window = window
        self.supervisor = supervisor
        self._selection_sync_enabled = True

        self._add_device_window: AddDeviceWindow | None = None
        self._add_device_controller: AddDeviceController | None = None
        self._discovery_window: DiscoveryWindow | None = None
        self._discovery_controller: DiscoveryController | None = None
        self._ui_timer: QTimer | None = None

    def bind(self) -> None:
        self.window.add_device_action.triggered.connect(self._on_open_add_device_window)
        self.window.discovery_action.triggered.connect(self._on_open_discovery_window)
        self.window.clear_selection_action.triggered.connect(self._on_clear_selection_clicked)

        self.window.connect_panel.connect_selected_button.clicked.connect(self._on_connect_selected_clicked)
        self.window.info_panel.load_info_button.clicked.connect(self._on_load_info_clicked)
        self.window.status_panel.poll_status_button.clicked.connect(self._on_poll_status_clicked)
        self.window.control_panel.reboot_button.clicked.connect(self._on_reboot_clicked)
        self.window.control_panel.sync_rtc_button.clicked.connect(self._on_sync_rtc_clicked)

        self.window.device_table.selectionModel().selectionChanged.connect(self._on_table_selection_changed)
        self.window.device_table.doubleClicked.connect(self._on_table_double_clicked)
        self.window.device_table_model.selection_toggled.connect(self._on_checkbox_toggled)
        self.window.device_table.horizontalHeader().sectionClicked.connect(self._on_header_section_clicked)

        self._ui_timer = QTimer(self.window)
        self._ui_timer.setInterval(100)
        self._ui_timer.timeout.connect(self._on_ui_refresh_tick)
        self._ui_timer.start()

        self.refresh_all()

    def _on_ui_refresh_tick(self) -> None:
        batch = self.supervisor.flush_ui_updates()
        if batch.has_changes:
            self.refresh_all()

    def refresh_all(self) -> None:
        selected_ips = self._selected_ips_from_table()
        focused_ip = self._focused_ip_from_table()

        snapshots = self.supervisor.registry.list_snapshots()
        snapshots = self._sort_snapshots_asc_by_ip(snapshots)
        self.window.device_table_model.set_snapshots(snapshots)
        self.window.resize_columns_to_contents()
        self._restore_selection(selected_ips, focused_ip)

        app_snapshot = self.supervisor.get_app_snapshot()
        self.window.main_status_bar.update_from_snapshot(app_snapshot)

        focus_snapshot = None
        if focused_ip:
            focus_snapshot = self.supervisor.get_snapshot(focused_ip)
        if focus_snapshot is None and selected_ips:
            focus_snapshot = self.supervisor.get_snapshot(selected_ips[0])

        self.window.info_panel.set_snapshot(focus_snapshot)
        self.window.status_panel.set_snapshot(focus_snapshot)

    def _append_log(self, text: str) -> None:
        self.window.log_panel.append_line(text)

    def _append_result(self, text: str) -> None:
        self.window.result_panel.append_text(text)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.warning(self.window, title, message)

    def _actor_for_ip(self, ip: str):
        actors = getattr(self.supervisor.registry, "actors_by_ip", None)
        if isinstance(actors, dict):
            return actors.get(ip)
        return None

    def _build_phase1_request(self, ip: str) -> Phase1Request:
        connect_panel = self.window.connect_panel

        entered_username = connect_panel.entered_username().strip() or "admin"
        entered_password = connect_panel.entered_password().strip() or "1234"
        is_factory_reset = connect_panel.is_factory_reset_password()

        if is_factory_reset:
            target_password = connect_panel.target_password()
        else:
            target_password = entered_password

        return Phase1Request(
            ip=ip,
            port=0,
            username=entered_username,
            password=entered_password,
            password_candidates=("1234", "admin", "123", "!camera1108", "!Camera1108"),
            target_password=target_password,
            verify_tls=False,
            sec3_username="TruenTest",
            sec3_password="!Camera1108",
            allowed_ip=self.supervisor.settings.allowed_ip,
        )

    def _selected_ips_from_table(self) -> list[str]:
        model = self.window.device_table_model
        selection_model = self.window.device_table.selectionModel()
        if selection_model is None:
            return []

        rows = selection_model.selectedRows()
        ips: list[str] = []
        for model_index in rows:
            snapshot = model.snapshot_at_row(model_index.row())
            if snapshot is not None:
                ips.append(snapshot.ip)
        return ips

    def _focused_ip_from_table(self) -> str | None:
        model_index = self.window.device_table.currentIndex()
        if not model_index.isValid():
            return None
        snapshot = self.window.device_table_model.snapshot_at_row(model_index.row())
        return snapshot.ip if snapshot is not None else None

    @contextmanager
    def _selection_sync_blocked(self):
        self._selection_sync_enabled = False
        try:
            yield
        finally:
            self._selection_sync_enabled = True

    def _restore_selection(self, selected_ips: list[str], focused_ip: str | None) -> None:
        selection_model = self.window.device_table.selectionModel()
        if selection_model is None:
            return

        with self._selection_sync_blocked():
            blocker = QSignalBlocker(selection_model)
            try:
                selection_model.clearSelection()

                for ip in selected_ips:
                    row = self.window.device_table_model.row_for_ip(ip)
                    if row < 0:
                        continue
                    index = self.window.device_table_model.index(row, 0)
                    selection_model.select(
                        QItemSelection(index, index),
                        QItemSelectionModel.Select | QItemSelectionModel.Rows,
                    )

                if focused_ip:
                    row = self.window.device_table_model.row_for_ip(focused_ip)
                    if row >= 0:
                        index = self.window.device_table_model.index(row, 0)
                        self.window.device_table.setCurrentIndex(index)
            finally:
                del blocker

    def _sync_registry_selection_from_table(self) -> None:
        if not self._selection_sync_enabled:
            return

        selected_ips = self._selected_ips_from_table()
        focused_ip = self._focused_ip_from_table()

        self.supervisor.registry.clear_selection()
        for ip in selected_ips:
            self.supervisor.set_selected(ip, True)
        self.supervisor.set_focused(focused_ip)

        self.refresh_all()

    def _current_target_ips(self) -> list[str]:
        checked_ips = [
            snapshot.ip
            for snapshot in self.supervisor.registry.list_snapshots()
            if snapshot.selected
        ]
        if checked_ips:
            return checked_ips

        selected = self._selected_ips_from_table()
        if selected:
            return selected

        focused = self._focused_ip_from_table()
        if focused:
            return [focused]

        return []

    def _apply_probe_metadata(self, ip: str, probe: dict | None) -> None:
        if not probe:
            return

        flavor_raw = str(probe.get("flavor") or "").strip().lower()
        if flavor_raw == DeviceFlavor.LEGACY.value:
            flavor = DeviceFlavor.LEGACY
        elif flavor_raw == DeviceFlavor.TTA.value:
            flavor = DeviceFlavor.TTA
        elif flavor_raw == DeviceFlavor.SECURITY3.value:
            flavor = DeviceFlavor.SECURITY3
        else:
            flavor = DeviceFlavor.UNKNOWN

        self.supervisor.registry.update_snapshot(
            ip,
            base_url=str(probe.get("base_url") or ""),
            root_path=str(probe.get("root_path") or ""),
            auth_scheme=str(probe.get("auth_scheme") or ""),
            flavor=flavor,
        )

    def _handle_rows_added(self, rows: list[dict]) -> None:
        added_count = 0
        for row in rows:
            ip = str(row.get("ip") or "").strip()
            if not ip:
                continue

            port = int(row.get("port") or 0)
            note = str(row.get("note") or "").strip()

            self.supervisor.add_device(ip, port=port, note=note)
            self._apply_probe_metadata(ip, row.get("probe"))
            added_count += 1

        if added_count > 0:
            self._append_log(f"rows added: {added_count}")
            self._append_result(f"rows added: {added_count}")
            self.refresh_all()

    def _ensure_add_device_window(self) -> None:
        if self._add_device_window is None:
            self._add_device_window = AddDeviceWindow(self.window)
            self._add_device_controller = AddDeviceController(
                window=self._add_device_window,
                on_rows_added=self._handle_rows_added,
            )
            self._add_device_controller.bind()

    def _ensure_discovery_window(self) -> None:
        if self._discovery_window is None:
            self._discovery_window = DiscoveryWindow(self.window)
            self._discovery_controller = DiscoveryController(
                window=self._discovery_window,
                on_rows_added=self._handle_rows_added,
                on_log=self._append_log,
            )
            self._discovery_controller.bind()

    def _on_open_add_device_window(self) -> None:
        self._ensure_add_device_window()
        assert self._add_device_window is not None
        self._add_device_window.show()
        self._add_device_window.raise_()
        self._add_device_window.activateWindow()

    def _on_open_discovery_window(self) -> None:
        self._ensure_discovery_window()
        assert self._discovery_window is not None
        self._discovery_window.show()
        self._discovery_window.raise_()
        self._discovery_window.activateWindow()

    def _on_clear_selection_clicked(self) -> None:
        self.supervisor.registry.clear_selection()
        self.supervisor.set_focused(None)
        self.refresh_all()

    def _on_checkbox_toggled(self, ip: str, checked: bool) -> None:
        self.supervisor.set_selected(ip, checked)
        self.refresh_all()

    def _on_header_section_clicked(self, section: int) -> None:
        key = self.window.device_table_model.COLUMN_KEYS[section]
        if key != "selected":
            return

        snapshots = self.supervisor.registry.list_snapshots()
        if not snapshots:
            return

        select_all = not all(snapshot.selected for snapshot in snapshots)
        for snapshot in snapshots:
            self.supervisor.set_selected(snapshot.ip, select_all)

        self.refresh_all()

    def _on_connect_selected_clicked(self) -> None:
        target_ips = self._current_target_ips()
        if not target_ips:
            self._show_error("Connect", "체크되었거나 선택된 장비가 없습니다.")
            return

        entered_username = self.window.connect_panel.entered_username().strip()
        entered_password = self.window.connect_panel.entered_password().strip()

        if not entered_username:
            self._show_error("Connect", "ID를 입력하세요.")
            return

        if not entered_password:
            self._show_error("Connect", "현재 비밀번호를 입력하세요.")
            return

        for ip in target_ips:
            request = self._build_phase1_request(ip)
            self.supervisor.enqueue_connect(ip, request)
            self._append_log(
                f"connect queued: ip={ip} port={request.port} user={request.username} "
                f"pw={request.password} target={request.target_password} tls={request.verify_tls}"
            )

    def _on_load_info_clicked(self) -> None:
        target_ips = self._current_target_ips()
        if not target_ips:
            self._show_error("Load Info", "체크되었거나 선택된 장비가 없습니다.")
            return

        queued = 0
        for ip in target_ips:
            snapshot = self.supervisor.get_snapshot(ip)
            actor = self._actor_for_ip(ip)

            if snapshot is None:
                self._append_log(f"info skipped (no snapshot): {ip}")
                continue

            if not snapshot.connected:
                self._append_log(f"info skipped (not connected): {ip}")
                continue

            if actor is not None and hasattr(actor, "has_session") and not actor.has_session():
                self._append_log(f"info skipped (no session): {ip}")
                continue

            self.supervisor.enqueue_info_load(ip)
            self._append_log(f"info queued: {ip}")
            queued += 1

        if queued == 0:
            self._show_error("Load Info", "연결 성공한 장비가 없습니다.")

    def _on_poll_status_clicked(self) -> None:
        target_ips = self._current_target_ips()
        if not target_ips:
            self._show_error("Poll Status", "체크되었거나 선택된 장비가 없습니다.")
            return

        queued = 0
        for ip in target_ips:
            snapshot = self.supervisor.get_snapshot(ip)
            actor = self._actor_for_ip(ip)

            if snapshot is None:
                self._append_log(f"status skipped (no snapshot): {ip}")
                continue

            if not snapshot.connected:
                self._append_log(f"status skipped (not connected): {ip}")
                continue

            if actor is not None and hasattr(actor, "has_session") and not actor.has_session():
                self._append_log(f"status skipped (no session): {ip}")
                continue

            self.supervisor.enqueue_status_poll(ip, hot=True)
            self._append_log(f"status poll queued: {ip}")
            queued += 1

        if queued == 0:
            self._show_error("Poll Status", "연결 성공한 장비가 없습니다.")

    def _on_reboot_clicked(self) -> None:
        target_ips = self._current_target_ips()
        if not target_ips:
            self._show_error("Reboot", "체크되었거나 선택된 장비가 없습니다.")
            return

        for ip in target_ips:
            self.supervisor.enqueue_control(ip, handler="reboot", kwargs={})
            self._append_log(f"reboot queued: {ip}")

    def _on_sync_rtc_clicked(self) -> None:
        target_ips = self._current_target_ips()
        if not target_ips:
            self._show_error("Sync RTC", "체크되었거나 선택된 장비가 없습니다.")
            return

        for ip in target_ips:
            self.supervisor.enqueue_control(ip, handler="set_rtc", kwargs={})
            self._append_log(f"sync rtc queued: {ip}")

    def _on_table_selection_changed(self, selected, deselected) -> None:
        self._sync_registry_selection_from_table()

    def _on_table_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        snapshot = self.window.device_table_model.snapshot_at_row(index.row())
        if snapshot is None:
            return
        self.supervisor.set_focused(snapshot.ip)
        self.refresh_all()