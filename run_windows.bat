@echo off
setlocal
cd /d "%~dp0"
if exist "dist\PROSTE_WIDEO.exe" (start "" "dist\PROSTE_WIDEO.exe" & exit /b 0)
if exist ".venv\Scripts\pythonw.exe" (start "" ".venv\Scripts\pythonw.exe" "proste_wideo.py" & exit /b 0)
echo PROSTE_WIDEO has not been built. Run build_windows.bat first.
pause
exit /b 1
