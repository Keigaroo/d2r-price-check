@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m d2pc.main --selftest
pause
