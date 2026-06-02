@echo off
REM One-click launcher: add cargo to PATH, pin backend Python, then start Tauri.
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
set "KB_PYTHON=E:\soft\Anaconda\python.exe"
cd /d "%~dp0desktop"
echo Starting KB Search (first run compiles Rust, please wait a few minutes)...
call npm run tauri dev
pause
