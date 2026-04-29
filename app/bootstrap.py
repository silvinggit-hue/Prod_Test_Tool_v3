from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtWidgets import QApplication

from application.core.app_supervisor import AppSupervisor
from ui.main.controller import MainWindowController
from ui.main.window import MainWindow


@dataclass(frozen=True)
class BootstrapResult:
    app: QApplication
    window: MainWindow
    supervisor: AppSupervisor
    controller: MainWindowController


class Bootstrap:
    def __init__(self, app: QApplication) -> None:
        self.app = app

    def build(self) -> BootstrapResult:
        supervisor = AppSupervisor()
        supervisor.start()

        window = MainWindow()
        controller = MainWindowController(
            window=window,
            supervisor=supervisor,
        )
        controller.bind()

        self.app.aboutToQuit.connect(supervisor.stop)

        # 런타임 동안 참조 유지
        window._supervisor = supervisor
        window._controller = controller

        return BootstrapResult(
            app=self.app,
            window=window,
            supervisor=supervisor,
            controller=controller,
        )