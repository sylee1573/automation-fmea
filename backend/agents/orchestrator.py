"""
Orchestrator — 4개 에이전트 순차 실행 조율

실행 순서:
  FMEA → (압축) → CP → (압축) → 작업표준서
                       └→ (압축) → 자주검사
  → 정합성 검증 (최대 2회 재시도)

사용:
  import asyncio
  from backend.agents import run_sequential, GenerationOptions

  result = asyncio.run(run_sequential(
      process_data={
          "drawing_text": "...",
          "process_text": "...",
          "part_name": "브래킷",
          "part_number": "FSB-001",
          "customer": "현대자동차",
          "process_type": "프레스",
      },
      options=GenerationOptions(),
      api_key="sk-ant-...",
      output_dir="output/",
  ))
"""

import json
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import anthropic

from . import fmea_agent, cp_agent, work_standard_agent, inspection_agent
from ..validators.consistency_checker import check as check_consistency
from ..output.excel_generator import generate_all

COMPRESSOR_MODEL = "claude-haiku-4-5-20251001"
WIKI_DIR = Path(__file__).parent.parent / "wiki" / "wiki"


# ─── 설정 ─────────────────────────────────────────────────────────────────────

@dataclass
class GenerationOptions:
    pfmea: bool = True
    cp: bool = True
    work_standard: bool = True
    inspection: bool = True

    def validate(self):
        """의존성 자동 보정"""
        if self.cp and not self.pfmea:
            self.pfmea = True
        if self.work_standard and not self.cp:
            self.cp = True
            self.pfmea = True
        if self.inspection and not self.cp:
            self.cp = True
            self.pfmea = True


# ─── Wiki 로딩 ────────────────────────────────────────────────────────────────

