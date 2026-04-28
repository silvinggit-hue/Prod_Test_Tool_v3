from __future__ import annotations

from enum import Enum


class FirmwareJobState(str, Enum):
    QUEUED = "queued"
    UPLOAD_PENDING = "upload_pending"
    UPLOADING = "uploading"
    REBOOTING = "rebooting"
    RECONNECTING = "reconnecting"
    VERIFYING = "verifying"
    SUCCESS = "success"
    FAILED = "failed"


class FirmwareFailureCode(str, Enum):
    BEFORE_VERSION_UNAVAILABLE = "before_version_unavailable"
    UPLOAD_AUTH_FAILED = "upload_auth_failed"
    UPLOAD_FILE_NOT_FOUND = "upload_file_not_found"
    UPLOAD_HTTP_FAILED = "upload_http_failed"
    UPLOAD_NETWORK_FAILED = "upload_network_failed"
    RECONNECT_TIMEOUT = "reconnect_timeout"
    VERSION_READ_FAILED = "version_read_failed"
    VERSION_UNCHANGED = "version_unchanged"
    UNEXPECTED_ERROR = "unexpected_error"