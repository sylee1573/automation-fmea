"""
spine — 공유 엔티티 ID 레이어 (경량 온톨로지)

FMEA를 엔티티 source-of-truth로 삼아 공정·특별특성에 안정적 ID를 부여한다.
정체성(ID·descriptor)은 코드가 100% 소유하며 LLM은 ID를 생성/echo하지 않는다.
순수 함수만 — LLM·외부 의존성 없음.

ID 규칙:
  process_id = "P" + process_number          (예: "10" → "P10")
  char_id    = "SC-{process_number}-{seq}"    (CC/SC 행, 공정 내 1부터)

dedupe:
  동일 특성이 여러 failure_mode 행에 반복돼도 char_id 하나만 생성한다.
  키 = (process_number, 정규화 descriptor). 정규화는 FMEA 내부 행끼리만 적용하는
  whitespace/대소문자 정확 비교(문서 간 의미 매칭 아님).
"""

from __future__ import annotations


# 특별특성 행에서 descriptor로 쓸 필드 우선순위
def _descriptor(row: dict) -> str:
    text = str(row.get("function", "")).strip()
    if not text:
        text = str(row.get("failure_mode", "")).strip()
    return text


def _normalize(text: str) -> str:
    """dedupe 비교용 정규화 — 공백 축약 + 소문자."""
    return " ".join(str(text).split()).lower()


def _is_special(row: dict) -> bool:
    return str(row.get("special_characteristic", "")).strip().upper() in ("CC", "SC")


def build_spine(fmea: dict | None) -> dict:
    """
    FMEA dict에서 spine을 결정론적으로 추출.

    Returns:
        {
          "processes": [{"id","number","name"}],
          "special_characteristics": [{"id","process_id","type","descriptor","spec"}],
        }
    """
    spine = {"processes": [], "special_characteristics": []}
    if not fmea:
        return spine

    rows = fmea.get("rows", []) or []

    # ── processes: 등장 순서 유지, 번호별 첫 행의 process_step을 name으로 ──────────
    seen_pnum: set[str] = set()
    for row in rows:
        pnum = str(row.get("process_number", "")).strip()
        if not pnum or pnum in seen_pnum:
            continue
        seen_pnum.add(pnum)
        spine["processes"].append({
            "id": f"P{pnum}",
            "number": pnum,
            "name": str(row.get("process_step", "")).strip(),
        })

    # ── special_characteristics: (process_number, 정규화 descriptor) dedupe ──────
    seq_by_pnum: dict[str, int] = {}
    seen_char: dict[tuple[str, str], str] = {}
    for row in rows:
        if not _is_special(row):
            continue
        pnum = str(row.get("process_number", "")).strip()
        if not pnum:
            continue
        descriptor = _descriptor(row)
        key = (pnum, _normalize(descriptor))
        if key in seen_char:
            continue
        seq = seq_by_pnum.get(pnum, 0) + 1
        seq_by_pnum[pnum] = seq
        char_id = f"SC-{pnum}-{seq}"
        seen_char[key] = char_id
        spine["special_characteristics"].append({
            "id": char_id,
            "process_id": f"P{pnum}",
            "type": str(row.get("special_characteristic", "")).strip().upper(),
            "descriptor": descriptor,
            "spec": "",
        })

    return spine


def stamp_ids(fmea: dict, spine: dict) -> dict:
    """
    FMEA rows에 process_id(전부)·char_id(CC/SC 매칭) 주입.
    원본을 변경하지 않고 얕은 복사본을 반환한다.
    """
    if not fmea:
        return fmea

    # (process_number, 정규화 descriptor) → char_id 역인덱스
    char_lookup: dict[tuple[str, str], str] = {}
    for sc in spine.get("special_characteristics", []):
        pnum = sc["process_id"][1:]  # "P10" → "10"
        char_lookup[(pnum, _normalize(sc["descriptor"]))] = sc["id"]

    new_rows = []
    for row in fmea.get("rows", []) or []:
        new_row = dict(row)
        pnum = str(row.get("process_number", "")).strip()
        new_row["process_id"] = f"P{pnum}" if pnum else ""
        if _is_special(row) and pnum:
            new_row["char_id"] = char_lookup.get((pnum, _normalize(_descriptor(row))), "")
        else:
            new_row["char_id"] = ""
        new_rows.append(new_row)

    result = dict(fmea)
    result["rows"] = new_rows
    return result


