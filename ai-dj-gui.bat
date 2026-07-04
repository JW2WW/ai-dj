@echo off
REM AI DJ GUI launcher for Windows
REM Run this to start the app (DJ selector + main GUI)

cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" "%~dp0app.py"
pause
