from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from domain.errors.app_error import AppError
from infra.discovery.setip_protocol import (
    default_template96,
    normalize_mac12,
    run_setip,
)


@dataclass(frozen=True)
class SetIpItem:
    mac12: str
    new_ip: str
    gw: str | None = None
    netmask: str | None = None


@dataclass(frozen=True)
class SetIpRequest:
    mac12: str
    new_ip: str
    bind_ip: str | None = None
    mask_bits: int = 24
    port: int = 64988
    gw: str | None = None
    netmask: str | None = None
    retries: int = 1
    ack_wait_sec: float = 0.35
    confirm_announce_sec: float = 0.0


@dataclass(frozen=True)
class SetIpResult:
    ok: bool
    mac12: str
    new_ip: str
    ack_seen: bool = False
    announce_seen: bool = False
    announced_ip: str | None = None
    error_kind: str = ""
    error_message: str = ""
    error_detail: str = ""


@dataclass(frozen=True)
class BatchSetIpRequest:
    items: list[SetIpItem]
    bind_ip: str | None = None
    mask_bits: int = 24
    port: int = 64988
    retries: int = 1
    ack_wait_sec: float = 0.35
    confirm_announce_sec: float = 0.0


@dataclass(frozen=True)
class BatchSetIpResult:
    ok: bool
    results: dict[str, SetIpResult]


class SetIpService:
    def __init__(self) -> None:
        self.template96 = default_template96()

    def change_ip(
        self,
        request: SetIpRequest,
        *,
        stop_requested: Callable[[], bool] | None = None,
    ) -> SetIpResult:
        mac12 = normalize_mac12(request.mac12)

        try:
            ok, ack_seen, announce_seen, announced_ip = run_setip(
                bind_ip=request.bind_ip,
                mask_bits=request.mask_bits,
                port=request.port,
                target_mac12=mac12,
                new_ip=request.new_ip,
                gw=request.gw,
                netmask=request.netmask,
                retries=request.retries,
                ack_wait_sec=request.ack_wait_sec,
                confirm_announce_sec=request.confirm_announce_sec,
                template96=self.template96,
                stop_requested=stop_requested,
            )

            # 현장 기준:
            # setip 단계에서는 ACK만 오면 "요청 전달 성공"으로 본다.
            final_ok = bool(ok or ack_seen)

            return SetIpResult(
                ok=final_ok,
                mac12=mac12,
                new_ip=request.new_ip,
                ack_seen=ack_seen,
                announce_seen=announce_seen,
                announced_ip=announced_ip,
                error_kind="" if final_ok else "setip",
                error_message="" if final_ok else "장비 응답 없음",
                error_detail="" if final_ok else "ACK를 확인하지 못했습니다.",
            )

        except AppError as exc:
            return SetIpResult(
                ok=False,
                mac12=mac12,
                new_ip=request.new_ip,
                error_kind=exc.kind,
                error_message=exc.message,
                error_detail=exc.detail or "",
            )
        except Exception as exc:
            return SetIpResult(
                ok=False,
                mac12=mac12,
                new_ip=request.new_ip,
                error_kind="setip",
                error_message="setip crashed",
                error_detail=str(exc),
            )

    def change_ip_batch(
        self,
        request: BatchSetIpRequest,
        *,
        stop_requested: Callable[[], bool] | None = None,
    ) -> BatchSetIpResult:
        # 현장 속도 기준:
        # batch 최종 확인까지 오래 기다리지 말고
        # 장비별로 짧게 요청만 전달한다.
        results: dict[str, SetIpResult] = {}

        items = list(request.items)
        for idx, item in enumerate(items):
            if stop_requested and stop_requested():
                break

            single_result = self.change_ip(
                SetIpRequest(
                    mac12=item.mac12,
                    new_ip=item.new_ip,
                    bind_ip=request.bind_ip,
                    mask_bits=request.mask_bits,
                    port=request.port,
                    gw=item.gw,
                    netmask=item.netmask,
                    retries=request.retries,
                    ack_wait_sec=request.ack_wait_sec,
                    confirm_announce_sec=request.confirm_announce_sec,
                ),
                stop_requested=stop_requested,
            )
            results[normalize_mac12(item.mac12)] = single_result

            # 다음 장비로 넘어가기 전 짧게만 쉰다.
            if idx < len(items) - 1:
                time.sleep(0.05)

        all_ok = bool(results) and all(item.ok for item in results.values())
        return BatchSetIpResult(
            ok=all_ok,
            results=results,
        )