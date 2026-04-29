from __future__ import annotations

from PyQt5.QtCore import QEvent, QTimer, pyqtSignal
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from application.core.video_coordinator import VideoStreamItem
from ui.video.video_host import VlcVideoHost


class VideoTileWidget(QFrame):
    double_clicked = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("video_tile")
        self.setStyleSheet(
            """
            QFrame#video_tile {
                border: 1px solid #666;
                border-radius: 6px;
                background: #111;
            }
            """
        )

        self._stream_item: VideoStreamItem | None = None
        self._active_profile_key: str = ""
        self._desired_running = False
        self._status_text = "stopped"

        self._host = VlcVideoHost()

        self.title_label = QLabel("대기")
        self.title_label.setStyleSheet("color: white; font-weight: bold;")
        self.title_label.setWordWrap(True)

        self.video_surface = QWidget()
        self.video_surface.setStyleSheet("background: black;")

        self.profile_label = QLabel("프로필: -")
        self.profile_label.setStyleSheet("color: #dddddd;")

        self.status_label = QLabel("상태: stopped")
        self.status_label.setStyleSheet("color: #dddddd;")
        self.status_label.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)
        root.addWidget(self.title_label)
        root.addWidget(self.video_surface, 1)
        root.addWidget(self.profile_label)
        root.addWidget(self.status_label)

        self._health_timer = QTimer(self)
        self._health_timer.setInterval(1500)
        self._health_timer.timeout.connect(self._on_health_tick)

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(2000)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._restart_stream)

        self.installEventFilter(self)
        self.video_surface.installEventFilter(self)
        self.title_label.installEventFilter(self)
        self.profile_label.installEventFilter(self)
        self.status_label.installEventFilter(self)

    def set_stream_item(self, item: VideoStreamItem | None) -> None:
        self.stop_stream()
        self._stream_item = item

        if item is None:
            self._active_profile_key = ""
            self.title_label.setText("빈 슬롯")
            self.profile_label.setText("프로필: -")
            self._set_status("stopped")
            return

        self._active_profile_key = item.default_profile
        self.title_label.setText(f"{item.ip} / {item.model}")
        self.profile_label.setText(f"프로필: {self._active_profile_key}")
        self.start_stream()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonDblClick:
            self.double_clicked.emit(self)
            return True
        return super().eventFilter(obj, event)

    def start_stream(self) -> None:
        if self._stream_item is None:
            return

        self._desired_running = True
        self._set_status("starting")

        url = self._stream_item.rtsp_profiles.get(self._active_profile_key, "")
        if not url:
            self._set_status("error", detail="프로필 URL 없음")
            return

        ok, detail = self._host.start(url=url, widget_id=int(self.video_surface.winId()))
        if not ok:
            self._set_status("error", detail=detail)
            self._schedule_reconnect()
            return

        self._health_timer.start()

    def stop_stream(self) -> None:
        self._desired_running = False
        self._health_timer.stop()
        self._reconnect_timer.stop()
        try:
            self._host.stop()
        except Exception:
            pass
        self._set_status("stopped")

    def refresh_stream(self) -> None:
        if self._stream_item is None:
            return
        self.stop_stream()
        self.start_stream()

    def _on_health_tick(self) -> None:
        if not self._desired_running:
            self._set_status("stopped")
            return

        state, detail = self._host.poll_state()

        if state == "playing":
            self._set_status("playing")
            return

        if state == "starting":
            self._set_status("starting")
            return

        if state == "stopped":
            self._set_status("reconnecting")
            self._schedule_reconnect()
            return

        self._set_status("error", detail=detail)
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if not self._desired_running:
            return
        if self._reconnect_timer.isActive():
            return
        self._reconnect_timer.start()

    def _restart_stream(self) -> None:
        if not self._desired_running or self._stream_item is None:
            return
        self._set_status("reconnecting")
        try:
            self._host.stop()
        except Exception:
            pass
        self.start_stream()

    def _set_status(self, status: str, *, detail: str = "") -> None:
        self._status_text = status
        if detail:
            self.status_label.setText(f"상태: {status} ({detail})")
        else:
            self.status_label.setText(f"상태: {status}")

    def current_status(self) -> str:
        return self._status_text