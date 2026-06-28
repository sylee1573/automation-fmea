"""
정합성 검증기 — spine(공유 엔티티 ID) 기준 FMEA ↔ CP ↔ 작업표준서 ↔ 자주검사 동일성 확인

타입 집합 비교가 아니라 **ID 동일성**으로 검증한다 → 누락·치환 동시 검출.

반환 형식: list[str]
  - "[FMEA_CP] ..." → CP 에이전트 재실행 필요
  - "[CP_WS] ..."   → 작업표준서 에이전트 재실행 필요
  - "[CP_INSP] ..." → 자주검사 에이전트 재실행 필요
"""

from __future__ import annotations


def _process_ids(data: dict | None) -> set[str]:
    """행의 process_id 집합. 구 스키마(미스탬프) graceful: process_number로 유도."""
    if not data:
        return set()
    ids: set[str] = set()
    for row in data.get("rows", []):
        pid = str(row.get("process_id", "")).strip()
        if not pid:
            pnum = str(row.get("process_number", "")).strip()
            pid = f"P{pnum}" if pnum else ""
        if pid:
            ids.add(pid)
    return ids


def _char_ids(data: dict | None) -> set[str]:
    """행의 char_id 집합(빈 값 제외)."""
    if not data:
        return set()
    return {
        str(row.get("char_id", "")).strip()
        for row in data.get("rows", [])
    } - {""}


def check(
    fmea: dict | None,
    cp: dict | None,
    work_standard: dict | None,
    inspection: dict | None,
    spine: dict | None = None,
) -> list[str]:
    """
    spine 기준 문서 간 정합성 검증.

    검증 항목:
      1. 공정 커버리지 — spine processes의 모든 process_id가 CP/WS/자주검사에 존재
      2. 특별특성 동일성 — spine special_characteristics의 모든 char_id가 CP·자주검사에 존재

    spine이 없으면 검증을 건너뛴다(빈 목록 반환).

    Returns:
        불일치 설명 문자열 목록 (비어 있으면 정합성 통과)
    """
    if not spine:
        return []

    issues: list[str] = []

    spine_pids = {p["id"] for p in spine.get("processes", [])}
    spine_cids = {c["id"] for c in spine.get("special_characteristics", [])}

    # ── 검증 1: 공정 커버리지 ────────────────────────────────────────────────────
    coverage = [
        (cp, "[FMEA_CP]", "CP"),
        (work_standard, "[CP_WS]", "작업표준서"),
        (inspection, "[CP_INSP]", "자주검사"),
    ]
    for doc, label, name in coverage:
        if doc is None:
            continue
        missing = spine_pids - _process_ids(doc)
        if missing:
            nums = ", ".join(sorted(missing))
            issues.append(f"{label} {name}에 누락된 공정: {nums}")

    # ── 검증 2: 특별특성 동일성 (CP·자주검사) ───────────────────────────────────
    char_targets = [
        (cp, "[FMEA_CP]", "CP"),
        (inspection, "[CP_INSP]", "자주검사"),
    ]
    for doc, label, name in char_targets:
        if doc is None:
            continue
        missing = spine_cids - _char_ids(doc)
        if missing:
            ids = ", ".join(sorted(missing))
            issues.append(f"{label} {name}에 누락·치환된 특별특성(char_id): {ids}")

    return issues
