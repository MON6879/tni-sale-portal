@echo off
chcp 65001 > nul
title TAO KHOA TELEGRAM MOI
cd /d "%~dp0"
echo =============================================================
echo 🔑 DANG KHOI CHAY TOOL TAO KEY TELEGRAM CHO ANH...
echo =============================================================
echo.
python generate_session.py
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
        "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" generate_session.py
    )
)
echo.
echo =============================================================
echo Nhan phim bat ky de dong cua so nay...
echo =============================================================
pause