def load_wiki_rules(wiki_dir: str = None) -> str:
    """wiki/ 폴더의 모든 .md 파일을 읽어 하나의 문자열로 반환"""
    target = Path(wiki_dir) if wiki_dir else WIKI_DIR
    if not target.exists():
        return ""

    pages = []
    for md_file in sorted(target.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            pages.append(f"### {md_file.stem}\n\n{text}")
        except Exception:
            continue

    return "\n\n---\n\n".join(pages)


# ─── 압축기 (CC/SC 강제 보존) ─────────────────────────────────────────────────

def _extract_cc_sc_rows(data: dict) -> list:
    rows = data.get("rows", [])
    return [r for r in rows if str(r.get("special_characteristic", "")).upper() in ("CC", "SC")]


async def _compress(
    result: dict,
    target_agent: str,
    client: anthropic.AsyncAnthropic,
) -> str:
    """
    결과 dict를 다음 에이전트 입력용 텍스트로 압축.
    CC/SC 항목은 JSON 원본 그대로 강제 포함.
    """
    cc_sc_rows = _extract_cc_sc_rows(result)

    mandatory_section = ""
    if cc_sc_rows:
        mandatory_section = (
            f"\n## [필수 포함] CC/SC 특별특성 항목 ({len(cc_sc_rows)}건) — 절대 누락 금지\n"
            f"```json\n{json.dumps(cc_sc_rows, ensure_ascii=False, indent=2)}\n```\n"
        )

    prompt = f"""다음 문서 결과를 {target_agent} 에이전트에게 전달할 핵심 요약으로 압축해라.

압축 규칙:
1. 아래 [필수 포함] 섹션은 반드시 그대로 출력할 것
2. 나머지는 {target_agent} 생성에 필요한 최소 정보만 마크다운으로 요약
3. 각 공정의 번호·이름·주요 관리항목을 간결하게 유지
{mandatory_section}
## 원본 (압축 대상)
{json.dumps(result, ensure_ascii=False)}
"""

    msg = await client.messages.create(
        model=COMPRESSOR_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


# ─── 메인 순차 실행 ───────────────────────────────────────────────────────────

async def run_sequential(
    process_data: dict,
    options: GenerationOptions = None,
    api_key: str = "",
    wiki_rules: str = None,
    similar_cases: str = "",
    output_dir: str = None,
    generate_excel: bool = True,
    progress_callback=None,
) -> dict:
    """
    4개 에이전트 순차 실행 후 Excel 생성.

    Args:
        process_data: {drawing_text, process_text, part_name, part_number, customer, process_type}
        options: 생성할 문서 선택 (기본: 4종 전체)
        api_key: Anthropic API 키
        wiki_rules: LLM Wiki 내용 (None이면 자동 로드)
        similar_cases: RAG 검색 결과 텍스트
        output_dir: Excel 저장 경로 (None이면 ./output/)
        generate_excel: Excel 파일 생성 여부

    Returns:
        {
          "fmea": dict | None,
          "cp": dict | None,
          "work_standard": dict | None,
          "inspection": dict | None,
          "issues": list[str],
          "output_files": list[str],
        }
    """
    if options is None:
        options = GenerationOptions()
    options.validate()

    if wiki_rules is None:
        wiki_rules = load_wiki_rules()

    client = anthropic.AsyncAnthropic(api_key=api_key)

    result = {
        "fmea": None,
        "cp": None,
        "work_standard": None,
        "inspection": None,
        "issues": [],
        "output_files": [],
    }

    async def _notify(step: str, status: str, **kwargs):
        msg = f"[{step}] {status}"
        if kwargs:
            msg += " " + str(kwargs)
        print(msg, flush=True)
        if progress_callback:
            await progress_callback(step=step, status=status, **kwargs)

    # ── Step 1: FMEA ───────────────────────────────────────────────────────────
    if options.pfmea:
        await _notify("FMEA", "started")
        result["fmea"] = await fmea_agent.generate(
            process_data=process_data,
            wiki_rules=wiki_rules,
            similar_cases=similar_cases,
            client=client,
        )
        rows = len(result["fmea"].get("rows", []))
        h = sum(1 for r in result["fmea"]["rows"] if str(r.get("AP", "")).upper() == "H")
        await _notify("FMEA", "completed", rows=rows, h_count=h)

    # ── Step 2: CP ─────────────────────────────────────────────────────────────
    if options.cp and result["fmea"]:
        await _notify("CP", "started")
        fmea_summary = await _compress(result["fmea"], "Control Plan", client)
        result["cp"] = await cp_agent.generate(
            process_data=process_data,
            fmea_summary=fmea_summary,
            wiki_rules=wiki_rules,
            client=client,
        )
        cp_rows = len(result["cp"].get("rows", []))
        await _notify("CP", "completed", rows=cp_rows)

    # ── Step 3: 작업표준서 + 자주검사 (CP 결과 공유, 압축 병렬) ─────────────────
    if result["cp"]:
        compress_tasks = []
        if options.work_standard:
            compress_tasks.append(_compress(result["cp"], "작업표준서", client))
        if options.inspection:
            compress_tasks.append(_compress(result["cp"], "자주검사", client))

        compress_results = await asyncio.gather(*compress_tasks) if compress_tasks else []
        compress_iter = iter(compress_results)
        cp_summary_ws = next(compress_iter) if options.work_standard else ""
        cp_summary_insp = next(compress_iter) if options.inspection else ""

        ws_task = (
            work_standard_agent.generate(
                process_data=process_data,
                cp_summary=cp_summary_ws,
                wiki_rules=wiki_rules,
                client=client,
            )
            if options.work_standard else None
        )

        insp_task = (
            inspection_agent.generate(
                process_data=process_data,
                cp_summary=cp_summary_insp,
                wiki_rules=wiki_rules,
                client=client,
            )
            if options.inspection else None
        )

        tasks_to_run = []
        labels = []
        if ws_task:
            tasks_to_run.append(ws_task)
            labels.append("work_standard")
        if insp_task:
            tasks_to_run.append(insp_task)
            labels.append("inspection")

        if tasks_to_run:
            step_labels = {"work_standard": "작업표준서", "inspection": "자주검사"}
            for label in labels:
                await _notify(step_labels[label], "started")

            results_list = await asyncio.gather(*tasks_to_run)
            for label, res in zip(labels, results_list):
                result[label] = res
                rows = len(res.get("rows", []))
                await _notify(step_labels[label], "completed", rows=rows)

    # ── Step 4: 정합성 검증 + 재시도 ──────────────────────────────────────────
    for attempt in range(2):
        issues = check_consistency(
            fmea=result["fmea"],
            cp=result["cp"],
            work_standard=result["work_standard"],
            inspection=result["inspection"],
        )
        if not issues:
            break

        await _notify("정합성", "retry", attempt=attempt + 1, issue_count=len(issues))

        retry_tasks = []
        retry_labels = []

        if any("[FMEA_CP]" in i for i in issues) and result["fmea"]:
            fmea_summary = await _compress(result["fmea"], "Control Plan", client)
            retry_tasks.append(cp_agent.generate(process_data, fmea_summary, wiki_rules, client))
            retry_labels.append("cp")

        if any("[CP_WS]" in i for i in issues) and result["cp"]:
            cp_sum = await _compress(result["cp"], "작업표준서", client)
            retry_tasks.append(work_standard_agent.generate(process_data, cp_sum, wiki_rules, client))
            retry_labels.append("work_standard")

        if any("[CP_INSP]" in i for i in issues) and result["cp"]:
            cp_sum = await _compress(result["cp"], "자주검사", client)
            retry_tasks.append(inspection_agent.generate(process_data, cp_sum, wiki_rules, client))
            retry_labels.append("inspection")

        if retry_tasks:
            retry_results = await asyncio.gather(*retry_tasks)
            for label, res in zip(retry_labels, retry_results):
                result[label] = res

    result["issues"] = check_consistency(
        fmea=result["fmea"],
        cp=result["cp"],
        work_standard=result["work_standard"],
        inspection=result["inspection"],
    )

    if result["issues"]:
        await _notify("정합성", "warning", issue_count=len(result["issues"]))
    else:
        await _notify("정합성", "completed", rows=0)

    # ── Step 5: Excel 생성 ─────────────────────────────────────────────────────
    if generate_excel:
        out_dir = Path(output_dir) if output_dir else Path("output")
        out_dir.mkdir(parents=True, exist_ok=True)

        await _notify("Excel", "started")
        output_files = generate_all(
            fmea=result["fmea"],
            cp=result["cp"],
            work_standard=result["work_standard"],
            inspection=result["inspection"],
            output_dir=str(out_dir),
        )
        result["output_files"] = [str(f) for f in output_files]
        await _notify("Excel", "completed", files=[Path(f).name for f in output_files])

    return result
