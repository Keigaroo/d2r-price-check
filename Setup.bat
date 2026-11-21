@echo off
setlocal EnableExtensions
title D2R Price Check - Setup
cd /d "%~dp0"

echo ============================================================
echo  D2R Price Check - one-time setup
echo ============================================================
echo.

if not exist "%~dp0d2pc\main.py" (
  echo [X] Setup can't find its files.
  echo     You are probably running it from INSIDE the zip file.
  echo     Right-click the zip, choose "Extract All...", then run Setup.bat
  echo     from the extracted folder.
  goto :fail
)

rem ---------- 1. Find or install Python 3.12 ----------
call :findpython
if defined PYEXE goto :havepython

echo [1/4] Python 3.12 not found. Installing it now (takes 1-3 minutes)...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :findpython
if not defined PYEXE (
  echo.
  echo [X] Python could not be installed automatically.
  echo     Install "Python 3.12" from https://www.python.org/downloads/
  echo     then run Setup.bat again.
  goto :fail
)

:havepython
echo [1/4] Using Python: %PYEXE%

rem ---------- 2. Private Python environment ----------
if not exist ".venv\Scripts\python.exe" (
  echo [2/4] Creating the program's Python environment...
  "%PYEXE%" -m venv .venv
  if errorlevel 1 goto :fail
) else (
  echo [2/4] Python environment already exists.
)

rem ---------- 3. Packages ----------
echo [3/4] Installing required packages (1-2 minutes)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :fail

rem ---------- 4. Desktop shortcut ----------
echo [4/4] Creating the "D2R Price Check" shortcut on your desktop...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'D2R Price Check.lnk')); $s.TargetPath='%~dp0Start Price Check.bat'; $s.WorkingDirectory='%~dp0'; $s.Save()"

echo.
echo ============================================================
echo  Running the self test...
echo ============================================================
".venv\Scripts\python.exe" -m d2pc.main --selftest
echo.
echo Setup finished. To use it: double-click "D2R Price Check" on your desktop,
echo then in D2R hover an item and press Ctrl+D.
echo.
pause
exit /b 0

:findpython
set "PYEXE="
for /f "delims=" %%P in ('py -3.12 -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%P"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"
exit /b 0

:fail
echo.
echo Setup did not finish. Take a screenshot of this window and send it to Joe.
pause
exit /b 1
