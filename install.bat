@echo off
chcp 65001 > nul
echo ============================================
echo    10MWT 설치 프로그램
echo ============================================
echo.

:: Python 설치 확인
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo.
    echo Python 설치 방법:
    echo 1. https://www.python.org/downloads/ 에서 다운로드
    echo 2. 설치 시 "Add Python to PATH" 체크 필수!
    echo.
    pause
    exit /b 1
)

echo [1/2] Python 확인 완료
python --version
echo.

echo [2/2] 필요한 패키지 설치 중...
echo.
pip install opencv-python numpy ultralytics Pillow matplotlib supabase reportlab --quiet

if %errorlevel% neq 0 (
    echo [오류] 패키지 설치 실패
    pause
    exit /b 1
)

echo.
echo ============================================
echo    설치 완료!
echo ============================================
echo.
echo "10MWT.bat" 파일을 더블클릭하여 실행하세요.
echo.
pause
