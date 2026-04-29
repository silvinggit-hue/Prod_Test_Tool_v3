from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TimeoutSettings:
    connect_sec: float = 3.0
    read_sec: float = 6.0


@dataclass(frozen=True)
class RetrySettings:
    max_attempts: int = 2
    backoff_base_sec: float = 0.25
    backoff_jitter_sec: float = 0.15
    retry_on_status: tuple[int, ...] = (502, 503, 504)


@dataclass(frozen=True)
class CredentialSettings:
    username: str
    password: str


@dataclass(frozen=True)
class AppSettings:
    default_port: int = 0  # 0 = auto
    verify_tls: bool = False
    allowed_ip: str = "192.168.10.2"

    timeout: TimeoutSettings = field(default_factory=TimeoutSettings)
    retry: RetrySettings = field(default_factory=RetrySettings)

    firmware_credentials: CredentialSettings = field(
        default_factory=lambda: CredentialSettings(username="admin", password="123")
    )
    tta_credentials: CredentialSettings = field(
        default_factory=lambda: CredentialSettings(username="admin", password="!camera1108")
    )
    security3_credentials: CredentialSettings = field(
        default_factory=lambda: CredentialSettings(username="TruenTest", password="!camera1108")
    )

    @property
    def default_username(self) -> str:
        return self.firmware_credentials.username

    @property
    def default_password(self) -> str:
        return self.firmware_credentials.password

    @property
    def target_password(self) -> str:
        # 현재 운영 기준에서 TTA / 보안 3.0 최종 비밀번호는 동일하다.
        return self.tta_credentials.password

    @property
    def sec3_username(self) -> str:
        return self.security3_credentials.username

    @property
    def sec3_password(self) -> str:
        return self.security3_credentials.password

    @property
    def tta_username(self) -> str:
        return self.tta_credentials.username

    @property
    def tta_password(self) -> str:
        return self.tta_credentials.password

    @classmethod
    def load(cls) -> "AppSettings":
        return cls()