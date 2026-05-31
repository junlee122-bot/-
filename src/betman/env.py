"""아주 작은 .env 로더 (외부 의존성 없이).

프로젝트 루트의 .env 를 읽어 os.environ 에 없으면 채운다. 이미 환경변수가
설정돼 있으면 그것을 우선한다(컨테이너/CI 주입 우선).
"""

from __future__ import annotations

import os
from pathlib import Path

# src/betman/env.py → 프로젝트 루트
_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: str | Path | None = None) -> None:
    """.env 파일을 읽어 비어있는 환경변수만 채운다."""
    env_path = Path(path) if path else _ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)
