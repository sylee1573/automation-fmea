"""
FMEA Agent — PFMEA 생성 (AIAG FMEA 4th Ed. / RPN 방식)
모델: claude-sonnet-4-6
"""

import json
import anthropic

MODEL = "claude-sonnet-4-6"

# ─── 시스템 프롬프트 (poc/fmea_poc.py 동일) ────────────────────────────────────
SYSTEM_PROMPT = """너는 자동차 부품 제조 공정의 PFMEA(공정 고장유형 및 영향분석) 전문가다.
AIAG FMEA 4th Edition 기준을 따른다.
위험도는 RPN(Risk Priority Number = S×O×D) 방식을 사용한다.
출력은 반드시 유효한 JSON만 출력한다. 설명 텍스트나 마크다운 코드블록 외부에 아무것도 추가하지 않는다."""

BUILTIN_FEWSHOT = """
예시 1
- process_number: "10" / process_step: "블랭킹" / process_work_element: "소재 투입"
- function: "코일 소재를 설계 치수로 절단" / special_characteristic: ""
- effect_end_user: "블랭크 형상 불량 → 후공정 치수 이탈" / S: 7
- effect_manufacturing: "금형 손상 / 후공정 자재 손실"
- failure_mode: "소재 방향 오투입" / cause: "투입 방향 표시 미흡"
- O: 3 / prevention_controls: "소재 투입 방향 보조 지그 설치"
- detection_controls: "초물 치수 검사 (버니어 캘리퍼스)" / D: 3 / RPN: 63
- recommended_action: "소재 방향 감지 센서 추가 검토"

예시 2 (CC 특별특성)
- process_number: "40" / process_step: "피어싱" / process_work_element: "볼트홀 가공"
- function: "볼트홀 φ12 +0.1/-0.0mm 가공" / special_characteristic: "CC"
- effect_end_user: "볼트 체결 불가 → 차량 안전사고" / S: 9
- effect_manufacturing: "조립 라인 정지 / 납기 지연"
- failure_mode: "볼트홀 직경 과소 또는 과대" / cause: "펀치 마모 / 다이 클리어런스 부적정"
- O: 2 / prevention_controls: "펀치 교체 기준 수립 (마모 한계 치수)"
- detection_controls: "핀 게이지 전수검사 (통과/불통과)" / D: 2 / RPN: 36
- recommended_action: "자동 핀 게이지 설비 도입 검토 (S≥9 안전 항목 → 필수)"

예시 3
- process_number: "60" / process_step: "최종 검사" / process_work_element: "치수 전수 검사"
- function: "설계 치수 내 합격품만 출하 승인" / special_characteristic: ""
- effect_end_user: "고객 클레임 / 반품" / S: 8
- effect_manufacturing: "불량 재작업 비용 증가"
- failure_mode: "불량품 유출" / cause: "검사 절차서 미준수"
- O: 2 / prevention_controls: "측정 결과 전산 입력 의무화"
- detection_controls: "측정 데이터 실시간 SPC 모니터링" / D: 5 / RPN: 80
- recommended_action: "측정 장비 RS-232 자동 수집 연동"
"""

PROMPT_TEMPLATE = """## 분석 대상

{scenario}

{similar_section}
---

위 부품과 공정에 대해 PFMEA를 작성해라.

규칙:
- 각 공정 단계마다 2~4개의 주요 고장유형 도출
- 특별특성은 special_characteristic 필드에 "CC" 또는 "SC" 기입 (없으면 빈 문자열)
- 고장 영향을 effect_end_user(최종 사용자)와 effect_manufacturing(제조 영향) 두 가지로 구분
- process_number는 10, 20, 30... (같은 공정의 여러 항목은 동일 번호)
- RPN 산출: RPN = S × O × D (반드시 세 값의 곱과 일치하는 정수)
- 권고 조치(recommended_action):
  - RPN ≥ 100 이거나 S ≥ 9(안전·법규 관련)인 항목은 권고 조치를 반드시 기입
  - 그 외 항목은 필요 시에만 기입하고 없으면 빈 문자열
- 문서 메타데이터(fmea_no, vehicle_model, supplier, doc_no, revision)는 입력에서
  파악되면 채우고, 모르면 빈 문자열
- responsibility, target_date, status, action_taken, revised_S/O/D/RPN,
  prepared_by, checked_by, approved_by는 빈 문자열

출력 형식:
```json
{{
  "part_name": "",
  "part_number": "",
  "customer": "",
  "fmea_no": "",
  "vehicle_model": "",
  "supplier": "",
  "doc_no": "",
  "revision": "",
  "prepared_by": "",
  "checked_by": "",
  "approved_by": "",
  "rows": [
    {{
      "process_number": "10",
      "process_step": "공정명",
      "process_work_element": "작업 요소",
      "function": "기능/요구사항",
      "special_characteristic": "CC/SC/빈문자열",
      "effect_end_user": "최종 사용자 고장 영향",
      "S": 0,
      "effect_manufacturing": "제조 공정 영향",
      "failure_mode": "고장유형",
      "cause": "고장 원인",
      "O": 0,
      "prevention_controls": "예방 관리 방법(PC)",
      "detection_controls": "검출 관리 방법(DC)",
      "D": 0,
      "RPN": 0,
      "recommended_action": "권고 조치",
      "responsibility": "",
      "target_date": "",
      "status": "",
      "action_taken": "",
      "revised_S": "",
      "revised_O": "",
      "revised_D": "",
      "revised_RPN": ""
    }}
  ]
}}
```"""

