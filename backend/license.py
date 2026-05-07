"""
하드웨어 지문 라이선스

- CPU ID + MAC 주소 조합 SHA256 해시로 기기 고유값 생성
- HMAC-SHA256 기반 라이선스 키 서명·검증
- 인터넷 없이 로컬 검증 (오프라인 지원)
- 만료 30일 전 경고, 만료 후 실행 차단

키 형식: {fingerprint_16자}-{YYYYMMDD}-{hmac_16자}
예시:    a1b2c3d4e5f6g7h8-20271231-x9y8z7w6v5u4t3s2

개발사 전용 키 발급:
  python license.py --issue --days 365 --fingerprint <지문값>
"""

import hashlib
import hmac
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# 개발사 비밀키 (외부 미공개)
_LICENSE_SECRET = "standards-gen-2024-v1-prod-secret"
_LICENSE_FILE = Path.home() / ".standards_gen" / "license.key"


def get_hardware_fingerprint() -> str:
    """CPU ID + MAC → SHA256[:16] 고유 지문 생성"""
    mac = ":".join(
        ["{:02x}".format((uuid.getnode() >> e) & 0xFF) for e in range(0, 2 * 6, 2)][::-1]
    )

    cpu_id = "UNKNOWN"
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty ProcessorId"],
                capture_output=True, text=True, timeout=10,
            )
            cpu_id = result.stdout.strip()
        except Exception:
            pass

    raw = f"{mac}:{cpu_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_license_key(fingerprint: str, expiry_days: int = 365) -> str:
    """개발사 전용 — 라이선스 키 발급"""
    expiry = (datetime.now() + timedelta(days=expiry_days)).strftime("%Y%m%d")
    payload = f"{fingerprint}:{expiry}"
    sig = hmac.new(_LICENSE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{fingerprint}-{expiry}-{sig}"


def validate_license(key: str) -> dict:
    """
    라이선스 키 검증.

    Returns:
        {"valid": bool, "expiry": str, "days_remaining": int, "reason": str}
    """
    try:
        parts = key.strip().split("-")
        if len(parts) != 3:
            return {"valid": False, "reason": "라이선스 키 형식이 올바르지 않습니다"}

        fp, expiry, sig = parts
        current_fp = get_hardware_fingerprint()

        if fp != current_fp:
            return {"valid": False, "reason": "다른 기기용 라이선스입니다 (기기 교체 시 재발급 필요)"}

        payload = f"{fp}:{expiry}"
        expected_sig = hmac.new(
            _LICENSE_SECRET.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()[:16]

        if not hmac.compare_digest(sig, expected_sig):
            return {"valid": False, "reason": "라이선스 키가 변조되었습니다"}

        expiry_date = datetime.strptime(expiry, "%Y%m%d")
        days_remaining = (expiry_date - datetime.now()).days

        if days_remaining < 0:
            return {
                "valid": False,
                "reason": f"라이선스가 만료되었습니다 ({expiry}). 갱신 문의: sylee1573@gmail.com",
            }

        return {
            "valid": True,
            "expiry": expiry,
            "days_remaining": days_remaining,
            "reason": "",
        }

    except Exception as e:
        return {"valid": False, "reason": f"검증 오류: {e}"}


def save_license(key: str) -> None:
    _LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LICENSE_FILE.write_text(key.strip(), encoding="utf-8")


def load_license() -> str:
    if _LICENSE_FILE.exists():
        return _LICENSE_FILE.read_text(encoding="utf-8").strip()
    return ""


def get_license_status() -> dict:
    """현재 라이선스 상태 반환 (FastAPI 상태 엔드포인트용)"""
    key = load_license()
    if not key:
        return {"licensed": False, "reason": "라이선스 키가 없습니다"}

    result = validate_license(key)
    result["licensed"] = result.pop("valid")
    return result


# ── CLI (개발사 전용 키 발급) ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="라이선스 키 관리")
    parser.add_argument("--fingerprint", help="현재 기기 지문 확인")
    parser.add_argument("--issue", action="store_true", help="키 발급")
    parser.add_argument("--fp", help="대상 기기 지문 (--issue와 함께)")
    parser.add_argument("--days", type=int, default=365, help="유효 기간 (일)")
    parser.add_argument("--validate", metavar="KEY", help="키 검증")
    args = parser.parse_args()

    if args.fingerprint or not any(vars(args).values()):
        print(f"이 기기의 지문: {get_hardware_fingerprint()}")
    elif args.issue:
        fp = args.fp or get_hardware_fingerprint()
        key = generate_license_key(fp, args.days)
        print(f"발급된 키: {key}")
        print(f"  대상 지문: {fp}")
        print(f"  유효 기간: {args.days}일 ({(datetime.now() + timedelta(days=args.days)).strftime('%Y-%m-%d')} 만료)")
    elif args.validate:
        status = validate_license(args.validate)
        print(f"검증 결과: {'유효' if status['valid'] else '무효'}")
        if status.get("days_remaining") is not None:
            print(f"  만료일: {status['expiry']} (남은 일수: {status['days_remaining']}일)")
        if status.get("reason"):
            print(f"  사유: {status['reason']}")
