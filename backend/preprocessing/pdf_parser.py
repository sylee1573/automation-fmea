#!/usr/bin/env python3
"""
Phase 2: 도면 PDF 파서

PyMuPDF로 도면 PDF에서 치수/공차/재질/특기사항 추출.
스캔 이미지 PDF는 텍스트 추출 불가 — 해당 사실을 결과에 표시.

실행: python pdf_parser.py --file <도면.pdf> [--output parsed.json]
"""

import argparse
import json
import re
from pathlib import Path

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

# ─── 정규식 패턴 ──────────────────────────────────────────────────────────────

# 치수 패턴: φ12 +0.1/-0.0, 285 ± 0.5, 25±0.5
_DIM_PATTERN = re.compile(
    r"(?:φ|Φ|R|SR|M)?\s*"          # 직경/반경/나사 접두사 (선택)
    r"(\d+(?:\.\d+)?)"              # 기본값
    r"\s*"
    r"("
    r"[±]\s*\d+(?:\.\d+)?"         # ± 공차
    r"|[+]\d+(?:\.\d+)?/[-]\d+(?:\.\d+)?"   # +/-공차
    r"|[-]\d+(?:\.\d+)?/[+]\d+(?:\.\d+)?"   # -/+공차
    r"|[+]\d+(?:\.\d+)?/-0(?:\.0+)?"        # +0.x/-0.0
    r")?"
    r"\s*(?:mm|㎜)?",
    re.IGNORECASE,
)

# 재질 패턴 (국내 자동차 부품 주요 강종)
_MATERIAL_PATTERNS = [
    r"SPFC\d+[A-Z]?",     # 고강도 냉연
    r"SPFH\d+[A-Z]?",     # 고강도 열연
    r"SPHC",              # 열연연강
    r"SPCC",              # 냉연연강
    r"SGACC?",            # 용융아연도금
    r"SCP[A-Z]\d+",       # 석도강판
    r"SS\d+",             # 일반구조용강
    r"S[0-9]+C",          # 기계구조용 탄소강
    r"SCM\d+",            # 크롬몰리강
    r"SCr\d+",            # 크롬강
    r"SKD\d+",            # 합금공구강
    r"A\d{4}[A-Z]?",      # 알루미늄합금
    r"ADC\d+",            # 다이캐스팅 Al
    r"STS\d+[A-Z]?",      # 스테인리스
    r"SUS\d+[A-Z]?",      # 스테인리스(일)
    r"[A-Z]{2,4}\d{3,4}", # 일반 강종 코드
]
_MATERIAL_RE = re.compile("|".join(_MATERIAL_PATTERNS))

# 표면조도 패턴: Ra 3.2, Rz 12.5
_ROUGHNESS_RE = re.compile(r"R[az]\s*\d+(?:\.\d+)?", re.IGNORECASE)

# 특별특성 키워드
_SC_KEYWORDS = ["특별특성", "cc", "sc", "critical", "significant", "★", "◆", "△"]


def extract_text_from_pdf(file_path: str) -> tuple[str, bool]:
    """PDF 텍스트 추출. 반환: (text, is_scanned)"""
    if not HAS_FITZ:
        return "(PyMuPDF 미설치 — pip install pymupdf)", False

    doc = fitz.open(file_path)
    pages_text = []
    for page in doc:
        pages_text.append(page.get_text())
    doc.close()

    full_text = "\n".join(pages_text)
    is_scanned = len(full_text.strip()) < 100  # 텍스트 거의 없으면 스캔 이미지 가능성
    return full_text, is_scanned


def parse_dimensions(text: str) -> list[dict]:
    """치수·공차 추출"""
    dims = []
    seen = set()
    for m in _DIM_PATTERN.finditer(text):
        value = m.group(1)
        tolerance = (m.group(2) or "").strip()
        context_start = max(0, m.start() - 20)
        context = text[context_start:m.end() + 10].replace("\n", " ")

        # 극소값 제외 (도면 번호, 날짜 등 오탐)
        if float(value) < 0.1 or float(value) > 9999:
            continue

        key = f"{value}{tolerance}"
        if key in seen:
            continue
        seen.add(key)

        # 직경 여부
        prefix_start = max(0, m.start() - 3)
        prefix = text[prefix_start:m.start()]
        is_diameter = bool(re.search(r"[φΦ]", prefix))

        dims.append({
            "value": value,
            "tolerance": tolerance,
            "is_diameter": is_diameter,
            "context": context.strip(),
        })

    return dims


