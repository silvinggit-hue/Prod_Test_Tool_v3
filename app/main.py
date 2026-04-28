from __future__ import annotations

from app.runtime import run_application


def main() -> int:
    return run_application()


if __name__ == "__main__":
    raise SystemExit(main())