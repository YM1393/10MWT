@echo off
chcp 65001 > nul
cd /d "%~dp0"
python app.py
if %errorlevel% neq 0 (
    echo.
    echo [오류] 앱 실행 실패
    echo install.bat을 먼저 실행하세요.
    pause
)