def parse_materials(text: str) -> list[str]:
    """재질 코드 추출 (중복 제거)"""
    found = _MATERIAL_RE.findall(text)
    return list(dict.fromkeys(found))  # 순서 유지 중복 제거


def parse_roughness(text: str) -> list[str]:
    """표면조도 요구사항 추출"""
    found = _ROUGHNESS_RE.findall(text)
    return list(set(found))


def parse_special_characteristics(text: str) -> list[str]:
    """특별특성 관련 텍스트 추출"""
    lines = text.split("\n")
    sc_lines = []
    for line in lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in _SC_KEYWORDS):
            stripped = line.strip()
            if stripped and len(stripped) < 200:
                sc_lines.append(stripped)
    return sc_lines


def guess_part_info(text: str) -> dict:
    """부품번호/부품명 추정"""
    info = {"part_number": "", "part_name": ""}

    # 부품번호 패턴 (영문+숫자 조합, 5~15자)
    pn_match = re.search(
        r"(?:부품번호|품번|P/N|PART\s*NO\.?|도번)\s*[:\s]\s*([A-Z0-9\-]+)",
        text, re.IGNORECASE
    )
    if pn_match:
        info["part_number"] = pn_match.group(1).strip()

    # 부품명 패턴
    name_match = re.search(
        r"(?:부품명|품명|PART\s*NAME|제품명)\s*[:\s]\s*([^\n\r]{2,40})",
        text, re.IGNORECASE
    )
    if name_match:
        info["part_name"] = name_match.group(1).strip()

    return info


def parse_drawing_pdf(file_path: str) -> dict:
    """
    도면 PDF 파싱.
    Returns:
        file_path, text_raw, part_number, part_name, materials,
        dimensions, surface_roughness, special_characteristics,
        is_scanned, warnings
    """
    if not Path(file_path).exists():
        return {"error": f"파일 없음: {file_path}"}

    text, is_scanned = extract_text_from_pdf(file_path)
    warnings = []

    if is_scanned:
        warnings.append("스캔 이미지 PDF — 텍스트 추출 불가. 치수 정보를 수동으로 입력하거나 OCR 처리 필요.")

    part_info = guess_part_info(text)
    materials = parse_materials(text)
    dimensions = parse_dimensions(text) if not is_scanned else []
    roughness = parse_roughness(text) if not is_scanned else []
    sc_lines = parse_special_characteristics(text) if not is_scanned else []

    if not materials:
        warnings.append("재질 코드 미감지 — 도면 텍스트에서 강종 정보를 찾을 수 없음.")
    if not dimensions:
        warnings.append("치수 정보 미감지.")

    return {
        "file_path": str(Path(file_path).resolve()),
        "part_number": part_info["part_number"],
        "part_name": part_info["part_name"],
        "materials": materials,
        "dimensions": dimensions[:30],   # 최대 30개
        "surface_roughness": roughness,
        "special_characteristics": sc_lines,
        "is_scanned": is_scanned,
        "text_raw": text[:4000] if not is_scanned else "",
        "warnings": warnings,
    }


def parse(content: bytes, use_vision: bool = False) -> dict:
    """
    bytes로 받은 PDF 내용을 파싱 (main.py FastAPI 업로드 어댑터).
    임시 파일에 쓴 후 parse_drawing_pdf() 호출.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = parse_drawing_pdf(tmp_path)
        # 텍스트 필드를 'text' 키로 통일
        result["text"] = result.pop("text_raw", "")
        return result
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Phase 2 — 도면 PDF 파서")
    parser.add_argument("--file", required=True, help="도면 PDF 파일")
    parser.add_argument("--output", default="", help="JSON 출력 파일")
    args = parser.parse_args()

    if not HAS_FITZ:
        print("오류: PyMuPDF 미설치. pip install pymupdf")
        return

    result = parse_drawing_pdf(args.file)

    if "error" in result:
        print(f"오류: {result['error']}")
        return

    print(f"[pdf_parser] {Path(args.file).name}")
    print(f"  스캔 이미지: {'예' if result['is_scanned'] else '아니오'}")
    print(f"  부품번호: {result['part_number'] or '(미감지)'}")
    print(f"  재질: {result['materials'] or '(미감지)'}")
    print(f"  치수 수: {len(result['dimensions'])}개")
    print(f"  표면조도: {result['surface_roughness'] or '(미감지)'}")
    print(f"  특별특성 관련 행: {len(result['special_characteristics'])}개")
    for w in result["warnings"]:
        print(f"  ⚠ {w}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  저장: {args.output}")


if __name__ == "__main__":
    main()
