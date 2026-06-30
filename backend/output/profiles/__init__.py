"""
회사 출력 프로파일 로더.

profiles/*.json 각 파일은 한 회사(또는 default)의 출력 양식 정의.
매칭: 프로파일의 "company" 또는 "aliases" 목록이 customer와 일치하면 채택.
미존재 시 default.json 으로 폴백.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PROFILE_DIR = Path(__file__).parent
DEFAULT_PROFILE = "default"


@lru_cache(maxsize=1)
def _load_all() -> dict[str, dict]:
    """profiles/*.json 전체를 company명 → 프로파일 dict 로 적재."""
    profiles: dict[str, dict] = {}
    for jf in PROFILE_DIR.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        key = data.get("company", jf.stem)
        profiles[key] = data
        for alias in data.get("aliases", []):
            profiles[alias] = data
    return profiles


def load_profile(customer: str | None = None) -> dict:
    """customer에 맞는 프로파일 반환. 미일치 시 default."""
    profiles = _load_all()
    if customer and customer in profiles:
        return profiles[customer]
    if DEFAULT_PROFILE in profiles:
        return profiles[DEFAULT_PROFILE]
    raise FileNotFoundError(
        f"기본 프로파일(default.json)이 {PROFILE_DIR}에 없습니다."
    )
