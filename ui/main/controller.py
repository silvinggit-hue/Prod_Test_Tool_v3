from __future__ import annotations

import ipaddress
from contextlib import contextmanager

from PyQt5.QtCore import QItemSelection, QItemSelectionModel, QModelIndex, QSignalBlocker, QTimer
from PyQt5.QtWidgets import QMessageBox

from application.core.app_supervisor import AppSupervisor
from application.firmware.firmware_batch_supervisor import FirmwareBatchSupervisor
from domain.enums.device import DeviceFlavor, DeviceState
from domain.models.phase1 import Phase1Request
from ui.add_device.controller import AddDeviceController
from ui.add_device.window import AddDeviceWindow
from ui.discovery.controller import DiscoveryController
from ui.discovery.window import DiscoveryWindow
from ui.main.window import MainWindow
from ui.video.controller import VideoWindowController
from ui.video.window import VideoWindow
from ui.firmware.controller import FirmwareWindowController
from ui.firmware.window import FirmwareWindow


class MainWindowController:
    BATCH_ALLOWED_HANDLERS = {
        "set_tdn",
        "set_icr",
        "set_air_wiper",
        "set_sensor_485",
        "set_shock_sensor",
        "reboot",
        "factory_reset",
        "set_model_name",
        "set_rtc",
        "set_extra_id",
        "apply_secondary_video",
        "set_min_focus_length",
        "apply_audio_profile",
        "set_video_input_format",
    }

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
        self._video_window: VideoWindow | None = None
        self._video_controller: VideoWindowController | None = None
        self._ui_timer: QTimer | None = None
        self._firmware_window: FirmwareWindow | None = None
        self._firmware_controller: FirmwareWindowController | None = None
        self._firmware_supervisor: FirmwareBatchSupervisor | None = None

    def bind(self) -> None:
        self.window.add_device_action.triggered.connect(self._on_open_add_device_window)
        self.window.discovery_action.triggered.connect(self._on_open_discovery_window)
        self.window.video_action.triggered.connect(self._on_open_video_window)
        self.window.firmware_action.triggered.connect(self._on_open_firmware_window)
        self.window.delete_rows_action.triggered.connect(self._on_delete_rows_clicked)

        self.window.connect_panel.connect_selected_button.clicked.connect(self._on_connect_selected_clicked)
        self.window.connect_panel.disconnect_selected_button.clicked.connect(self._on_disconnect_selected_clicked)

        self.window.info_panel.load_info_button.clicked.connect(self._on_load_info_clicked)
        self.window.status_panel.poll_status_button.clicked.connect(self._on_poll_status_clicked)

        self._bind_control_panel()

        self.window.device_table.selectionModel().selectionChanged.connect(self._on_table_selection_changed)
        self.window.device_table.doubleClicked.connect(self._on_table_double_clicked)
        self.window.device_table_model.selection_toggled.connect(self._on_checkbox_toggled)
        self.window.device_table.horizontalHeader().sectionClicked.connect(self._on_header_section_clicked)

        self._ui_timer = QTimer(self.window)
        self._ui_timer.setInterval(100)
        self._ui_timer.timeout.connect(self._on_ui_refresh_tick)
        self._ui_timer.start()

        self.refresh_all()

    def _bind_control_panel(self) -> None:
        panel = self.window.control_panel

        panel.single_mode_radio.toggled.connect(self._refresh_target_summary)
        panel.batch_mode_radio.toggled.connect(self._refresh_target_summary)

        panel.pt_leftup_button.pressed.connect(lambda: self._on_pt_press("leftup"))
        panel.pt_leftup_button.released.connect(self._on_pt_release)

        panel.pt_up_button.pressed.connect(lambda: self._on_pt_press("up"))
        panel.pt_up_button.released.connect(self._on_pt_release)

        panel.pt_rightup_button.pressed.connect(lambda: self._on_pt_press("rightup"))
        panel.pt_rightup_button.released.connect(self._on_pt_release)

        panel.pt_left_button.pressed.connect(lambda: self._on_pt_press("left"))
        panel.pt_left_button.released.connect(self._on_pt_release)

        panel.pt_right_button.pressed.connect(lambda: self._on_pt_press("right"))
        panel.pt_right_button.released.connect(self._on_pt_release)

        panel.pt_leftdown_button.pressed.connect(lambda: self._on_pt_press("leftdown"))
        panel.pt_leftdown_button.released.connect(self._on_pt_release)

        panel.pt_down_button.pressed.connect(lambda: self._on_pt_press("down"))
        panel.pt_down_button.released.connect(self._on_pt_release)

        panel.pt_rightdown_button.pressed.connect(lambda: self._on_pt_press("rightdown"))
        panel.pt_rightdown_button.released.connect(self._on_pt_release)

        panel.zoom_in_button.pressed.connect(lambda: self._on_zoom_press("in"))
        panel.zoom_in_button.released.connect(self._on_zoom_release)
        panel.zoom_out_button.pressed.connect(lambda: self._on_zoom_press("out"))
        panel.zoom_out_button.released.connect(self._on_zoom_release)
        panel.zoom_1x_button.clicked.connect(lambda: self._on_zoom_clicked("1x"))

        panel.focus_near_button.pressed.connect(lambda: self._on_focus_press("near"))
        panel.focus_near_button.released.connect(self._on_focus_release)
        panel.focus_far_button.pressed.connect(lambda: self._on_focus_press("far"))
        panel.focus_far_button.released.connect(self._on_focus_release)
        panel.focus_auto_button.clicked.connect(lambda: self._on_focus_clicked("auto"))

        panel.tdn_day_button.clicked.connect(lambda: self._on_tdn_clicked("day"))
        panel.tdn_night_button.clicked.connect(lambda: self._on_tdn_clicked("night"))
        panel.tdn_auto_button.clicked.connect(lambda: self._on_tdn_clicked("auto"))

        panel.icr_on_button.clicked.connect(lambda: self._on_icr_clicked("on"))
        panel.icr_off_button.clicked.connect(lambda: self._on_icr_clicked("off"))
        panel.icr_auto_button.clicked.connect(lambda: self._on_icr_clicked("auto"))

        panel.air_wiper_on_button.clicked.connect(lambda: self._on_air_wiper_clicked("on"))
        panel.air_wiper_off_button.clicked.connect(lambda: self._on_air_wiper_clicked("off"))

        panel.model_apply_button.clicked.connect(self._on_model_apply_clicked)
        panel.extra_id_apply_button.clicked.connect(self._on_extra_id_apply_clicked)
        panel.sync_rtc_button.clicked.connect(self._on_sync_rtc_clicked)

        panel.secondary_video_button.clicked.connect(self._on_secondary_video_clicked)
        panel.video_input_apply_button.clicked.connect(self._on_video_input_apply_clicked)
        panel.min_focus_apply_button.clicked.connect(self._on_min_focus_apply_clicked)
        panel.sensor_485_on_button.clicked.connect(lambda: self._on_sensor_485_clicked("on"))
        panel.sensor_485_off_button.clicked.connect(lambda: self._on_sensor_485_clicked("off"))
        panel.shock_sensor_on_button.clicked.connect(lambda: self._on_shock_sensor_clicked("on"))
        panel.shock_sensor_off_button.clicked.connect(lambda: self._on_shock_sensor_clicked("off"))
        panel.audio_apply_button.clicked.connect(self._on_audio_apply_clicked)
        panel.audio_max_volume_button.clicked.connect(self._on_audio_max_volume_clicked)

        panel.reboot_button.clicked.connect(self._on_reboot_clicked)
        panel.factory_reset_button.clicked.connect(self._on_factory_reset_clicked)

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
        self.window.control_panel.set_video_input_context(focus_snapshot)
        self._refresh_target_summary()

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

    def _checked_ips(self) -> list[str]:
        return [
            snapshot.ip
            for snapshot in self.supervisor.registry.list_snapshots()
            if snapshot.selected
        ]

    def _current_target_ips(self) -> list[str]:
        checked_ips = self._checked_ips()
        if checked_ips:
            return checked_ips

        selected = self._selected_ips_from_table()
        if selected:
            return selected

        focused = self._focused_ip_from_table()
        if focused:
            return [focused]

        return []

    def _single_target_ip(self) -> str | None:
        targets = self._current_target_ips()
        return targets[0] if targets else None

    def _refresh_target_summary(self) -> None:
        current_ip = self._single_target_ip()
        checked_count = len(self._checked_ips())
        self.window.connect_panel.set_target_summary(current_ip, checked_count)
        self.window.control_panel.set_target_summary(current_ip, checked_count)

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

    def _ensure_video_window(self) -> None:
        if self._video_window is None:
            self._video_window = VideoWindow(self.window)
            self._video_controller = VideoWindowController(
                window=self._video_window,
                supervisor=self.supervisor,
                checked_ips_provider=self._checked_ips,
                selected_ips_provider=self._selected_ips_from_table,
                focused_ip_provider=self._focused_ip_from_table,
                on_log=self._append_log,
                on_result=self._append_result,
            )
            self._video_controller.bind()

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

    def _on_open_video_window(self) -> None:
        self._ensure_video_window()
        assert self._video_controller is not None
        self._video_controller.open_window()

    def _ensure_firmware_window(self) -> None:
        if self._firmware_window is None:
            self._firmware_window = FirmwareWindow(self.window)
            self._firmware_supervisor = FirmwareBatchSupervisor()
            self._firmware_controller = FirmwareWindowController(
                window=self._firmware_window,
                firmware_supervisor=self._firmware_supervisor,
                checked_ips_provider=self._checked_ips,
                selected_ips_provider=self._selected_ips_from_table,
                focused_ip_provider=self._focused_ip_from_table,
                snapshot_provider=self.supervisor.get_snapshot,
                refresh_main_callback=self.refresh_all,
                enqueue_info_load_callback=self.supervisor.enqueue_info_load,
                on_log=self._append_log,
                on_result=self._append_result,
            )
            self._firmware_controller.bind()

    def _on_open_firmware_window(self) -> None:
        self._ensure_firmware_window()
        assert self._firmware_controller is not None
        self._firmware_controller.open_window()

    def _on_clear_selection_clicked(self) -> None:
        self.supervisor.registry.clear_selection()
        self.supervisor.set_focused(None)
        self.refresh_all()

    def _delete_target_ips(self) -> list[str]:
        checked_ips = self._checked_ips()
        if checked_ips:
            return checked_ips

        selected_ips = self._selected_ips_from_table()
        if selected_ips:
            return selected_ips

        focused_ip = self._focused_ip_from_table()
        if focused_ip:
            return [focused_ip]

        return []

    def _on_delete_rows_clicked(self) -> None:
        target_ips = self._delete_target_ips()
        if not target_ips:
            self._show_error("행 삭제", "삭제할 장비가 없습니다.")
            return

        if QMessageBox.question(
                self.window,
                "행 삭제",
                f"선택한 장비 {len(target_ips)}대를 목록에서 삭제하시겠습니까?",
        ) != QMessageBox.Yes:
            return

        removed_count = self.supervisor.remove_devices(target_ips)

        self._append_log(f"rows deleted: {removed_count}")
        self._append_result(f"행 삭제 완료: {removed_count}대")
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
            self._show_error("연결", "체크되었거나 선택된 장비가 없습니다.")
            return

        entered_username = self.window.connect_panel.entered_username().strip()
        entered_password = self.window.connect_panel.entered_password().strip()

        if not entered_username:
            self._show_error("연결", "아이디를 입력하세요.")
            return

        if not entered_password:
            self._show_error("연결", "현재 비밀번호를 입력하세요.")
            return

        requests: list[tuple[str, Phase1Request]] = []
        for ip in target_ips:
            request = self._build_phase1_request(ip)
            requests.append((ip, request))
            self._append_log(
                f"connect batch item: ip={ip} port={request.port} user={request.username} "
                f"pw={request.password} target={request.target_password} tls={request.verify_tls}"
            )

        if hasattr(self.supervisor, "enqueue_connect_batch"):
            batch_id = self.supervisor.enqueue_connect_batch(requests, auto_info=True)
            self._append_log(f"connect batch queued: batch_id={batch_id} count={len(requests)}")
            self._append_result(f"연결 시작: {len(requests)}대 / batch={batch_id}")
        else:
            for ip, request in requests:
                self.supervisor.enqueue_connect(ip, request)
            self._append_log(f"connect queued: count={len(requests)}")
            self._append_result(f"연결 시작: {len(requests)}대")

    def _disconnect_targets(self, ips: list[str], *, reason: str = "연결 해제됨") -> int:
        count = 0
        for ip in ips:
            snapshot = self.supervisor.get_snapshot(ip)
            actor = self._actor_for_ip(ip)

            if actor is not None and hasattr(actor, "disconnect"):
                actor.disconnect(reason=reason)
                count += 1
                continue

            if snapshot is not None:
                self.supervisor.registry.update_snapshot(
                    ip,
                    connected=False,
                    state=DeviceState.DISCONNECTED,
                )
                count += 1

        self.refresh_all()
        return count

    def _on_disconnect_selected_clicked(self) -> None:
        target_ips = self._current_target_ips()
        if not target_ips:
            self._show_error("연결 해제", "체크되었거나 선택된 장비가 없습니다.")
            return

        if QMessageBox.question(
            self.window,
            "연결 해제",
            f"선택 장비 {len(target_ips)}대의 작업을 멈추고 연결을 해제하시겠습니까?",
        ) != QMessageBox.Yes:
            return

        count = self._disconnect_targets(target_ips, reason="사용자 연결 해제")
        self._append_log(f"disconnect applied: {count}")
        self._append_result(f"연결 해제 완료: {count}대")

    def _on_load_info_clicked(self) -> None:
        target_ips = self._current_target_ips()
        if not target_ips:
            self._show_error("정보 읽기", "체크되었거나 선택된 장비가 없습니다.")
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
            self._show_error("정보 읽기", "연결 성공한 장비가 없습니다.")

    def _on_poll_status_clicked(self) -> None:
        target_ips = self._current_target_ips()
        if not target_ips:
            self._show_error("상태 읽기", "체크되었거나 선택된 장비가 없습니다.")
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
            self._show_error("상태 읽기", "연결 성공한 장비가 없습니다.")

    def _resolve_control_target_ips(
        self,
        *,
        single_only: bool = False,
        require_connected: bool = True,
        require_session: bool = True,
        action_name: str = "제어",
        show_error_if_empty: bool = True,
    ) -> list[str]:
        mode = self.window.control_panel.control_mode()

        if single_only:
            source_ips = self._current_target_ips()[:1]
        elif mode == "batch":
            source_ips = self._checked_ips()
        else:
            source_ips = self._current_target_ips()[:1]

        if not source_ips:
            if show_error_if_empty:
                if single_only or mode == "single":
                    self._show_error(action_name, "현재 장비가 없습니다.")
                else:
                    self._show_error(action_name, "전체 제어 대상이 없습니다. 체크박스로 장비를 선택하세요.")
            return []

        resolved: list[str] = []
        for ip in source_ips:
            snapshot = self.supervisor.get_snapshot(ip)
            actor = self._actor_for_ip(ip)

            if snapshot is None:
                self._append_log(f"{action_name} skipped (no snapshot): {ip}")
                continue

            if require_connected and not snapshot.connected:
                self._append_log(f"{action_name} skipped (not connected): {ip}")
                continue

            if require_session and actor is not None and hasattr(actor, "has_session") and not actor.has_session():
                self._append_log(f"{action_name} skipped (no session): {ip}")
                continue

            resolved.append(ip)

        if not resolved and show_error_if_empty:
            self._show_error(action_name, "실행 가능한 연결 장비가 없습니다.")

        return resolved

    def _enqueue_control_for_targets(
        self,
        *,
        handler: str,
        kwargs: dict | None = None,
        action_name: str,
        single_only: bool = False,
        confirm_text: str | None = None,
        show_error_if_empty: bool = True,
    ) -> None:
        if not single_only and self.window.control_panel.control_mode() == "batch":
            if handler not in self.BATCH_ALLOWED_HANDLERS:
                self._show_error(action_name, "이 기능은 현재 장비 1대만 제어할 수 있습니다.")
                return

        if confirm_text:
            if QMessageBox.question(self.window, action_name, confirm_text) != QMessageBox.Yes:
                return

        target_ips = self._resolve_control_target_ips(
            single_only=single_only,
            require_connected=True,
            require_session=True,
            action_name=action_name,
            show_error_if_empty=show_error_if_empty,
        )
        if not target_ips:
            return

        for ip in target_ips:
            self.supervisor.enqueue_control(ip, handler=handler, kwargs=dict(kwargs or {}))
            self._append_log(f"{handler} queued: {ip}")

        self._append_result(f"{action_name} 실행: {len(target_ips)}대")

    def _on_pt_press(self, action: str) -> None:
        self._enqueue_control_for_targets(
            handler="pt",
            kwargs={"action": action, "speed": 5},
            action_name="PT 제어",
            single_only=True,
            show_error_if_empty=True,
        )

    def _on_pt_release(self) -> None:
        self._enqueue_control_for_targets(
            handler="pt",
            kwargs={"action": "stop", "speed": 5},
            action_name="PT 정지",
            single_only=True,
            show_error_if_empty=False,
        )

    def _on_zoom_press(self, action: str) -> None:
        self._enqueue_control_for_targets(
            handler="zoom",
            kwargs={"action": action},
            action_name="Zoom 제어",
            single_only=True,
            show_error_if_empty=True,
        )

    def _on_zoom_release(self) -> None:
        self._enqueue_control_for_targets(
            handler="zoom",
            kwargs={"action": "stop"},
            action_name="Zoom 정지",
            single_only=True,
            show_error_if_empty=False,
        )

    def _on_zoom_clicked(self, action: str) -> None:
        self._enqueue_control_for_targets(
            handler="zoom",
            kwargs={"action": action},
            action_name="Zoom 제어",
            single_only=True,
        )

    def _on_focus_press(self, action: str) -> None:
        self._enqueue_control_for_targets(
            handler="focus",
            kwargs={"action": action},
            action_name="Focus 제어",
            single_only=True,
            show_error_if_empty=True,
        )

    def _on_focus_release(self) -> None:
        self._enqueue_control_for_targets(
            handler="focus",
            kwargs={"action": "stop"},
            action_name="Focus 정지",
            single_only=True,
            show_error_if_empty=False,
        )

    def _on_focus_clicked(self, action: str) -> None:
        self._enqueue_control_for_targets(
            handler="focus",
            kwargs={"action": action},
            action_name="Focus 제어",
            single_only=True,
        )

    def _on_tdn_clicked(self, action: str) -> None:
        self._enqueue_control_for_targets(
            handler="set_tdn",
            kwargs={"action": action},
            action_name="TDN 변경",
        )

    def _on_icr_clicked(self, action: str) -> None:
        self._enqueue_control_for_targets(
            handler="set_icr",
            kwargs={"action": action},
            action_name="ICR 변경",
        )

    def _on_air_wiper_clicked(self, action: str) -> None:
        self._enqueue_control_for_targets(
            handler="set_air_wiper",
            kwargs={"action": action},
            action_name="Air Wiper 변경",
        )

    def _on_model_apply_clicked(self) -> None:
        value = self.window.control_panel.model_name()
        if not value:
            self._show_error("모델명 적용", "모델명을 입력하세요.")
            return

        self._enqueue_control_for_targets(
            handler="set_model_name",
            kwargs={"value": value},
            action_name="모델명 적용",
        )

    def _on_extra_id_apply_clicked(self) -> None:
        value = self.window.control_panel.extra_id()
        if not value:
            self._show_error("Extra ID 적용", "Extra ID를 입력하세요.")
            return

        self._enqueue_control_for_targets(
            handler="set_extra_id",
            kwargs={"value": value},
            action_name="Extra ID 적용",
        )

    def _on_sync_rtc_clicked(self) -> None:
        self._enqueue_control_for_targets(
            handler="set_rtc",
            kwargs={},
            action_name="시간 현재값 적용",
        )

    def _on_secondary_video_clicked(self) -> None:
        self._enqueue_control_for_targets(
            handler="apply_secondary_video",
            kwargs={},
            action_name="보조 영상 설정",
        )

    def _on_video_input_apply_clicked(self) -> None:
        code = self.window.control_panel.video_input_code()
        label = self.window.control_panel.video_input_label()
        resolution_code = self.window.control_panel.video_input_max_resolution()

        if not code:
            self._show_error("입력 형식 적용", "입력 형식을 선택하세요.")
            return

        if not resolution_code:
            self._show_error("입력 형식 적용", "선택한 입력 형식의 해상도 매핑을 찾을 수 없습니다.")
            return

        self._enqueue_control_for_targets(
            handler="set_video_input_format",
            kwargs={
                "input_code": code,
                "resolution_code": resolution_code,
            },
            action_name="입력 형식 적용",
        )
        self._append_log(
            f"video input selected: {label} / VID_INPUTFORMAT={code} / VID_RESOLUTION={resolution_code}"
        )

    def _on_min_focus_apply_clicked(self) -> None:
        value = self.window.control_panel.min_focus_value()
        if not value:
            self._show_error("최소 초점 적용", "최소 초점 거리를 입력하세요.")
            return

        self._enqueue_control_for_targets(
            handler="set_min_focus_length",
            kwargs={"value": value},
            action_name="최소 초점 적용",
        )

    def _on_sensor_485_clicked(self, action: str) -> None:
        self._enqueue_control_for_targets(
            handler="set_sensor_485",
            kwargs={"action": action},
            action_name="485 Sensor 변경",
        )

    def _on_shock_sensor_clicked(self, action: str) -> None:
        self._enqueue_control_for_targets(
            handler="set_shock_sensor",
            kwargs={"action": action},
            action_name="Shock Sensor 변경",
        )

    def _on_audio_apply_clicked(self) -> None:
        self._enqueue_control_for_targets(
            handler="apply_audio_profile",
            kwargs={
                "algorithm": self.window.control_panel.audio_algorithm(),
                "source": self.window.control_panel.audio_source(),
                "output": self.window.control_panel.audio_output(),
                "mode": "3",
                "set_max_volume": False,
            },
            action_name="오디오 적용",
        )

    def _on_audio_max_volume_clicked(self) -> None:
        self._enqueue_control_for_targets(
            handler="apply_audio_profile",
            kwargs={
                "algorithm": self.window.control_panel.audio_algorithm(),
                "source": self.window.control_panel.audio_source(),
                "output": self.window.control_panel.audio_output(),
                "mode": "3",
                "set_max_volume": True,
            },
            action_name="오디오 최대 볼륨",
        )

    def _on_reboot_clicked(self) -> None:
        mode = self.window.control_panel.control_mode()
        target_label = "현재 장비" if mode == "single" else "체크한 장비"
        self._enqueue_control_for_targets(
            handler="reboot",
            kwargs={},
            action_name="재부팅",
            confirm_text=f"{target_label}를 재부팅하시겠습니까?",
        )

    def _on_factory_reset_clicked(self) -> None:
        mode = self.window.control_panel.control_mode()
        target_label = "현재 장비" if mode == "single" else "체크한 장비"
        self._enqueue_control_for_targets(
            handler="factory_reset",
            kwargs={},
            action_name="공장 초기화",
            confirm_text=f"{target_label}를 공장 초기화하시겠습니까?",
        )

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