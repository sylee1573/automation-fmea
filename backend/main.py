"""
FastAPI 백엔드 — 표준류 자동생성 시스템

실행:
  cd D:\표준류
  uvicorn backend.main:app --reload --port 8000
"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# 상대 임포트 — uvicorn backend.main:app 으로 실행 시 backend 패키지 컨텍스트 유지
from .config import clear_api_key, is_configured, load_api_key, save_api_key
from .license import (
    get_hardware_fingerprint,
    get_license_status,
    save_license,
    validate_license,
)
from .agents import GenerationOptions, load_wiki_rules, run_sequential
from .preprocessing.pdf_parser import parse as parse_pdf
from .preprocessing.excel_parser import parse_process_sheet

OUTPUT_DIR = Path(__file__).parent.parent / "output"
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

app = FastAPI(title="표준류 자동생성 시스템", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 세션 저장소 ───────────────────────────────────────────────────────────────
_sessions: dict[str, dict] = {}
_task_queues: dict[str, asyncio.Queue] = {}


# ─────────────────────────────────────────────────────────────────────────────
# API 키 설정
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/setup/status")
def get_setup_status():
    return {"configured": is_configured()}


@app.post("/setup/apikey")
def post_api_key(api_key: str = Form(...)):
    key = api_key.strip()
    if not key.startswith("sk-ant-"):
        raise HTTPException(400, "올바른 Anthropic API 키를 입력해주세요 (sk-ant- 로 시작)")
    save_api_key(key)
    return {"ok": True}


@app.delete("/setup/apikey")
def delete_api_key():
    clear_api_key()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# 라이선스
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/license/fingerprint")
def get_fingerprint():
    return {"fingerprint": get_hardware_fingerprint()}


@app.get("/license/status")
def get_license_info():
    return get_license_status()


@app.post("/license/activate")
def activate_license(license_key: str = Form(...)):
    result = validate_license(license_key)
    if result["valid"]:
        save_license(license_key)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 파일 업로드
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/upload")
async def upload_files(
    drawing: Optional[UploadFile] = File(None),
    process_sheet: Optional[UploadFile] = File(None),
):
    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "drawing_text": "",
        "process_text": "",
        "part_name": "",
        "part_number": "",
        "customer": "",
        "process_type": "",
        "output_files": {},
        "last_result": None,
    }

    drawing_summary = ""
    process_summary = ""

    if drawing:
        content = await drawing.read()
        try:
            parsed = parse_pdf(content, use_vision=False)
            session["drawing_text"] = parsed.get("text", "")
            session["part_name"] = parsed.get("part_name", "")
            session["part_number"] = parsed.get("part_number", "")
            drawing_summary = (
                f"도면: {drawing.filename}"
                + (f" (부품번호: {session['part_number']})" if session["part_number"] else "")
            )
        except Exception as e:
            drawing_summary = f"도면 파싱 오류: {e}"

    if process_sheet:
        content = await process_sheet.read()
        try:
            text = parse_process_sheet(content)
            session["process_text"] = text
            process_summary = f"공정검토서: {process_sheet.filename}"
        except Exception as e:
            process_summary = f"공정검토서 파싱 오류: {e}"

    _sessions[session_id] = session

    summary_parts = []
    if drawing_summary:
        summary_parts.append(drawing_summary)
    if process_summary:
        summary_parts.append(process_summary)
    if not summary_parts:
        summary_parts.append("파일 없음 — 데모 시나리오로 생성합니다")

    return {
        "session_id": session_id,
        "summary": "\n".join(summary_parts),
        "part_name": session["part_name"],
        "part_number": session["part_number"],
    }


@app.post("/session/update")
def update_session(
    session_id: str = Form(...),
    part_name: str = Form(""),
    part_number: str = Form(""),
    customer: str = Form(""),
    process_type: str = Form(""),
):
    if session_id not in _sessions:
        raise HTTPException(404, "세션 없음")
    s = _sessions[session_id]
    if part_name:
        s["part_name"] = part_name
    if part_number:
        s["part_number"] = part_number
    if customer:
        s["customer"] = customer
    if process_type:
        s["process_type"] = process_type
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# 표준류 생성 (SSE 스트리밍)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/generate")
async def start_generation(
    session_id: str = Form(...),
    pfmea: str = Form("true"),
    cp: str = Form("true"),
    work_standard: str = Form("true"),
    inspection: str = Form("true"),
):
    if session_id not in _sessions:
        raise HTTPException(404, "세션 없음 — 먼저 파일을 업로드해주세요")

    if not is_configured():
        raise HTTPException(400, "API 키가 설정되지 않았습니다")

    def to_bool(v: str) -> bool:
        return v.lower() in ("true", "1", "yes")

    options = GenerationOptions(
        pfmea=to_bool(pfmea),
        cp=to_bool(cp),
        work_standard=to_bool(work_standard),
        inspection=to_bool(inspection),
    )
    options.validate()

    task_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _task_queues[task_id] = queue

    asyncio.create_task(_run_generation(task_id, session_id, options))
    return {"task_id": task_id}


@app.get("/stream/{task_id}")
async def stream_progress(task_id: str):
    if task_id not in _task_queues:
        raise HTTPException(404, "태스크 없음")

    async def event_generator():
        queue = _task_queues[task_id]
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=120)
                except asyncio.TimeoutError:
                    yield "data: {\"type\":\"heartbeat\"}\n\n"
                    continue

                if event is None:
                    break

                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            _task_queues.pop(task_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_generation(task_id: str, session_id: str, options: GenerationOptions):
    queue = _task_queues.get(task_id)
    if not queue:
        return

    session = _sessions[session_id]
    api_key = load_api_key()

    async def on_progress(step: str, status: str, **kwargs):
        await queue.put({"type": "progress", "step": step, "status": status, **kwargs})

    try:
        process_data = {
            "drawing_text": session.get("drawing_text", ""),
            "process_text": session.get("process_text", ""),
            "part_name": session.get("part_name", ""),
            "part_number": session.get("part_number", ""),
            "customer": session.get("customer", ""),
            "process_type": session.get("process_type", ""),
        }

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        result = await run_sequential(
            process_data=process_data,
            options=options,
            api_key=api_key,
            wiki_rules=load_wiki_rules(),
            similar_cases="",
            output_dir=str(OUTPUT_DIR),
            generate_excel=True,
            progress_callback=on_progress,
        )

        for file_path in result.get("output_files", []):
            filename = Path(file_path).name
            session["output_files"][filename] = file_path

        session["last_result"] = result

        await queue.put({
            "type": "done",
            "files": [Path(f).name for f in result.get("output_files", [])],
            "issues": result.get("issues", []),
            "session_id": session_id,
        })

    except anthropic.AuthenticationError:
        await queue.put({"type": "error", "message": "API 키가 올바르지 않습니다. 설정에서 다시 입력해주세요."})
    except anthropic.RateLimitError:
        await queue.put({"type": "error", "message": "API 요청 한도 초과. 잠시 후 다시 시도해주세요."})
    except Exception as e:
        await queue.put({"type": "error", "message": f"생성 오류: {e}"})
    finally:
        await queue.put(None)


# ─────────────────────────────────────────────────────────────────────────────
# 파일 다운로드
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/download/{session_id}/{filename}")
def download_file(session_id: str, filename: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "세션 없음")

    file_path_str = session["output_files"].get(filename)
    if not file_path_str:
        raise HTTPException(404, f"{filename} 파일이 없습니다")

    file_path = Path(file_path_str)
    if not file_path.exists():
        raise HTTPException(404, "파일이 삭제되었습니다")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 챗봇
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(
    message: str = Form(...),
    session_id: str = Form(""),
):
    if not is_configured():
        raise HTTPException(400, "API 키가 설정되지 않았습니다")

    session = _sessions.get(session_id, {})
    context = _build_chat_context(session)

    api_key = load_api_key()
    client = anthropic.AsyncAnthropic(api_key=api_key)

    system = (
        "너는 자동차 부품 표준류 자동생성 시스템의 도우미다. "
        "FMEA, CP, 작업표준서, 자주검사항목 생성을 돕는다. "
        "답변은 간결하고 실용적으로 한국어로 작성한다."
    )

    messages = []
    if context:
        messages.append({"role": "user", "content": context})
        messages.append({"role": "assistant", "content": "네, 현재 작업 중인 부품 정보를 확인했습니다."})
    messages.append({"role": "user", "content": message})

    async def stream_response():
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'text', 'content': text}, ensure_ascii=False)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_chat_context(session: dict) -> str:
    if not session:
        return ""
    parts = []
    if session.get("part_name"):
        parts.append(f"부품명: {session['part_name']}")
    if session.get("part_number"):
        parts.append(f"부품번호: {session['part_number']}")
    if session.get("customer"):
        parts.append(f"고객사: {session['customer']}")
    if not parts:
        return ""
    return "현재 작업 중인 부품 정보:\n" + "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# 정적 파일 (React 빌드 결과)
# ─────────────────────────────────────────────────────────────────────────────

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")
