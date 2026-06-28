"""
CP Agent — Control Plan(관리계획서) 생성
모델: claude-haiku-4-5-20251001
입력: FMEA 압축 요약 → CC/SC·고RPN(≥100) 항목 자동 반영
"""

import json
import anthropic

from . import spine as spine_mod

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """너는 자동차 부품 제조 공정의 관리계획서(Control Plan) 전문가다.
AIAG APQP & Control Plan 매뉴얼 기준을 따른다.
PFMEA 결과를 기반으로 관리계획서를 작성한다.
출력은 반드시 유효한 JSON만 출력한다. 설명 텍스트나 마크다운 코드블록 외부에 아무것도 추가하지 않는다."""

PROMPT_TEMPLATE = """## 부품 정보
부품명: {part_name}
부품번호: {part_number}
고객사: {customer}

## 공정 정보
{process_text}

## PFMEA 핵심 요약 (고RPN 항목 반영)
{fmea_summary}

{spine_text}

---

위 정보를 바탕으로 관리계획서(Control Plan)를 작성해라.

규칙:
- 일반(특별특성 아님) 제품특성·공정특성은 rows 배열에 직접 작성한다.
- **CC/SC 특별특성 행은 rows에 만들지 마라.** 대신 위 [공유 엔티티 목록]의 char_id별로
  special_fills 객체에 비정체성 필드만 채운다. char_id·특성명·공정ID는 코드가 소유하므로
  네가 생성하거나 변경하지 마라. 목록에 없는 char_id를 새로 만들지 마라.
- PFMEA의 고RPN(RPN≥100) 또는 S≥9 항목은 전수검사(100%) 또는 자동화 검출 방법으로 관리
- sample_size: "5개/회" 형식, frequency: "매 2시간", "초물/종물" 형식
- measurement_method: 구체적인 측정 기기명 포함 (예: "버니어 캘리퍼스 ±0.05mm")

출력 형식:
```json
{{
  "part_name": "",
  "part_number": "",
  "customer": "",
  "rows": [
    {{
      "process_number": "10",
      "process_name": "공정명",
      "machine": "설비명",
      "characteristic_type": "제품/공정",
      "characteristic_name": "관리 특성명 (일반 특성만)",
      "special_characteristic": "",
      "specification": "관리 규격 (예: 12.0+0.1/-0.0mm)",
      "measurement_method": "측정 방법 및 기기",
      "sample_size": "샘플 크기",
      "frequency": "검사 주기",
      "control_method": "관리 방법 (SPC/LPA/육안 등)",
      "reaction_plan": "이상 발생 시 조치"
    }}
  ],
  "special_fills": {{
    "SC-40-1": {{
      "process_name": "공정명",
      "machine": "설비명",
      "characteristic_type": "제품/공정",
      "specification": "관리 규격",
      "measurement_method": "측정 방법 및 기기",
      "sample_size": "샘플 크기",
      "frequency": "검사 주기",
      "control_method": "관리 방법",
      "reaction_plan": "이상 발생 시 조치"
    }}
  }}
}}
```"""


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    return json.loads(text)


async def generate(
    process_data: dict,
    fmea_summary: str,
    wiki_rules: str,
    client: anthropic.AsyncAnthropic,
    spine: dict = None,
    spine_text: str = "",
) -> dict:
    """
    Control Plan JSON 생성 (코드 시드: 특별특성 정체성은 코드 소유).

    Args:
        process_data: {drawing_text, process_text, part_name, part_number, customer, process_type}
        fmea_summary: FMEA 압축 요약 (서술 — 고RPN 항목 포함)
        wiki_rules: LLM Wiki 내용 (프롬프트 캐싱 적용)
        client: AsyncAnthropic 인스턴스
        spine: 공유 엔티티 ID 레이어 (build_spine 결과)
        spine_text: spine 프롬프트 문자열 (format_spine_for_prompt)

    Returns:
        Control Plan dict (CC/SC 행은 spine char_id로 조립됨)
    """
    user_prompt = PROMPT_TEMPLATE.format(
        part_name=process_data.get("part_name", ""),
        part_number=process_data.get("part_number", ""),
        customer=process_data.get("customer", ""),
        process_text=process_data.get("process_text", ""),
        fmea_summary=fmea_summary,
        spine_text=spine_text,
    )

    content_blocks = []

    if wiki_rules:
        content_blocks.append({
            "type": "text",
            "text": f"## CP 작성 룰셋 (LLM Wiki)\n\n{wiki_rules}",
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

    _log_cache_usage(msg.usage, "CP")
    parsed = _parse_json(msg.content[0].text)

    if spine is not None:
        rows, issues = spine_mod.assemble_rows(parsed, spine)
        parsed["rows"] = rows
        parsed.pop("special_fills", None)
        if issues:
            print(f"  [CP] 특별특성 조립 경고: {issues}")

    return parsed


def _log_cache_usage(usage, agent_name: str):
    created = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    if created:
        print(f"  [{agent_name}] 캐시 저장: {created:,} 토큰")
    if read:
        print(f"  [{agent_name}] 캐시 히트: {read:,} 토큰 절감")
