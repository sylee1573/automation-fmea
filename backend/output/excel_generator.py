"""
Excel 생성 진입점 — 회사 프로파일에 따라 4종(FMEA·CP·작업표준서·자주검사) 생성.

내용(정규 데이터)과 양식(렌더링)을 분리한다:
  - 데이터는 에이전트가 생성한 정규 dict (RPN 방식, 문서 메타데이터 포함)
  - 양식은 회사 프로파일(profiles/*.json)이 결정 → renderers 로 디스패치

사용:
  from backend.output.excel_generator import generate_all
  files = generate_all(fmea, cp, work_standard, inspection,
                       output_dir="output/", customer="현대자동차")
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from . import renderers
from .profiles import load_profile


def _output_path(output_dir: str, prefix: str, part_number: str, ext: str = "xlsx") -> Path:
    safe_pn = part_number.replace("/", "-").replace("\\", "-") or "unknown"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(output_dir) / f"{prefix}_{safe_pn}_{ts}.{ext}"


# 문서 타입 → (출력 파일 prefix)
_DOC_PREFIX = {
    "fmea": "PFMEA",
    "cp": "CP",
    "work_standard": "WS",
    "inspection": "INSP",
}


def generate_all(
    fmea: Optional[dict],
    cp: Optional[dict],
    work_standard: Optional[dict],
    inspection: Optional[dict],
    output_dir: str = "output",
    customer: str = "",
    profile: Optional[dict] = None,
) -> list[Path]:
    """
    회사 프로파일에 맞춰 4종 Excel 파일 생성.

    Args:
        fmea, cp, work_standard, inspection: 각 문서 정규 dict (None이면 생략)
        output_dir: 저장 폴더
        customer: 고객사명 (프로파일 매칭 키). profile 인자가 있으면 무시.
        profile: 명시적 프로파일 dict (없으면 customer로 조회, 미일치 시 default)

    Returns:
        생성된 파일 경로 목록
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    if profile is None:
        profile = load_profile(customer)

    docs = {
        "fmea": fmea,
        "cp": cp,
        "work_standard": work_standard,
        "inspection": inspection,
    }

    outputs: list[Path] = []
    for doc_type, data in docs.items():
        if not data:
            continue
        doc_cfg = profile.get(doc_type, {})
        renderer = doc_cfg.get("renderer") or profile.get("renderer", "config")
        ext = "xlsm" if renderer == "template" else "xlsx"
        path = _output_path(output_dir, _DOC_PREFIX[doc_type], data.get("part_number", ""), ext)
        outputs.append(renderers.render(doc_type, data, profile, str(path)))

    return outputs
