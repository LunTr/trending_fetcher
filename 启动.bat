@echo off
REM One-click launcher: keep Rust/Tauri build output outside the project.
setlocal
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
set "KB_PYTHON=E:\soft\Anaconda\python.exe"
cd /d "%~dp0desktop"
echo Starting KB Search with an ephemeral Tauri build cache...
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\tauri-dev-light.ps1"
set "APP_EXIT=%ERRORLEVEL%"
pause
exit /b %APP_EXIT%
