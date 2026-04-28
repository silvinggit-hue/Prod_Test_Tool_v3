from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


RESET_PASSWORDS = {"1234", "admin"}


class ConnectPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Connect")
        self._build_ui()
        self._update_mode_hint()

    def _build_ui(self) -> None:
        self.username_edit = QLineEdit("admin")
        self.username_edit.setPlaceholderText("현재 ID 입력")

        self.password_edit = QLineEdit("1234")
        self.password_edit.setPlaceholderText("현재 비밀번호 입력")
        # PW 마스킹 제거

        self.target_profile_combo = QComboBox()
        self.target_profile_combo.addItem("기본 (123)", "basic")
        self.target_profile_combo.addItem("TTA (!camera1108)", "tta")
        self.target_profile_combo.addItem("보안3.0 (!Camera1108)", "security3")

        self.mode_hint_label = QLabel("")
        self.mode_hint_label.setWordWrap(True)

        self.connect_selected_button = QPushButton("Connect Selected")

        form = QFormLayout()
        form.addRow("ID", self.username_edit)
        form.addRow("PW", self.password_edit)
        form.addRow("Target", self.target_profile_combo)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.mode_hint_label)
        root.addWidget(self.connect_selected_button)

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

    def _update_mode_hint(self) -> None:
        reset_mode = self.is_factory_reset_password()
        self.target_profile_combo.setEnabled(reset_mode)

        if reset_mode:
            self.mode_hint_label.setText(
                "초기화 비밀번호 감지됨. 선택한 Target 비밀번호로 변경한 뒤 접속합니다."
            )
        else:
            self.mode_hint_label.setText(
                "이미 변경된 비밀번호로 판단합니다. 입력한 ID / 비밀번호로 직접 접속을 시도합니다."
            )