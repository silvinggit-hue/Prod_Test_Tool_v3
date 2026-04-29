from __future__ import annotations

from dataclasses import dataclass

from domain.enums.firmware import FirmwareFailureCode
from domain.errors.app_error import AppError


@dataclass(frozen=True)
class FirmwareError(AppError):
    failure_code: FirmwareFailureCode = FirmwareFailureCode.UNEXPECTED_ERROR

    def __post_init__(self) -> None:
        super().__post_init__()