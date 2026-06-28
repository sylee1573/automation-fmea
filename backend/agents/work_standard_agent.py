"""
Work Standard Agent — 작업표준서 생성
모델: claude-haiku-4-5-20251001
입력: CP 압축 요약 → 공정별 작업 순서·핵심사항 작성
"""

import json
import anthropic

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """너는 자동차 부품 제조 공정의 작업표준서 전문가다.
관리계획서(Control Plan) 결과를 기반으로 공정별 작업 순서와 핵심 사항을 작성한다.
현장 작업자가 실제로 수행할 수 있는 구체적인 내용을 작성해야 한다.
출력은 반드시 유효한 JSON만 출력한다. 설명 텍스트나 마크다운 코드블록 외부에 아무것도 추가하지 않는다."""

PROMPT_TEMPLATE = """## 부품 정보
부품명: {part_name}
부품번호: {part_number}
고객사: {customer}

## 공정 정보
{process_text}

## 관리계획서(CP) 핵심 요약
{cp_summary}

{spine_text}

---

위 정보를 바탕으로 작업표준서를 작성해라.

규칙:
- 위 [공유 엔티티 목록]의 공정을 모두 다룬다. 목록에 없는 공정을 임의로 만들지 마라.
- process_number는 목록의 공정번호를 그대로 사용한다.
- 각 공정의 작업 단계를 세부적으로 분해 (공정당 3~6단계)
- key_point: 작업자가 반드시 확인해야 할 핵심 사항 (CC/SC 관련 주의사항 강조)
- reason: 핵심사항의 이유/근거 (품질 불량 예방 관점)
- tool_equipment: 실제 사용 공구·설비 이름 (구체적으로)
- safety: 안전 주의사항 (해당 없으면 빈 문자열)

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
      "step_number": "1",
      "work_content": "작업 내용 (동사 형태로)",
      "key_point": "핵심 사항",
      "reason": "이유/근거",
      "tool_equipment": "공구/설비",
      "safety": "안전 주의사항"
    }}
  ]
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
    cp_summary: str,
    wiki_rules: str,
    client: anthropic.AsyncAnthropic,
    spine_text: str = "",
) -> dict:
    """
    작업표준서 JSON 생성. 공정 커버리지를 위해 process_id를 코드가 스탬프한다.

    Args:
        process_data: {drawing_text, process_text, part_name, part_number, customer, process_type}
        cp_summary: CP 압축 요약
        wiki_rules: LLM Wiki 내용 (프롬프트 캐싱 적용)
        client: AsyncAnthropic 인스턴스
        spine_text: spine 공정 목록 프롬프트 문자열

    Returns:
        작업표준서 dict (행에 process_id 스탬프)
    """
    user_prompt = PROMPT_TEMPLATE.format(
        part_name=process_data.get("part_name", ""),
        part_number=process_data.get("part_number", ""),
        customer=process_data.get("customer", ""),
        process_text=process_data.get("process_text", ""),
        cp_summary=cp_summary,
        spine_text=spine_text,
    )

    content_blocks = []

    if wiki_rules:
        content_blocks.append({
            "type": "text",
            "text": f"## 작업표준서 작성 룰셋 (LLM Wiki)\n\n{wiki_rules}",
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

    _log_cache_usage(msg.usage, "작업표준서")
    parsed = _parse_json(msg.content[0].text)

    # 공정 커버리지: process_number 정확일치로 process_id 스탬프 (정체성은 코드 소유)
    for row in parsed.get("rows", []) or []:
        pnum = str(row.get("process_number", "")).strip()
        row["process_id"] = f"P{pnum}" if pnum else ""

    return parsed


def _log_cache_usage(usage, agent_name: str):
    created = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    if created:
        print(f"  [{agent_name}] 캐시 저장: {created:,} 토큰")
    if read:
        print(f"  [{agent_name}] 캐시 히트: {read:,} 토큰 절감")
