from __future__ import annotations

import platform

try:
    import vlc  # type: ignore
except Exception:
    vlc = None


class VlcVideoHost:
    def __init__(self) -> None:
        self.instance = None
        self.player = None
        self.media = None
        self._last_error = ""

    @staticmethod
    def is_available() -> bool:
        return vlc is not None

    def start(self, *, url: str, widget_id: int) -> tuple[bool, str]:
        self.stop()

        if vlc is None:
            self._last_error = "VLC unavailable"
            return False, self._last_error

        try:
            self.instance = vlc.Instance(
                "--no-video-title-show",
                "--quiet",
                "--network-caching=300",
                "--live-caching=300",
                "--rtsp-tcp",
                "--drop-late-frames",
                "--skip-frames",
            )
            self.player = self.instance.media_player_new()
            self.media = self.instance.media_new(url)
            self.player.set_media(self.media)
            self._attach_window(widget_id)

            result = self.player.play()
            if result == -1:
                self._last_error = "play failed"
                self.stop()
                return False, self._last_error

            return True, ""
        except Exception as exc:
            self._last_error = str(exc)
            self.stop()
            return False, self._last_error

    def stop(self) -> None:
        try:
            if self.player is not None:
                self.player.stop()
        except Exception:
            pass

        self.media = None
        self.player = None
        self.instance = None

    def poll_state(self) -> tuple[str, str]:
        if vlc is None:
            return "error", "VLC unavailable"

        if self.player is None:
            return "stopped", ""

        try:
            state = self.player.get_state()
            state_text = str(state).lower()
        except Exception as exc:
            return "error", str(exc)

        if "opening" in state_text or "buffering" in state_text:
            return "starting", ""
        if "playing" in state_text:
            return "playing", ""
        if "ended" in state_text or "stopped" in state_text:
            return "stopped", ""
        if "error" in state_text:
            return "error", self._last_error or "stream error"

        return "starting", ""

    def _attach_window(self, widget_id: int) -> None:
        if self.player is None:
            return

        system_name = platform.system().lower()

        if "windows" in system_name:
            self.player.set_hwnd(int(widget_id))
            return

        if "darwin" in system_name or "mac" in system_name:
            self.player.set_nsobject(int(widget_id))
            return

        self.player.set_xwindow(int(widget_id))