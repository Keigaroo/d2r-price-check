@echo off
title D2R Price Check
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo D2R Price Check isn't set up yet. Double-click Setup.bat in this folder first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m d2pc.update_source
".venv\Scripts\python.exe" -m d2pc.main
pause
