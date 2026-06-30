"""
Template 렌더러 — 고객사가 업로드한 실제 Excel 양식을 틀로 사용해 데이터를 채운다.

config 렌더러가 양식을 '코드로 그리는' 반면, 이 렌더러는 고객사 원본 양식 파일
(헤더·로고·서식·컬럼폭 그대로)을 열어 데이터 행만 채워 넣는다.

프로파일 형식 (profiles/*.json):
  {
    "renderer": "template",
    "template": {
      "fmea": {
        "path": "templates/mtk.xlsm",     # backend/output 기준 상대경로 또는 절대경로
        "sheet": "PFMEA",
        "data_start_row": 11,
        "columns": {"process_step": 2, "failure_mode": 3, "S": 5, ...},  # field→열번호
        "meta_cells": {"C7": "part_number", "C8": "part_name"}            # 선택
      }
    }
  }
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Side

_TEMPLATE_BASE = Path(__file__).parent.parent  # backend/output


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (_TEMPLATE_BASE / p)


def _thin_border() -> Border:
    s = Side(style="thin", color="BBBBBB")
    return Border(left=s, right=s, top=s, bottom=s)


def render(doc_type: str, data: dict, profile: dict, output_path: str) -> Path:
    """고객사 양식 템플릿에 data["rows"]를 채워 저장."""
    tpl_cfg = (profile.get("template") or {}).get(doc_type)
    if not tpl_cfg:
        # 이 문서 타입에 템플릿이 없으면 config 렌더러로 폴백
        from . import config_renderer
        return config_renderer.render(doc_type, data, profile, output_path)

    tpl_path = _resolve(tpl_cfg["path"])
    if not tpl_path.exists():
        raise FileNotFoundError(f"양식 템플릿 없음: {tpl_path}")

    keep_vba = tpl_path.suffix.lower() == ".xlsm"
    wb = openpyxl.load_workbook(tpl_path, keep_vba=keep_vba)

    sheet = tpl_cfg.get("sheet")
    ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb.active

    columns: dict = {str(k): int(v) for k, v in tpl_cfg["columns"].items()}
    start = int(tpl_cfg.get("data_start_row", 2))
    max_col = max(columns.values(), default=ws.max_column)
    border = _thin_border()

    # 데이터 영역(헤더 아래) 병합 해제 + 기존 내용 지우기
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= start:
            ws.unmerge_cells(str(rng))
    for r in range(start, (ws.max_row or start) + 1):
        for c in range(1, max_col + 1):
            ws.cell(row=r, column=c).value = None

    # 데이터 채우기
    rows = data.get("rows", [])
    for i, row in enumerate(rows):
        r = start + i
        for field, col in columns.items():
            val = row.get(field, "")
            # MTK처럼 예방/검출 관리가 한 칸인 경우: 예방이 비면 검출로 대체
            if field == "prevention_controls" and not val:
                val = row.get("detection_controls", "") or ""
            # 빈 값은 건너뜀 — 같은 컬럼에 여러 필드가 매핑된 경우(process_step/function)
            # 빈 필드가 이미 채운 값을 덮어쓰지 않도록 보호
            if val in (None, ""):
                continue
            cell = ws.cell(row=r, column=col, value=val)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            cell.border = border

    # 메타 셀 채우기 (품번/품명/차종 등)
    for cell_ref, field in (tpl_cfg.get("meta_cells") or {}).items():
        v = data.get(field, "")
        if v:
            try:
                ws[cell_ref] = v
            except Exception:
                pass

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    wb.close()
    return Path(output_path)
