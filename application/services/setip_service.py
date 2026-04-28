from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from domain.errors.app_error import AppError
from infra.discovery.setip_protocol import (
    default_template96,
    normalize_mac12,
    run_setip,
    run_setip_batch,
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
    retries: int = 2
    ack_wait_sec: float = 1.0
    confirm_announce_sec: float = 0.8


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
    retries: int = 2
    ack_wait_sec: float = 1.0
    confirm_announce_sec: float = 0.8


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
            return SetIpResult(
                ok=ok,
                mac12=mac12,
                new_ip=request.new_ip,
                ack_seen=ack_seen,
                announce_seen=announce_seen,
                announced_ip=announced_ip,
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
        try:
            raw_targets = [
                {
                    "mac12": item.mac12,
                    "new_ip": item.new_ip,
                    "gw": item.gw,
                    "netmask": item.netmask,
                }
                for item in request.items
            ]

            raw = run_setip_batch(
                bind_ip=request.bind_ip,
                mask_bits=request.mask_bits,
                port=request.port,
                targets=raw_targets,
                retries=request.retries,
                ack_wait_sec=request.ack_wait_sec,
                confirm_announce_sec=request.confirm_announce_sec,
                template96=self.template96,
                stop_requested=stop_requested,
            )

            results: dict[str, SetIpResult] = {}
            for item in request.items:
                mac12 = normalize_mac12(item.mac12)
                ok = bool(raw.get(mac12, False))
                results[mac12] = SetIpResult(
                    ok=ok,
                    mac12=mac12,
                    new_ip=item.new_ip,
                    ack_seen=ok,
                    announce_seen=ok,
                    announced_ip=item.new_ip if ok else None,
                )

            return BatchSetIpResult(
                ok=all(result.ok for result in results.values()) if results else False,
                results=results,
            )
        except Exception as exc:
            return BatchSetIpResult(
                ok=False,
                results={},
            )