from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AppError(Exception):
    kind: str
    message: str
    status_code: int | None = None
    detail: str | None = None
    phase: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "status_code": self.status_code,
            "detail": self.detail,
            "phase": self.phase,
            "error_code": self.error_code,
        }

    def __str__(self) -> str:
        base = f"{self.kind}: {self.message}"
        if self.status_code is not None:
            base += f" (status={self.status_code})"
        if self.phase:
            base += f" (phase={self.phase})"
        if self.error_code:
            base += f" (code={self.error_code})"
        if self.detail:
            base += f" | {self.detail}"
        return base