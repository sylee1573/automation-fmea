#!/usr/bin/env python3
"""
Phase 1: FMEA 메타데이터 자동 태거

excel_scanner.py 출력 CSV를 받아 각 파일 상단을 Claude Haiku로 분석,
공장명/공정유형/고객사/연도 등을 자동 태깅하여 새 CSV로 저장.

실행: python metadata_tagger.py --input 목록표.csv [--output 목록표_tagged.csv] [--limit 10]

비용: claude-haiku-4-5 기준 파일당 ~$0.001 (500개 = ~$0.5)
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import anthropic
import openpyxl

TAG_FIELDS = [
    "태그_공장명", "태그_공정유형", "태그_부품번호",
    "태그_고객사", "태그_작성연도", "태그_양식버전",
    "태그_공정수", "태그_특이사항",
]


def read_excel_preview(file_path: str, max_rows: int = 12) -> str:
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(min_row=1, max_row=max_rows, values_only=True):
            if any(c is not None for c in row):
                rows.append(" | ".join(str(c) if c is not None else "" for c in row[:12]))
        wb.close()
        return "\n".join(rows)
    except Exception as e:
        return f"(읽기 실패: {e})"


def tag_with_claude(client: anthropic.Anthropic, filename: str, preview: str) -> dict:
    prompt = f"""다음 Excel 파일의 상단 내용을 분석하여 메타데이터를 JSON으로 추출해라.
확인 불가 항목은 빈 문자열, 공정수는 정수 0.

파일명: {filename}

파일 상단 내용:
{preview}

추출 항목:
- 공장명: 공장 유형 (예: 프레스공장, 용접공장, 열처리공장, 가공공장, 도장공장, 조립공장)
- 공정유형: 주요 공정 (예: 드로잉, 피어싱, MIG용접, 침탄열처리, CNC선반, 정전도장)
- 부품번호: 도면번호 또는 부품번호
- 고객사: 완성차 업체 (예: 현대자동차, 기아, 한국GM, 르노코리아, 쌍용자동차)
- 작성연도: 4자리 연도
- 양식버전: 버전/개정번호 (예: v1, Rev.3)
- 공정수: 공정 단계 수 (정수)
- 특이사항: 특이한 점 (예: 용접 공정 포함, AP 방식 사용, 특별특성 항목 없음)

JSON만 출력:
{{"공장명":"","공정유형":"","부품번호":"","고객사":"","작성연도":"","양식버전":"","공정수":0,"특이사항":""}}"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in raw:
        raw = raw.split("```", 1)[1].split("```", 1)[0].strip()

    return json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description="Phase 1 — FMEA 메타데이터 자동 태거")
    parser.add_argument("--input", required=True, help="excel_scanner.py 출력 CSV")
    parser.add_argument("--output", default="", help="태깅 결과 CSV (기본: input_tagged.csv)")
    parser.add_argument("--limit", type=int, default=0, help="처리할 최대 파일 수 (테스트: --limit 10)")
    args = parser.parse_args()

    if not args.output:
        p = Path(args.input)
        args.output = str(p.parent / f"{p.stem}_tagged.csv")

    api_key = os.environ.get("ANTHROPIC_API_KEY") or input("Anthropic API 키: ").strip()
    if not api_key:
        sys.exit("오류: API 키 필요")
    client = anthropic.Anthropic(api_key=api_key)

    with open(args.input, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # FMEA 판별된 파일만 태깅 (비FMEA는 빈 태그로 패스)
    target_rows = [r for r in rows if r.get("FMEA_판별") == "O"]
    skip_rows = [r for r in rows if r.get("FMEA_판별") != "O"]

    if args.limit:
        target_rows = target_rows[:args.limit]

    print(f"[Phase 1] 메타데이터 태깅")
    print(f"  태깅 대상: {len(target_rows)}개 (FMEA 판별)  |  건너뜀: {len(skip_rows)}개 (비FMEA)")

    # 비FMEA 파일에 빈 태그 추가
    for r in skip_rows:
        for k in TAG_FIELDS:
            r[k] = ""

    tagged = []
    errors = 0
    for i, row in enumerate(target_rows, 1):
        file_path = str(Path(row.get("경로", "")) / row.get("파일명", ""))
        name = row.get("파일명", "")
        print(f"  [{i:3}/{len(target_rows)}] {name[:45]}", end=" ... ", flush=True)

        preview = read_excel_preview(file_path)
        try:
            meta = tag_with_claude(client, name, preview)
            row.update({
                "태그_공장명":   meta.get("공장명", ""),
                "태그_공정유형": meta.get("공정유형", ""),
                "태그_부품번호": meta.get("부품번호", ""),
                "태그_고객사":   meta.get("고객사", ""),
                "태그_작성연도": meta.get("작성연도", ""),
                "태그_양식버전": meta.get("양식버전", ""),
                "태그_공정수":   meta.get("공정수", ""),
                "태그_특이사항": meta.get("특이사항", ""),
            })
            print("완료")
        except Exception as e:
            print(f"오류: {e}")
            for k in TAG_FIELDS:
                row[k] = ""
            errors += 1

        tagged.append(row)

    all_rows = tagged + skip_rows
    if all_rows:
        with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_rows)

    print(f"\n  태깅 완료. 오류: {errors}건")
    print(f"  결과 저장: {args.output}")
    print("\n  → 다음 단계: python quality_filter.py --input <이 CSV>")
    print("  → 담당자: 태그_공장명, 태그_공정유형, 태그_고객사 확인 후 틀린 항목 직접 수정")


if __name__ == "__main__":
    main()
