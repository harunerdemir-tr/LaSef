@echo off
title LaSef v7.0 Multi-Agent Enterprise Workspace
chcp 65001 > nul
cd /d "%~dp0"
echo ===================================================
echo 🎭 LaSef v7.0 Kurumsal Coklu Ajan Orkestrasi Baslatiliyor...
echo ===================================================
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Bir hata olustu. Cikmak icin bir tusa basin...
    pause > nul
)
