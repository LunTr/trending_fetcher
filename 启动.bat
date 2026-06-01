@echo off
chcp 65001 >nul
REM ── 一键启动桌面应用：补 cargo 到 PATH + 锁定后端用的 Python，再起 Tauri ──
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
set "KB_PYTHON=E:\soft\Anaconda\python.exe"
cd /d "%~dp0desktop"
echo 正在启动 KB Search（首次需编译 Rust，请等待几分钟）...
call npm run tauri dev
pause
