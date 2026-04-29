from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Sequence

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

from config.constants import APP_DISPLAY_NAME, APP_NAME, APP_ORG_NAME, APP_ICON_PATH
from app.bootstrap import Bootstrap, BootstrapResult
from common.logging.logging_config import setup_logging
from config.constants import APP_DISPLAY_NAME, APP_NAME, APP_ORG_NAME


def _log_uncaught_exception(
    *,
    logger: logging.Logger,
    prefix: str,
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback,
) -> None:
    logger.critical("%s %s", prefix, exc_value)
    logger.critical(
        "Unhandled exception traceback:\n%s",
        "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
    )


def install_global_exception_hooks() -> None:
    logger = logging.getLogger(__name__)

    def _global_excepthook(exc_type, exc_value, exc_traceback) -> None:
        _log_uncaught_exception(
            logger=logger,
            prefix="[FATAL] Unhandled exception:",
            exc_type=exc_type,
            exc_value=exc_value,
            exc_traceback=exc_traceback,
        )

    def _threading_excepthook(args: threading.ExceptHookArgs) -> None:
        _log_uncaught_exception(
            logger=logger,
            prefix="[FATAL][THREAD] Unhandled exception:",
            exc_type=args.exc_type,
            exc_value=args.exc_value,
            exc_traceback=args.exc_traceback,
        )

    sys.excepthook = _global_excepthook
    threading.excepthook = _threading_excepthook


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is not None:
        return app

    qt_args = list(argv) if argv is not None else list(sys.argv)
    app = QApplication(qt_args)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setOrganizationName(APP_ORG_NAME)
    app.setQuitOnLastWindowClosed(True)

    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))

    return app


def initialize_runtime(
    *,
    argv: Sequence[str] | None = None,
    log_dir: str | Path | None = None,
    log_level: int | str | None = None,
) -> BootstrapResult:
    # Step 0 런타임에서는 offscreen을 자동 강제하지 않는다.
    # 테스트 쪽에서만 필요하면 개별 테스트가 직접 설정한다.
    setup_logging(log_dir=log_dir, level=log_level)
    install_global_exception_hooks()

    app = create_application(argv)
    return Bootstrap(app).build()


def run_application(
    *,
    argv: Sequence[str] | None = None,
    log_dir: str | Path | None = None,
    log_level: int | str | None = None,
) -> int:
    built = initialize_runtime(argv=argv, log_dir=log_dir, log_level=log_level)
    built.window.show()
    built.window.raise_()
    built.window.activateWindow()
    return built.app.exec_()