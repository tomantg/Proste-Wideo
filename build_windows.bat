@echo off
setlocal
cd /d "%~dp0"
title PROSTE_WIDEO - Windows Build
where py >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] Python 3.11+ required. Install it from python.org and check Add Python to PATH.
  pause
  exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 goto failed
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto failed
python -m pip install -r requirements.txt
if errorlevel 1 goto failed
python -m pytest --version >nul 2>&1
if errorlevel 1 python -m pip install pytest
python -m pytest -q tests
if errorlevel 1 goto failed
python -m PyInstaller --noconfirm --clean --windowed --onefile --name PROSTE_WIDEO --hidden-import=PIL._tkinter_finder --collect-all cv2 --collect-all imageio_ffmpeg proste_wideo.py
if errorlevel 1 goto failed
if not exist dist\PROSTE_WIDEO.exe goto failed
 echo.
 echo [OK] dist\PROSTE_WIDEO.exe was built. Copy this file to a Windows PC.
 echo Windows Defender and SmartScreen may warn about unsigned software.
 pause
 exit /b 0
:failed
echo [ERROR] Build or tests failed. See errors above.
pause
exit /b 1
