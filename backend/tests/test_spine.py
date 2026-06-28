"""
spine + consistency_checker 단위 테스트 (API·orchestrator 불필요).

실행:  python -m backend.tests.test_spine
spine·consistency_checker만 import → anthropic/openpyxl 등 무거운 의존성 없음.
"""

from backend.agents import spine as S
from backend.validators import consistency_checker as C


# ── 픽스처: 동일 특성("볼트홀 직경")이 과소/과대 두 failure_mode 행에 반복 ──────────
FMEA = {
    "rows": [
        {"process_number": "10", "process_step": "블랭킹",
         "function": "코일 절단", "special_characteristic": "", "failure_mode": "오투입"},
        {"process_number": "40", "process_step": "피어싱",
         "function": "볼트홀 직경", "special_characteristic": "CC",
         "failure_mode": "직경 과소"},
        {"process_number": "40", "process_step": "피어싱",
         "function": "볼트홀 직경", "special_characteristic": "CC",
         "failure_mode": "직경 과대"},
        {"process_number": "60", "process_step": "최종검사",
         "function": "표면 조도", "special_characteristic": "SC",
         "failure_mode": "조도 불량"},
    ]
}


def test_build_spine_ids_and_dedupe():
    spine = S.build_spine(FMEA)
    pids = [p["id"] for p in spine["processes"]]
    assert pids == ["P10", "P40", "P60"], pids

    cids = [c["id"] for c in spine["special_characteristics"]]
    # 볼트홀 직경은 두 행이지만 dedupe → SC-40-1 하나. 표면조도 → SC-60-1.
    assert cids == ["SC-40-1", "SC-60-1"], cids

    sc40 = spine["special_characteristics"][0]
    assert sc40["type"] == "CC" and sc40["process_id"] == "P40"
    assert sc40["descriptor"] == "볼트홀 직경"


def test_stamp_ids():
    spine = S.build_spine(FMEA)
    stamped = S.stamp_ids(FMEA, spine)
    rows = stamped["rows"]
    assert rows[0]["process_id"] == "P10" and rows[0]["char_id"] == ""
    # 중복 두 CC 행 모두 같은 char_id로 스탬프
    assert rows[1]["char_id"] == "SC-40-1"
    assert rows[2]["char_id"] == "SC-40-1"
    assert rows[3]["char_id"] == "SC-60-1"
    # 원본 불변
    assert "process_id" not in FMEA["rows"][0]


def test_seed_and_merge_fills_ok():
    spine = S.build_spine(FMEA)
    stubs = S.seed_special_rows(spine)
    assert {s["char_id"] for s in stubs} == {"SC-40-1", "SC-60-1"}

    fills = {
        "SC-40-1": {"specification": "φ12 +0.1/-0.0", "measurement_method": "핀게이지"},
        "SC-60-1": {"specification": "Ra 1.6", "measurement_method": "조도계"},
    }
    rows, issues = S.merge_fills(stubs, fills)
    assert issues == []
    r40 = next(r for r in rows if r["char_id"] == "SC-40-1")
    # 정체성 보존 + 서술 병합
    assert r40["characteristic_name"] == "볼트홀 직경"
    assert r40["specification"] == "φ12 +0.1/-0.0"


def test_merge_fills_detects_missing_and_phantom():
    spine = S.build_spine(FMEA)
    stubs = S.seed_special_rows(spine)
    fills = {
        "SC-40-1": {"specification": "φ12"},
        "SC-99-9": {"specification": "허수"},  # spine에 없는 키
        # SC-60-1 누락
    }
    rows, issues = S.merge_fills(stubs, fills)
    joined = " ".join(issues)
    assert "누락: SC-60-1" in joined, issues
    assert "허수: SC-99-9" in joined, issues


def test_identity_column_not_overwritten_by_fill():
    """fill이 char_id/characteristic_name을 덮어쓰려 해도 stub이 이김."""
    spine = S.build_spine(FMEA)
    stubs = S.seed_special_rows(spine)
    fills = {"SC-40-1": {"char_id": "HACKED", "characteristic_name": "조작",
                         "specification": "ok"},
             "SC-60-1": {"specification": "ok"}}
    rows, issues = S.merge_fills(stubs, fills)
    r40 = next(r for r in rows if r["process_number"] == "40")
    assert r40["char_id"] == "SC-40-1"
    assert r40["characteristic_name"] == "볼트홀 직경"


# ── consistency_checker (ID 동일성) ──────────────────────────────────────────────

def _cp_from_spine(spine, drop_char=None, swap_char=None, drop_proc=None):
    """spine을 충실히 반영한 CP dict 생성(테스트용). 옵션으로 결함 주입."""
    rows = []
    for p in spine["processes"]:
        if drop_proc and p["id"] == drop_proc:
            continue
        rows.append({"process_number": p["number"], "process_id": p["id"],
                     "characteristic_name": "일반특성", "char_id": ""})
    for c in spine["special_characteristics"]:
        cid = c["id"]
        if drop_proc and c["process_id"] == drop_proc:
            continue
        if drop_char and cid == drop_char:
            continue
        if swap_char and cid == swap_char:
            cid = "SC-99-9"  # 다른 특성으로 치환
        rows.append({"process_number": c["process_id"][1:], "process_id": c["process_id"],
                     "characteristic_name": c["descriptor"], "char_id": cid})
    return {"rows": rows}


def test_check_passes_when_consistent():
    spine = S.build_spine(FMEA)
    cp = _cp_from_spine(spine)
    insp = _cp_from_spine(spine)
    ws = _cp_from_spine(spine)
    assert C.check(FMEA, cp, ws, insp, spine) == []


def test_check_detects_char_substitution():
    """치환: char_id가 다른 값으로 바뀌면 (구 검사기는 통과하던 케이스) 검출."""
    spine = S.build_spine(FMEA)
    cp = _cp_from_spine(spine, swap_char="SC-40-1")
    issues = C.check(FMEA, cp, None, None, spine)
    assert any("[FMEA_CP]" in i and "SC-40-1" in i for i in issues), issues


def test_check_detects_char_missing_in_inspection():
    spine = S.build_spine(FMEA)
    cp = _cp_from_spine(spine)
    insp = _cp_from_spine(spine, drop_char="SC-60-1")
    issues = C.check(FMEA, cp, None, insp, spine)
    assert any("[CP_INSP]" in i and "SC-60-1" in i for i in issues), issues


def test_check_detects_process_missing_in_ws():
    """[CP_WS] — 현재(구) 검사기엔 미구현이던 케이스."""
    spine = S.build_spine(FMEA)
    cp = _cp_from_spine(spine)
    ws = _cp_from_spine(spine, drop_proc="P40")
    issues = C.check(FMEA, cp, ws, None, spine)
    assert any("[CP_WS]" in i and "P40" in i for i in issues), issues


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
