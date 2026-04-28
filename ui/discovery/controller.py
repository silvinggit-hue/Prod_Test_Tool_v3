from __future__ import annotations

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from collections.abc import Callable

from infra.discovery.udp_discovery import run_udp_discovery
from ui.discovery.window import DiscoveryRow, DiscoveryWindow


class DiscoveryScanWorker(QObject):
    finished = pyqtSignal(object, object)  # bind_ip, rows
    failed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            bind_ip, devices = run_udp_discovery(
                bind_ip=None,
                mask_bits=24,
                port=64988,
                seconds=4.0,
                repeat=4,
                interval=0.12,
                ignore_self=True,
            )

            rows = [
                DiscoveryRow(
                    selected=True,
                    ip=dev.ip,
                    mac=dev.mac,
                    mac12=dev.mac12,
                    model=dev.model,
                    firmware=dev.firmware,
                    lens=dev.lens,
                    note=dev.note,
                )
                for dev in devices
            ]
            self.finished.emit(bind_ip, rows)

        except Exception as exc:
            self.failed.emit(str(exc))


class DiscoveryController:
    def __init__(
        self,
        *,
        window: DiscoveryWindow,
        on_rows_added: Callable[[list[dict]], None],
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        self.window = window
        self.on_rows_added = on_rows_added
        self.on_log = on_log

        self._thread: QThread | None = None
        self._worker: DiscoveryScanWorker | None = None

    def bind(self) -> None:
        self.window.scan_requested.connect(self._on_scan_requested)
        self.window.stop_requested.connect(self._on_stop_requested)
        self.window.add_selected_requested.connect(self._on_add_selected_requested)
        self.window.add_all_requested.connect(self._on_add_all_requested)

    def _log(self, text: str) -> None:
        if self.on_log is not None:
            self.on_log(text)

    def _on_scan_requested(self) -> None:
        if self._thread is not None:
            self._log("discovery scan already running")
            return

        self.window.clear_results()
        self.window.set_scanning(True)

        self._thread = QThread()
        self._worker = DiscoveryScanWorker()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)

        self._thread.start()
        self._log("UDP discovery started")

    def _on_stop_requested(self) -> None:
        if self._worker is not None:
            self._worker.stop()
        self._log("discovery stop requested")

    def _on_scan_finished(self, bind_ip: str | None, rows: list[DiscoveryRow]) -> None:
        self.window.set_bind_ip(bind_ip)
        self.window.set_results(rows)
        self.window.set_scanning(False)
        self._log(f"UDP discovery finished: {len(rows)} device(s)")

    def _on_scan_failed(self, message: str) -> None:
        self.window.set_scanning(False)
        self._log(f"UDP discovery failed: {message}")

    def _cleanup(self) -> None:
        if self._thread is not None:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None

    def _to_main_rows(self, rows: list[DiscoveryRow]) -> list[dict]:
        out: list[dict] = []
        for row in rows:
            out.append(
                {
                    "ip": row.ip,
                    "port": 0,
                    "note": "discovery",
                    "mac": row.mac,
                    "mac12": row.mac12,
                    "model": row.model,
                    "firmware": row.firmware,
                    "lens": row.lens,
                }
            )
        return out

    def _on_add_selected_requested(self) -> None:
        rows = self.window.selected_results()
        if not rows:
            self._log("discovery add selected: no selected rows")
            return
        self.on_rows_added(self._to_main_rows(rows))
        self._log(f"discovery rows added: {len(rows)}")

    def _on_add_all_requested(self) -> None:
        rows = self.window.all_results()
        if not rows:
            self._log("discovery add all: no rows")
            return
        self.on_rows_added(self._to_main_rows(rows))
        self._log(f"discovery rows added: {len(rows)}")