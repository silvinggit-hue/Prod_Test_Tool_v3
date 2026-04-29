from __future__ import annotations

from dataclasses import dataclass

from domain.errors.app_error import AppError


@dataclass(frozen=True)
class ProbeResult:
    base_url: str
    root_path: str
    auth_scheme: str
    flavor: str = "legacy"


@dataclass(frozen=True)
class Phase1Request:
    ip: str
    port: int = 0

    # 초기화 직후 기본값
    username: str = "admin"
    password: str = "1234"

    # 참고용 후보군.
    # 실제 connect_service에서는 입력값이 1234인지 아닌지로 분기해서 사용한다.
    password_candidates: tuple[str, ...] = ("1234", "admin", "123", "!camera1108", "!Camera1108")

    # legacy/basic/TTA 최종 운영 비밀번호
    # - 기본 펌웨어: 123
    # - TTA: !camera1108
    target_password: str = "123"

    verify_tls: bool = False

    # Security 3.0 운영 계정
    sec3_username: str = "TruenTest"
    sec3_password: str = "!Camera1108"
    allowed_ip: str = "192.168.10.2"


@dataclass(frozen=True)
class Phase1Response:
    ok: bool

    base_url: str | None = None
    root_path: str | None = None
    auth_scheme: str | None = None
    flavor: str | None = None

    sys_version: str | None = None
    effective_username: str | None = None
    effective_password: str | None = None

    recovered: bool = False
    default_password_state: bool | None = None
    password_changed: bool | None = None

    error: AppError | None = None