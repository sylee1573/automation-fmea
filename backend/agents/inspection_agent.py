"""
Inspection Agent — 자주검사항목 생성
모델: claude-haiku-4-5-20251001
입력: CP 압축 요약 → 특별특성(CC/SC) 기반 자주검사 항목 추출
"""

import json
import anthropic

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """너는 자동차 부품 제조 공정의 자주검사(공정 검사) 전문가다.
관리계획서(Control Plan)의 특별특성 항목을 기반으로 작업자가 자주적으로 수행하는 검사 항목을 작성한다.
IATF 16949 요구사항에 따라 특별특성(CC/SC)은 반드시 자주검사에 포함해야 한다.
출력은 반드시 유효한 JSON만 출력한다. 설명 텍스트나 마크다운 코드블록 외부에 아무것도 추가하지 않는다."""

PROMPT_TEMPLATE = """## 부품 정보
부품명: {part_name}
부품번호: {part_number}
고객사: {customer}

## 관리계획서(CP) 핵심 요약 (CC/SC 항목 포함)
{cp_summary}

---

위 정보를 바탕으로 자주검사항목을 작성해라.

규칙:
- CC/SC 특별특성 항목은 반드시 포함 (누락 불가)
- 일반 관리항목 중 작업자 자주검사가 필요한 항목 선별
- sample_size·frequency: CP의 내용을 그대로 가져올 것
- measurement_tool: 작업자가 실제 사용하는 측정 도구명
- record_method: "검사성적서", "자주검사표", "SPC 차트" 등 구체적으로

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
      "inspection_item": "검사 항목명",
      "special_characteristic": "CC/SC/빈문자열",
      "specification": "관리 규격 (예: 12.0+0.1/-0.0mm)",
      "measurement_tool": "측정 도구 (예: 핀 게이지 φ12.1)",
      "sample_size": "샘플 크기 (예: 5개/회)",
      "frequency": "검사 주기 (예: 매 2시간, 초물/종물)",
      "record_method": "기록 방법"
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
) -> dict:
    """
    자주검사항목 JSON 생성.

    Args:
        process_data: {drawing_text, process_text, part_name, part_number, customer, process_type}
        cp_summary: CP 압축 요약 (CC/SC 항목 포함)
        wiki_rules: LLM Wiki 내용 (프롬프트 캐싱 적용)
        client: AsyncAnthropic 인스턴스

    Returns:
        자주검사항목 dict
    """
    user_prompt = PROMPT_TEMPLATE.format(
        part_name=process_data.get("part_name", ""),
        part_number=process_data.get("part_number", ""),
        customer=process_data.get("customer", ""),
        cp_summary=cp_summary,
    )

    content_blocks = []

    if wiki_rules:
        content_blocks.append({
            "type": "text",
            "text": f"## 자주검사 작성 룰셋 (LLM Wiki)\n\n{wiki_rules}",
            "cache_control": {"type": "ephemeral"},
        })

    content_blocks.append({
        "type": "text",
        "text": user_prompt,
    })

    msg = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": content_blocks}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    )

    _log_cache_usage(msg.usage, "자주검사")
    return _parse_json(msg.content[0].text)


def _log_cache_usage(usage, agent_name: str):
    created = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    if created:
        print(f"  [{agent_name}] 캐시 저장: {created:,} 토큰")
    if read:
        print(f"  [{agent_name}] 캐시 히트: {read:,} 토큰 절감")
