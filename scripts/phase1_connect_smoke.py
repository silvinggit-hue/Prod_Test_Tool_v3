from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from application.services.connect_service import run_phase1
from config.app_settings import AppSettings
from domain.models.phase1 import Phase1Request


def _to_bool(text: str) -> bool:
    return str(text).strip().lower() in ("1", "true", "yes", "y", "on")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase1 connect smoke")
    parser.add_argument("--ip", required=True)
    parser.add_argument("--port", type=int, default=0)

    parser.add_argument("--user", default="admin")

    # 초기화 직후 기본값
    parser.add_argument("--password", default="1234")

    # legacy/basic/TTA 최종 운영 비밀번호
    # 기본 펌웨어면 123, TTA면 !camera1108
    parser.add_argument("--target-password", default="123")

    parser.add_argument("--verify-tls", default="false")

    parser.add_argument("--sec3-user", default="TruenTest")
    parser.add_argument("--sec3-password", default="!Camera1108")

    args = parser.parse_args()

    settings = AppSettings.load()
    req = Phase1Request(
        ip=args.ip,
        port=args.port,
        username=args.user,
        password=args.password,
        password_candidates=("1234", "admin", "123", "!camera1108", "!Camera1108"),
        target_password=args.target_password,
        verify_tls=_to_bool(args.verify_tls),
        sec3_username=args.sec3_user,
        sec3_password=args.sec3_password,
        allowed_ip=settings.allowed_ip,
    )

    resp = run_phase1(req, settings=settings)

    payload = {
        "ok": resp.ok,
        "base_url": resp.base_url,
        "root_path": resp.root_path,
        "auth_scheme": resp.auth_scheme,
        "flavor": resp.flavor,
        "sys_version": resp.sys_version,
        "effective_username": resp.effective_username,
        "effective_password": resp.effective_password,
        "recovered": resp.recovered,
        "default_password_state": resp.default_password_state,
        "password_changed": resp.password_changed,
        "error": (resp.error.to_dict() if resp.error else None),
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if resp.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())