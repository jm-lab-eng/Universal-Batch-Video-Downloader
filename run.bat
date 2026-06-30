@echo off
REM Universal Batch Video Downloader — Windows launcher
REM Activates venv if present, then runs the application.

cd /d "%~dp0"

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

python main.py

if errorlevel 1 (
    echo.
    echo Application exited with an error. Press any key to close.
    pause >nul
)