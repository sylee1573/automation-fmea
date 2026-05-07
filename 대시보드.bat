@echo off
cd /d D:\표준류
python show_status.py
if errorlevel 1 (
    echo.
    echo [오류] Python이 설치되어 있지 않거나 실행 실패
    pause
)
