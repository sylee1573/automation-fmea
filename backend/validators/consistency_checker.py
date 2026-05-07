"""
정합성 검증기 — FMEA ↔ CP ↔ 작업표준서 ↔ 자주검사 항목 일치 확인

반환 형식: list[str]
  - "[FMEA_CP] ..." → CP 에이전트 재실행 필요
  - "[CP_WS] ..."   → 작업표준서 에이전트 재실행 필요
  - "[CP_INSP] ..." → 자주검사 에이전트 재실행 필요
"""

from __future__ import annotations


def _get_process_numbers(data: dict | None) -> set[str]:
    if not data:
        return set()
    return {str(r.get("process_number", "")).strip() for r in data.get("rows", [])} - {""}


def _get_cc_sc_by_process(data: dict | None, process_key: str = "process_number") -> dict[str, list[str]]:
    """공정번호 → CC/SC 항목명 리스트 매핑"""
    if not data:
        return {}
    result: dict[str, list[str]] = {}
    for row in data.get("rows", []):
        sc = str(row.get("special_characteristic", "")).upper()
        if sc not in ("CC", "SC"):
            continue
        pnum = str(row.get(process_key, "")).strip()
        name_key = "failure_mode" if "failure_mode" in row else "characteristic_name"
        name = str(row.get(name_key, row.get("inspection_item", ""))).strip()
        result.setdefault(pnum, []).append(f"{sc}:{name}")
    return result


def check(
    fmea: dict | None,
    cp: dict | None,
    work_standard: dict | None,
    inspection: dict | None,
) -> list[str]:
    """
    문서 간 정합성 검증.

    검증 항목:
      1. FMEA 공정번호 ↔ CP 공정번호 일치
      2. FMEA CC/SC 항목 → CP 특별특성 누락 없는지
      3. CP CC/SC 특별특성 → 자주검사 항목 누락 없는지

    Returns:
        불일치 설명 문자열 목록 (비어 있으면 정합성 통과)
    """
    issues: list[str] = []

    # ── 검증 1: 공정번호 일치 ───────────────────────────────────────────────────
    if fmea and cp:
        fmea_pnums = _get_process_numbers(fmea)
        cp_pnums = _get_process_numbers(cp)

        in_fmea_not_cp = fmea_pnums - cp_pnums
        in_cp_not_fmea = cp_pnums - fmea_pnums

        if in_fmea_not_cp:
            nums = ", ".join(sorted(in_fmea_not_cp))
            issues.append(f"[FMEA_CP] FMEA에 있지만 CP에 없는 공정번호: {nums}")
        if in_cp_not_fmea:
            nums = ", ".join(sorted(in_cp_not_fmea))
            issues.append(f"[FMEA_CP] CP에 있지만 FMEA에 없는 공정번호: {nums}")

    # ── 검증 2: FMEA CC/SC → CP 특별특성 ──────────────────────────────────────
    if fmea and cp:
        fmea_cc_sc = _get_cc_sc_by_process(fmea, "process_number")
        cp_cc_sc = _get_cc_sc_by_process(cp, "process_number")

        for pnum, fmea_items in fmea_cc_sc.items():
            cp_items = cp_cc_sc.get(pnum, [])
            fmea_sc_types = {item.split(":")[0] for item in fmea_items}
            cp_sc_types = {item.split(":")[0] for item in cp_items}

            missing = fmea_sc_types - cp_sc_types
            if missing:
                issues.append(
                    f"[FMEA_CP] 공정 {pnum}: FMEA의 {missing} 항목이 CP 특별특성에 누락"
                )

    # ── 검증 3: CP CC/SC → 자주검사 ────────────────────────────────────────────
    if cp and inspection:
        cp_cc_sc = _get_cc_sc_by_process(cp, "process_number")
        insp_pnums = _get_process_numbers(inspection)
        insp_cc_sc = _get_cc_sc_by_process(inspection, "process_number")

        for pnum, cp_items in cp_cc_sc.items():
            cp_sc_types = {item.split(":")[0] for item in cp_items}
            insp_items = insp_cc_sc.get(pnum, [])
            insp_sc_types = {item.split(":")[0] for item in insp_items}

            if pnum not in insp_pnums:
                issues.append(
                    f"[CP_INSP] 공정 {pnum}: CP의 CC/SC 항목이 있지만 자주검사에 공정 없음"
                )
            else:
                missing = cp_sc_types - insp_sc_types
                if missing:
                    issues.append(
                        f"[CP_INSP] 공정 {pnum}: CP의 {missing} 항목이 자주검사에 누락"
                    )

    return issues
