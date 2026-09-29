@echo off
rem Opens the Job Scout dashboard. Keep this window open while you use it.
cd /d "%~dp0"
echo Starting Job Scout... your browser will open in a few seconds.
echo Keep this window open. Close it to stop the dashboard.
start "" cmd /c "timeout /t 4 >nul && start http://localhost:5000"
python app.py
if errorlevel 1 (
  echo.
  echo Job Scout could not start. Open this folder in Claude Code and type:
  echo   the dashboard won't start
  pause
)
