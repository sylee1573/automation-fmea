"""
실행 런처 — 표준류 자동생성 시스템 (단일 프로세스)

백엔드(FastAPI)가 빌드된 프론트엔드(frontend/dist)를 같은 포트에 서빙하므로
이 런처 하나로 앱 전체가 뜬다. 프론트는 상대경로(BASE='')를 쓰기 때문에
어떤 포트로 떠도 수정이 필요 없다.

  python run.py

기존 방식( uvicorn backend.main:app --port 8000 )과 공존한다.
"""

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent
# main.py는 상대 임포트(from .config ...)라 backend 패키지로 로드돼야 한다.
sys.path.insert(0, str(ROOT))

PREFERRED_PORTS = (8000, 8001, 8080, 8765)


def pick_free_port() -> int:
    """선호 포트를 순차 점검하고, 전부 점유면 임의 빈 포트를 반환."""
    for port in PREFERRED_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:  # 연결 실패 = 비어있음
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_browser_later(url: str, delay: float = 2.0) -> None:
    def _open():
        time.sleep(delay)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    dist = ROOT / "frontend" / "dist"
    if not dist.exists():
        print("[안내] frontend/dist 가 없습니다. 먼저 프론트엔드를 빌드하세요:")
        print("       cd frontend && npm install && npm run build")
        print("       (빌드 없이도 API는 뜨지만 웹 화면은 표시되지 않습니다.)\n")

    port = pick_free_port()
    url = f"http://127.0.0.1:{port}"
    print(f"[실행] 브라우저에서 {url} 열림", flush=True)
    open_browser_later(url)

    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
