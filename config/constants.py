from __future__ import annotations

from pathlib import Path

APP_NAME = "Prod_Test_Tool_v3"
APP_DISPLAY_NAME = "Prod Test Tool v3"
APP_ORG_NAME = "Truen"

APP_LOG_FILENAME = "prod_test_tool_v3.log"

DEFAULT_LOG_DIR_NAME = "logs"
DEFAULT_LOG_LEVEL_NAME = "INFO"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = PROJECT_ROOT / DEFAULT_LOG_DIR_NAME