from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)


RESET_PASSWORDS = {"1234", "admin"}


class ConnectPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Connect")
        self._build_ui()
        self._update_mode_hint()

    def _make_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setMinimumHeight(26)
        button.setMaximumHeight(26)
        button.setStyleSheet(
            """
            QPushButton {
                padding: 0px 6px;
            }
            """
        )
        return button

    def _build_ui(self) -> None:
        self.username_edit = QLineEdit("admin")
        self.username_edit.setPlaceholderText("현재 ID")

        self.password_edit = QLineEdit("1234")
        self.password_edit.setPlaceholderText("현재 비밀번호")

        self.target_profile_combo = QComboBox()
        self.target_profile_combo.addItem("기본 장비 (123)", "basic")
        self.target_profile_combo.addItem("TTA (!camera1108)", "tta")
        self.target_profile_combo.addItem("보안 3.0 (!Camera1108)", "security3")

        self.mode_hint_label = QLabel("")
        self.mode_hint_label.setWordWrap(True)

        self.target_summary_label = QLabel("대상: 체크 0대 / 현재 장비 없음")
        self.target_summary_label.setWordWrap(True)
        self.target_summary_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.connect_selected_button = self._make_button("선택 장비 연결")
        self.disconnect_selected_button = self._make_button("선택 장비 연결 해제")

        form = QFormLayout()
        form.setContentsMargins(2, 2, 2, 2)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(4)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.addRow("아이디", self.username_edit)
        form.addRow("현재 비밀번호", self.password_edit)
        form.addRow("변경 대상", self.target_profile_combo)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(4)
        button_row.addWidget(self.connect_selected_button, 1)
        button_row.addWidget(self.disconnect_selected_button, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 6, 4, 6)
        root.setSpacing(5)
        root.addLayout(form)
        root.addWidget(self.mode_hint_label)
        root.addWidget(self.target_summary_label)
        root.addLayout(button_row)

        self.password_edit.textChanged.connect(self._update_mode_hint)

    def entered_username(self) -> str:
        text = self.username_edit.text().strip()
        return text if text else "admin"

    def entered_password(self) -> str:
        return self.password_edit.text()

    def is_factory_reset_password(self) -> bool:
        return self.entered_password().strip() in RESET_PASSWORDS

    def selected_target_profile(self) -> str:
        data = self.target_profile_combo.currentData()
        return str(data or "basic")

    def target_password(self) -> str:
        profile = self.selected_target_profile()
        if profile == "basic":
            return "123"
        if profile == "tta":
            return "!camera1108"
        if profile == "security3":
            return "!Camera1108"
        return "123"

    def sec3_username(self) -> str:
        return "TruenTest"

    def sec3_password(self) -> str:
        return "!Camera1108"

    def set_target_summary(self, current_ip: str | None, checked_count: int) -> None:
        current_text = (current_ip or "").strip() or "없음"
        self.target_summary_label.setText(
            f"대상: 체크 {int(checked_count)}대 / 현재 {current_text}"
        )

    def _update_mode_hint(self) -> None:
        reset_mode = self.is_factory_reset_password()
        self.target_profile_combo.setEnabled(reset_mode)

        if reset_mode:
            self.mode_hint_label.setText(
                "초기화 비밀번호입니다. 선택한 운영 비밀번호로 변경 후 연결합니다."
            )
        else:
            self.mode_hint_label.setText(
                "이미 변경된 비밀번호입니다. 입력한 아이디/비밀번호로 바로 연결합니다."
            )