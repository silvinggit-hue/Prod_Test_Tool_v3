from __future__ import annotations

from typing import Callable

from infra.reset.truen_reset_service import (
    BatchResetItem,
    BatchResetRequest,
    BatchResetResult,
    ResetRequest,
    ResetResult,
    TruenResetService,
)


class ResetService:
    def __init__(self, *, impl: TruenResetService | None = None) -> None:
        self.impl = impl or TruenResetService()

    def reset(
        self,
        request: ResetRequest,
        *,
        stop_requested: Callable[[], bool] | None = None,
    ) -> ResetResult:
        return self.impl.reset(request, stop_requested=stop_requested)

    def reset_batch(
        self,
        request: BatchResetRequest,
        *,
        stop_requested: Callable[[], bool] | None = None,
    ) -> BatchResetResult:
        return self.impl.reset_batch(request, stop_requested=stop_requested)


__all__ = [
    "ResetService",
    "ResetRequest",
    "ResetResult",
    "BatchResetItem",
    "BatchResetRequest",
    "BatchResetResult",
]