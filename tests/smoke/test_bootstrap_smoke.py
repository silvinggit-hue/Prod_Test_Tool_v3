from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.runtime import initialize_runtime
from config.constants import APP_LOG_FILENAME, APP_NAME


def test_bootstrap_smoke(tmp_path: Path) -> None:
    built = initialize_runtime(argv=[APP_NAME], log_dir=tmp_path)

    assert built.app is not None
    assert built.window is not None
    assert built.window.windowTitle()

    built.window.show()
    built.app.processEvents()

    logging.getLogger(__name__).info("bootstrap smoke test log entry")
    built.app.processEvents()

    log_path = tmp_path / APP_LOG_FILENAME
    assert log_path.exists()
    assert built.app.applicationName() == APP_NAME

    built.window.close()
    built.app.processEvents()