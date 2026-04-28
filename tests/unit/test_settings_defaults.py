from __future__ import annotations

from config.app_settings import AppSettings
from config.firmware_settings import FirmwareSettings
from config.scheduler_settings import SchedulerSettings
from config.ui_settings import UiSettings


def test_app_settings_defaults_match_current_operation() -> None:
    settings = AppSettings.load()

    assert settings.default_port == 0
    assert settings.verify_tls is False

    assert settings.firmware_credentials.username == "admin"
    assert settings.firmware_credentials.password == "123"

    assert settings.tta_credentials.username == "admin"
    assert settings.tta_credentials.password == "!camera1108"

    assert settings.security3_credentials.username == "TruenTest"
    assert settings.security3_credentials.password == "!camera1108"

    assert settings.default_username == "admin"
    assert settings.default_password == "123"
    assert settings.target_password == "!camera1108"
    assert settings.sec3_username == "TruenTest"
    assert settings.sec3_password == "!camera1108"


def test_scheduler_defaults() -> None:
    settings = SchedulerSettings.load()

    assert settings.global_http_max == 16
    assert settings.max_inflight_per_device == 1
    assert settings.hot_page_size == 10


def test_ui_defaults() -> None:
    settings = UiSettings.load()

    assert settings.device_page_size == 10
    assert settings.ui_flush_ms == 100
    assert "ip" in settings.default_visible_columns
    assert "firmware" in settings.default_visible_columns


def test_firmware_defaults() -> None:
    settings = FirmwareSettings.load()

    assert settings.upload_parallelism_default == 16
    assert settings.upload_parallelism_max == 24
    assert settings.reboot_wait_sec == 40.0
    assert settings.reconnect_interval_sec == 2.0
    assert settings.reconnect_timeout_sec == 120.0
    assert settings.verify_max_attempts == 3
    assert settings.verify_interval_sec == 3.0