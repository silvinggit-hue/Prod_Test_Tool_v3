from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
)

from infra.data.video_input_profiles import (
    boardid_to_hex,
    get_board_input_formats,
    get_max_resolution_for_inputformat,
    resolve_board_input_group,
)


class ControlPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Control")
        self._video_input_context_key: tuple[str, str] | None = None
        self._build_ui()

    # ---------------------------------------------------------
    # compact helpers
    # ---------------------------------------------------------
    def _make_button(
        self,
        text: str,
        *,
        height: int = 23,
        fill: bool = False,
    ) -> QPushButton:
        button = QPushButton(text)

        if fill:
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        button.setMinimumHeight(height)
        button.setMaximumHeight(height)
        button.setMinimumWidth(0)
        button.setStyleSheet(
            """
            QPushButton {
                padding: 0px 2px;
            }
            """
        )
        return button

    def _make_small_button(self, text: str) -> QPushButton:
        return self._make_button(text, height=23, fill=False)

    def _make_fill_button(self, text: str) -> QPushButton:
        return self._make_button(text, height=23, fill=True)

    def _row(self, *widgets) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        for widget in widgets:
            lay.addWidget(widget, 1)

        return lay

    def _compact_group(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setStyleSheet(
            """
            QGroupBox {
                margin-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 5px;
                padding: 0 2px 0 2px;
            }
            """
        )
        return box

    # ---------------------------------------------------------
    # build
    # ---------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(3, 6, 3, 6)
        root.setSpacing(5)

        root.addWidget(self._build_target_group())
        root.addWidget(self._build_ptz_group())
        root.addWidget(self._build_air_wiper_group())
        root.addWidget(self._build_video_filter_group())
        root.addWidget(self._build_device_group())
        root.addWidget(self._build_test_prep_group())
        root.addWidget(self._build_system_group())
        root.addStretch(1)

    def _build_target_group(self) -> QGroupBox:
        box = self._compact_group("제어 대상")

        self.single_mode_radio = QRadioButton("현재 장비 1대")
        self.batch_mode_radio = QRadioButton("체크한 장비 전체")
        self.single_mode_radio.setChecked(True)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.single_mode_radio)
        self.mode_group.addButton(self.batch_mode_radio)

        self.target_summary_label = QLabel("현재 장비: 없음\n전체 제어 대상: 0대")
        self.target_summary_label.setWordWrap(True)
        self.target_summary_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        top.addWidget(self.single_mode_radio)
        top.addWidget(self.batch_mode_radio)
        top.addStretch(1)

        root = QVBoxLayout(box)
        root.setContentsMargins(3, 6, 3, 6)
        root.setSpacing(5)
        root.addLayout(top)
        root.addWidget(self.target_summary_label)
        return box

    def _build_ptz_group(self) -> QGroupBox:
        box = self._compact_group("렌즈 / PTZ")

        self.pt_leftup_button = self._make_small_button("↖")
        self.pt_up_button = self._make_small_button("↑")
        self.pt_rightup_button = self._make_small_button("↗")
        self.pt_left_button = self._make_small_button("←")
        self.pt_right_button = self._make_small_button("→")
        self.pt_leftdown_button = self._make_small_button("↙")
        self.pt_down_button = self._make_small_button("↓")
        self.pt_rightdown_button = self._make_small_button("↘")

        for button in (
            self.pt_leftup_button,
            self.pt_up_button,
            self.pt_rightup_button,
            self.pt_left_button,
            self.pt_right_button,
            self.pt_leftdown_button,
            self.pt_down_button,
            self.pt_rightdown_button,
        ):
            button.setFixedSize(26, 23)

        self.zoom_in_button = self._make_fill_button("+")
        self.zoom_out_button = self._make_fill_button("-")
        self.zoom_1x_button = self._make_fill_button("1x")

        self.focus_near_button = self._make_fill_button("Near")
        self.focus_far_button = self._make_fill_button("Far")
        self.focus_auto_button = self._make_fill_button("Auto")

        pt_grid = QGridLayout()
        pt_grid.setContentsMargins(0, 0, 0, 0)
        pt_grid.setHorizontalSpacing(2)
        pt_grid.setVerticalSpacing(2)

        center_label = QLabel("•")
        center_label.setAlignment(Qt.AlignCenter)
        center_label.setFixedSize(18, 18)

        pt_grid.addWidget(self.pt_leftup_button, 0, 0)
        pt_grid.addWidget(self.pt_up_button, 0, 1)
        pt_grid.addWidget(self.pt_rightup_button, 0, 2)

        pt_grid.addWidget(self.pt_left_button, 1, 0)
        pt_grid.addWidget(center_label, 1, 1)
        pt_grid.addWidget(self.pt_right_button, 1, 2)

        pt_grid.addWidget(self.pt_leftdown_button, 2, 0)
        pt_grid.addWidget(self.pt_down_button, 2, 1)
        pt_grid.addWidget(self.pt_rightdown_button, 2, 2)

        pt_wrap = QHBoxLayout()
        pt_wrap.setContentsMargins(0, 0, 0, 0)
        pt_wrap.setSpacing(0)
        pt_wrap.addStretch(1)
        pt_wrap.addLayout(pt_grid)
        pt_wrap.addStretch(1)

        pt_box = self._compact_group("PT")
        pt_box_layout = QVBoxLayout(pt_box)
        pt_box_layout.setContentsMargins(3, 3, 3, 3)
        pt_box_layout.setSpacing(2)
        pt_box_layout.addLayout(pt_wrap)

        zoom_box = self._compact_group("Zoom")
        zoom_layout = QVBoxLayout(zoom_box)
        zoom_layout.setContentsMargins(3, 3, 3, 3)
        zoom_layout.setSpacing(2)
        zoom_layout.addLayout(self._row(self.zoom_in_button, self.zoom_out_button, self.zoom_1x_button))

        focus_box = self._compact_group("Focus")
        focus_layout = QVBoxLayout(focus_box)
        focus_layout.setContentsMargins(3, 3, 3, 3)
        focus_layout.setSpacing(2)
        focus_layout.addLayout(self._row(self.focus_near_button, self.focus_far_button, self.focus_auto_button))

        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(2)
        right_col.addWidget(zoom_box)
        right_col.addWidget(focus_box)

        split_row = QHBoxLayout()
        split_row.setContentsMargins(0, 0, 0, 0)
        split_row.setSpacing(3)
        split_row.addWidget(pt_box, 1)
        split_row.addLayout(right_col, 1)

        root = QVBoxLayout(box)
        root.setContentsMargins(3, 6, 3, 6)
        root.setSpacing(5)
        root.addLayout(split_row)
        return box

    def _build_air_wiper_group(self) -> QGroupBox:
        box = self._compact_group("Air Wiper")

        self.air_wiper_on_button = self._make_fill_button("켜기")
        self.air_wiper_off_button = self._make_fill_button("끄기")

        root = QVBoxLayout(box)
        root.setContentsMargins(3, 6, 3, 6)
        root.setSpacing(5)
        root.addLayout(self._row(self.air_wiper_on_button, self.air_wiper_off_button))
        return box

    def _build_video_filter_group(self) -> QGroupBox:
        box = self._compact_group("영상 / 필터")

        self.tdn_day_button = self._make_fill_button("Day")
        self.tdn_night_button = self._make_fill_button("Night")
        self.tdn_auto_button = self._make_fill_button("Auto")

        self.icr_on_button = self._make_fill_button("On")
        self.icr_off_button = self._make_fill_button("Off")
        self.icr_auto_button = self._make_fill_button("Auto")

        root = QVBoxLayout(box)
        root.setContentsMargins(3, 6, 3, 6)
        root.setSpacing(5)
        root.addLayout(self._row(self.tdn_day_button, self.tdn_night_button, self.tdn_auto_button))
        root.addLayout(self._row(self.icr_on_button, self.icr_off_button, self.icr_auto_button))
        return box

    def _build_device_group(self) -> QGroupBox:
        box = self._compact_group("장비 설정")

        self.model_name_edit = QLineEdit()
        self.model_name_edit.setPlaceholderText("모델명 입력")
        self.model_apply_button = self._make_small_button("적용")

        self.extra_id_edit = QLineEdit()
        self.extra_id_edit.setPlaceholderText("Extra ID 입력")
        self.extra_id_apply_button = self._make_small_button("적용")

        self.sync_rtc_button = self._make_fill_button("현재시간 적용")

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(4)
        form.setVerticalSpacing(3)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.setSpacing(3)
        model_row.addWidget(self.model_name_edit, 1)
        model_row.addWidget(self.model_apply_button, 0)

        extra_id_row = QHBoxLayout()
        extra_id_row.setContentsMargins(0, 0, 0, 0)
        extra_id_row.setSpacing(3)
        extra_id_row.addWidget(self.extra_id_edit, 1)
        extra_id_row.addWidget(self.extra_id_apply_button, 0)

        form.addRow("모델명", model_row)
        form.addRow("Extra ID", extra_id_row)
        form.addRow("RTC", self.sync_rtc_button)

        root = QVBoxLayout(box)
        root.setContentsMargins(3, 6, 3, 6)
        root.setSpacing(5)
        root.addLayout(form)
        return box

    def _build_test_prep_group(self) -> QGroupBox:
        box = self._compact_group("테스트 준비")

        self.secondary_video_button = self._make_fill_button("영상 설정")

        self.video_input_combo = QComboBox()
        self.video_input_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.video_input_combo.setMinimumHeight(23)
        self.video_input_combo.setMaximumHeight(23)
        self.video_input_combo.setEnabled(False)

        self.video_input_target_label = QLabel("선택 정보: -")
        self.video_input_target_label.setWordWrap(True)

        self.video_input_apply_button = self._make_small_button("적용")
        self.video_input_apply_button.setEnabled(False)

        self.min_focus_edit = QLineEdit()
        self.min_focus_edit.setPlaceholderText("최소 초점 거리")
        self.min_focus_apply_button = self._make_small_button("적용")

        self.sensor_485_on_button = self._make_fill_button("켜기")
        self.sensor_485_off_button = self._make_fill_button("끄기")

        self.shock_sensor_on_button = self._make_fill_button("켜기")
        self.shock_sensor_off_button = self._make_fill_button("끄기")

        self.audio_algorithm_combo = QComboBox()
        self.audio_algorithm_combo.addItem("AAC", "aac")
        self.audio_algorithm_combo.addItem("G711", "g711")
        self.audio_algorithm_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.audio_algorithm_combo.setMinimumHeight(23)
        self.audio_algorithm_combo.setMaximumHeight(23)

        self.audio_source_combo = QComboBox()
        self.audio_source_combo.addItem("Analog", "analog")
        self.audio_source_combo.addItem("Embedded", "embedded")
        self.audio_source_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.audio_source_combo.setMinimumHeight(23)
        self.audio_source_combo.setMaximumHeight(23)

        self.audio_output_combo = QComboBox()
        self.audio_output_combo.addItem("Decoded", "decoded")
        self.audio_output_combo.addItem("Loopback", "loopback")
        self.audio_output_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.audio_output_combo.setMinimumHeight(23)
        self.audio_output_combo.setMaximumHeight(23)

        self.audio_apply_button = self._make_fill_button("적용")
        self.audio_max_volume_button = self._make_fill_button("최대 볼륨")

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(4)
        form.setVerticalSpacing(3)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        video_input_row = QHBoxLayout()
        video_input_row.setContentsMargins(0, 0, 0, 0)
        video_input_row.setSpacing(3)
        video_input_row.addWidget(self.video_input_combo, 1)
        video_input_row.addWidget(self.video_input_apply_button, 0)

        min_focus_row = QHBoxLayout()
        min_focus_row.setContentsMargins(0, 0, 0, 0)
        min_focus_row.setSpacing(3)
        min_focus_row.addWidget(self.min_focus_edit, 1)
        min_focus_row.addWidget(self.min_focus_apply_button, 0)

        sensor_485_row = self._row(self.sensor_485_on_button, self.sensor_485_off_button)
        shock_row = self._row(self.shock_sensor_on_button, self.shock_sensor_off_button)

        audio_box = QVBoxLayout()
        audio_box.setContentsMargins(0, 0, 0, 0)
        audio_box.setSpacing(3)
        audio_box.addWidget(self.audio_algorithm_combo)
        audio_box.addWidget(self.audio_source_combo)
        audio_box.addWidget(self.audio_output_combo)
        audio_box.addLayout(self._row(self.audio_apply_button, self.audio_max_volume_button))

        form.addRow("보조 영상", self.secondary_video_button)
        form.addRow("입력 형식", video_input_row)
        form.addRow("선택 정보", self.video_input_target_label)
        form.addRow("최소 초점", min_focus_row)
        form.addRow("485 Sensor", sensor_485_row)
        form.addRow("Shock Sensor", shock_row)
        form.addRow("오디오", audio_box)

        root = QVBoxLayout(box)
        root.setContentsMargins(3, 6, 3, 6)
        root.setSpacing(5)
        root.addLayout(form)

        self.video_input_combo.currentIndexChanged.connect(self._update_video_input_target_label)
        return box

    def _build_system_group(self) -> QGroupBox:
        box = self._compact_group("시스템")

        self.reboot_button = self._make_fill_button("재부팅")
        self.factory_reset_button = self._make_fill_button("공장 초기화")

        root = QVBoxLayout(box)
        root.setContentsMargins(3, 6, 3, 6)
        root.setSpacing(5)
        root.addLayout(self._row(self.reboot_button, self.factory_reset_button))
        return box

    # ---------------------------------------------------------
    # video input helpers
    # ---------------------------------------------------------
    def _clear_video_input_choices(self, message: str) -> None:
        self._video_input_context_key = None
        self.video_input_combo.blockSignals(True)
        self.video_input_combo.clear()
        self.video_input_combo.blockSignals(False)
        self.video_input_combo.setEnabled(False)
        self.video_input_apply_button.setEnabled(False)
        self.video_input_target_label.setText("선택 정보: -")

    def _update_video_input_target_label(self) -> None:
        code = self.video_input_code()
        label = self.video_input_label()
        if not code:
            self.video_input_target_label.setText("선택 정보: -")
            return

        max_res = get_max_resolution_for_inputformat(code)
        if max_res:
            self.video_input_target_label.setText(
                f"{label} / VID_INPUTFORMAT={code} / max res {max_res}"
            )
        else:
            self.video_input_target_label.setText(
                f"{label} / VID_INPUTFORMAT={code} / max res -"
            )

    def set_video_input_context(self, snapshot) -> None:
        if snapshot is None:
            self._clear_video_input_choices("장비 정보 읽기 후 선택 가능")
            return

        model = str(getattr(snapshot, "model", "") or "").strip() or "-"
        board_id = str(getattr(snapshot, "board_id", "") or "").strip()

        if not board_id:
            self._clear_video_input_choices(f"{model} / 보드 정보 없음")
            return

        context_key = (model, board_id)
        if self._video_input_context_key == context_key and self.video_input_combo.count() > 0:
            return

        formats = list(get_board_input_formats(board_id) or [])
        board_hex = boardid_to_hex(board_id)
        group_name = resolve_board_input_group(board_id)

        self.video_input_context_label.setText(
            f"{model} / 보드 {board_hex} / 그룹 {group_name}"
        )

        previous_code = self.video_input_code()

        self.video_input_combo.blockSignals(True)
        self.video_input_combo.clear()
        for code, label in formats:
            self.video_input_combo.addItem(f"{label} [{code}]", str(code))
        self.video_input_combo.blockSignals(False)

        self._video_input_context_key = context_key

        if formats:
            preferred_index = 0
            if previous_code:
                for idx in range(self.video_input_combo.count()):
                    if str(self.video_input_combo.itemData(idx) or "") == previous_code:
                        preferred_index = idx
                        break
            self.video_input_combo.setCurrentIndex(preferred_index)
            self.video_input_combo.setEnabled(True)
            self.video_input_apply_button.setEnabled(True)
            self._update_video_input_target_label()
        else:
            self.video_input_combo.setEnabled(False)
            self.video_input_apply_button.setEnabled(False)
            self.video_input_target_label.setText("선택 정보: 지원 목록 없음")

    # ---------------------------------------------------------
    # getters
    # ---------------------------------------------------------
    def control_mode(self) -> str:
        return "batch" if self.batch_mode_radio.isChecked() else "single"

    def set_target_summary(self, current_ip: str | None, batch_count: int) -> None:
        current_text = (current_ip or "").strip() or "없음"
        self.target_summary_label.setText(
            f"현재 장비: {current_text}\n전체 제어 대상: {int(batch_count)}대"
        )

    def model_name(self) -> str:
        return self.model_name_edit.text().strip()

    def extra_id(self) -> str:
        return self.extra_id_edit.text().strip()

    def min_focus_value(self) -> str:
        return self.min_focus_edit.text().strip()

    def video_input_code(self) -> str:
        return str(self.video_input_combo.currentData() or "").strip()

    def video_input_label(self) -> str:
        return self.video_input_combo.currentText().strip()

    def video_input_max_resolution(self) -> str | None:
        code = self.video_input_code()
        if not code:
            return None
        return get_max_resolution_for_inputformat(code)

    def audio_algorithm(self) -> str:
        return str(self.audio_algorithm_combo.currentData() or "aac")

    def audio_source(self) -> str:
        return str(self.audio_source_combo.currentData() or "analog")

    def audio_output(self) -> str:
        return str(self.audio_output_combo.currentData() or "decoded")