def seed_special_rows(spine: dict, process_number: str | None = None) -> list[dict]:
    """
    CC/SC 시드 stub 목록(정체성 칼럼만). 에이전트가 채울 비정체성 필드는 비워 둔다.
    process_number 지정 시 해당 공정만 필터.
    """
    stubs = []
    for sc in spine.get("special_characteristics", []):
        if process_number is not None and sc["process_id"][1:] != str(process_number):
            continue
        stubs.append({
            "char_id": sc["id"],
            "process_id": sc["process_id"],
            "process_number": sc["process_id"][1:],
            "characteristic_name": sc["descriptor"],
            "special_characteristic": sc["type"],
        })
    return stubs


def merge_fills(stubs: list[dict], fills: dict) -> tuple[list[dict], list[str]]:
    """
    char_id 키로 stub(정체성) + 에이전트 fill(서술) 병합.

    Args:
        stubs: seed_special_rows 결과
        fills: {char_id: {<비정체성 필드>}} — 에이전트 출력

    Returns:
        (병합 행 목록, 문제 메시지 목록)
          문제: 누락 키(fill 없음) / 허수 키(stub에 없는 char_id)
    """
    fills = fills or {}
    valid_ids = {s["char_id"] for s in stubs}
    issues: list[str] = []

    rows: list[dict] = []
    for stub in stubs:
        cid = stub["char_id"]
        fill = fills.get(cid)
        if not isinstance(fill, dict):
            issues.append(f"누락: {cid} 채움값 없음")
            fill = {}
        row = dict(stub)
        # 정체성 칼럼은 fill이 덮어쓰지 못하게 stub을 마지막에 적용
        merged = {**fill, **row}
        rows.append(merged)

    for cid in fills:
        if cid not in valid_ids:
            issues.append(f"허수: {cid}는 spine에 없는 char_id")

    return rows, issues


def assemble_rows(parsed: dict, spine: dict, process_number=None) -> tuple[list[dict], list[str]]:
    """
    에이전트 출력(parsed = {rows:[일반], special_fills:{char_id:{...}}})을 최종 행으로 조립.

      - 일반 행: process_number 정확일치로 process_id 스탬프, char_id="".
      - 특별특성 행: seed_special_rows + merge_fills(정체성은 코드 소유).

    Returns: (최종 행 목록, 문제 메시지 목록)
    """
    general = []
    for row in parsed.get("rows", []) or []:
        new_row = dict(row)
        pnum = str(row.get("process_number", "")).strip()
        new_row["process_id"] = f"P{pnum}" if pnum else ""
        new_row["char_id"] = ""
        general.append(new_row)

    stubs = seed_special_rows(spine, process_number=process_number)
    special, issues = merge_fills(stubs, parsed.get("special_fills"))

    return general + special, issues


def format_spine_for_prompt(spine: dict) -> str:
    """프롬프트용 '필수 참조 목록' — 압축 없이 verbatim."""
    procs = spine.get("processes", [])
    chars = spine.get("special_characteristics", [])

    lines = ["## [공유 엔티티 목록] — ID는 아래 표기를 글자 그대로 사용할 것\n"]

    lines.append("### 공정 (process_id)")
    if procs:
        for p in procs:
            lines.append(f"- {p['id']}  (공정번호 {p['number']}: {p['name']})")
    else:
        lines.append("- (없음)")

    lines.append("\n### 특별특성 (char_id)")
    if chars:
        for c in chars:
            lines.append(
                f"- {c['id']}  [{c['type']}] {c['process_id']} — {c['descriptor']}"
            )
    else:
        lines.append("- (없음)")

    return "\n".join(lines)
