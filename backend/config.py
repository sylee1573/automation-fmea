"""
API 키 관리 — Windows DPAPI 암호화 저장

저장 위치: ~/.standards_gen/api_key.bin
비DPAPI 환경(개발용): 평문 저장 (fallback)
"""

from pathlib import Path

CONFIG_DIR = Path.home() / ".standards_gen"
API_KEY_FILE = CONFIG_DIR / "api_key.bin"


def _dpapi_encrypt(data: bytes) -> bytes:
    try:
        import win32crypt
        # CryptProtectData returns bytes directly (not a tuple)
        result = win32crypt.CryptProtectData(data, None, None, None, None, 0)
        return result if isinstance(result, bytes) else result[1]
    except Exception:
        return data  # DPAPI 미설치 또는 실패 시 평문 fallback


def _dpapi_decrypt(data: bytes) -> bytes:
    try:
        import win32crypt
        # CryptUnprotectData returns (description, bytes) tuple
        result = win32crypt.CryptUnprotectData(data, None, None, None, 0)
        return result[1] if isinstance(result, tuple) else result
    except Exception:
        return data  # 평문 fallback


def save_api_key(api_key: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    encrypted = _dpapi_encrypt(api_key.strip().encode("utf-8"))
    API_KEY_FILE.write_bytes(encrypted)


def load_api_key() -> str:
    if not API_KEY_FILE.exists():
        return ""
    try:
        encrypted = API_KEY_FILE.read_bytes()
        decrypted = _dpapi_decrypt(encrypted)
        return decrypted.decode("utf-8").strip()
    except Exception:
        return ""


def is_configured() -> bool:
    key = load_api_key()
    return bool(key and key.startswith("sk-ant-"))


def clear_api_key() -> None:
    if API_KEY_FILE.exists():
        API_KEY_FILE.unlink()
