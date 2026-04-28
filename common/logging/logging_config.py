from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

from config.constants import (
    APP_LOG_FILENAME,
    DEFAULT_LOG_DIR,
    DEFAULT_LOG_LEVEL_NAME,
)

_LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s - %(message)s"
_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES: Final[int] = 5 * 1024 * 1024
_BACKUP_COUNT: Final[int] = 5


def _normalize_level(level: int | str | None) -> int:
    if level is None:
        return logging.getLevelName(DEFAULT_LOG_LEVEL_NAME)

    if isinstance(level, int):
        return level

    level_name = str(level).strip().upper() or DEFAULT_LOG_LEVEL_NAME
    return getattr(logging, level_name, logging.INFO)


def setup_logging(
    *,
    log_dir: str | Path | None = None,
    level: int | str | None = None,
    filename: str = APP_LOG_FILENAME,
) -> Path:
    resolved_level = _normalize_level(level)
    resolved_dir = Path(log_dir) if log_dir is not None else DEFAULT_LOG_DIR
    resolved_dir.mkdir(parents=True, exist_ok=True)

    log_path = resolved_dir / filename
    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    file_handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(resolved_level)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    return log_path