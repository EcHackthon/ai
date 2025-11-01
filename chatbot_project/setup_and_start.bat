@echo off
chcp 65001 > nul
echo ============================================
echo    AI 서버 설정 및 시작
echo ============================================
echo.

cd /d %~dp0

echo [1/2] 필요한 패키지 설치 중...
echo.
pip install -r requirements.txt
echo.

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ 패키지 설치 실패!
    echo Python과 pip이 설치되어 있는지 확인해주세요.
    pause
    exit /b 1
)

echo.
echo ✅ 패키지 설치 완료!
echo.
echo [2/2] AI 서버 시작 중...
echo.
echo ============================================
echo    AI API 서버 실행
echo    - 주소: http://localhost:5000
echo    - Health Check: http://localhost:5000/api/health
echo ============================================
echo.

python api_server.py

pause
