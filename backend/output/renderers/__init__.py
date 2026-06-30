"""
렌더러 디스패치 — 회사 프로파일이 지정한 렌더러로 문서를 그린다.

렌더러 선택 우선순위:
  1. doc 설정의 "renderer"  (문서별 오버라이드)
  2. 프로파일 최상위 "renderer"
  3. "config" (기본)
"""

from __future__ import annotations

from pathlib import Path

from . import config_renderer


def render(doc_type: str, data: dict, profile: dict, output_path: str) -> Path:
    doc_cfg = profile.get(doc_type, {})
    renderer = doc_cfg.get("renderer") or profile.get("renderer", "config")

    if renderer == "template":
        from . import template_renderer  # 지연 임포트 (Phase 3)
        return template_renderer.render(doc_type, data, profile, output_path)

    return config_renderer.render(doc_type, data, profile, output_path)