# 해외 고객용: 내용 필드를 영어로 생성 (숫자·코드·부품번호는 유지)
EN_DIRECTIVE = """

## LANGUAGE REQUIREMENT
Write ALL textual field values in ENGLISH: process_step, process_work_element,
function, special_characteristic notes, effect_end_user, effect_manufacturing,
failure_mode, cause, prevention_controls, detection_controls, recommended_action.
Use standard AIAG PFMEA terminology. Keep part numbers, codes (CC/SC), and all
numeric scores (S/O/D/RPN) unchanged."""


def _build_scenario(process_data: dict) -> str:
    parts = []
    if process_data.get("part_name"):
        parts.append(f"부품명: {process_data['part_name']}")
    if process_data.get("part_number"):
        parts.append(f"부품번호: {process_data['part_number']}")
    if process_data.get("customer"):
        parts.append(f"고객사: {process_data['customer']}")
    if process_data.get("drawing_text"):
        parts.append(f"\n[도면]\n{process_data['drawing_text']}")
    if process_data.get("process_text"):
        parts.append(f"\n[공정검토서]\n{process_data['process_text']}")
    return "\n".join(parts)


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    return json.loads(text)


def _enforce_rpn(data: dict) -> dict:
    """RPN = S×O×D 강제 재계산. revised_S/O/D가 모두 채워졌으면 revised_RPN도 산출."""
    for row in data.get("rows", []):
        try:
            row["RPN"] = int(row.get("S", 0)) * int(row.get("O", 0)) * int(row.get("D", 0))
        except (TypeError, ValueError):
            row["RPN"] = 0
        rs, ro, rd = row.get("revised_S"), row.get("revised_O"), row.get("revised_D")
        if all(str(v).strip() not in ("", "None") for v in (rs, ro, rd)):
            try:
                row["revised_RPN"] = int(rs) * int(ro) * int(rd)
            except (TypeError, ValueError):
                row["revised_RPN"] = ""
    return data


async def generate(
    process_data: dict,
    wiki_rules: str,
    similar_cases: str,
    client: anthropic.AsyncAnthropic,
    language: str = "ko",
) -> dict:
    """
    PFMEA JSON 생성.

    Args:
        process_data: {drawing_text, process_text, part_name, part_number, customer, process_type}
        wiki_rules: LLM Wiki 내용 (프롬프트 캐싱 적용)
        similar_cases: RAG 검색 결과 포맷된 문자열
        client: AsyncAnthropic 인스턴스

    Returns:
        RPN 방식 PFMEA dict (문서 메타데이터 + rows)
    """
    scenario = _build_scenario(process_data)
    similar_section = f"\n{similar_cases}\n" if similar_cases else ""

    user_prompt = PROMPT_TEMPLATE.format(
        scenario=scenario,
        similar_section=similar_section,
    )
    if language == "en":
        user_prompt += EN_DIRECTIVE

    content_blocks = []

    if wiki_rules:
        content_blocks.append({
            "type": "text",
            "text": f"## FMEA 작성 룰셋 (LLM Wiki)\n\n{wiki_rules}",
            "cache_control": {"type": "ephemeral"},
        })

    content_blocks.append({
        "type": "text",
        "text": f"## PFMEA 작성 예시 (few-shot)\n\n{BUILTIN_FEWSHOT}\n\n---",
        "cache_control": {"type": "ephemeral"},
    })

    content_blocks.append({
        "type": "text",
        "text": user_prompt,
    })

    async with client.messages.stream(
        model=MODEL,
        max_tokens=64000,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": content_blocks}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    ) as stream:
        msg = await stream.get_final_message()

    _log_cache_usage(msg.usage, "FMEA")
    return _enforce_rpn(_parse_json(msg.content[0].text))


def _log_cache_usage(usage, agent_name: str):
    created = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    if created:
        print(f"  [{agent_name}] 캐시 저장: {created:,} 토큰")
    if read:
        print(f"  [{agent_name}] 캐시 히트: {read:,} 토큰 절감")
