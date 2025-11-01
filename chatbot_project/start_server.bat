@echo off
echo ============================================================
echo AI API Server Starting (Flask mode)...
echo ============================================================
cd /d %~dp0
python main.py --server
pause
