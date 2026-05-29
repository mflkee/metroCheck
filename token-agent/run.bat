@echo off
echo ============================================================
echo   ARSHIN Token Agent - Synology Drive Mode
echo ============================================================
echo.
echo IMPORTANT: Change the path below to your Synology Drive folder!
echo.
echo Current path: C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json
echo.
echo If your Synology Drive is in different location:
echo   1. Right-click this file -> Edit
echo   2. Change the line: set TOKEN_FILE_PATH=...
echo   3. Save and run again
echo.

rem === CHANGE THIS PATH TO YOUR SYNOLOGY DRIVE FOLDER ===
set TOKEN_FILE_PATH=C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json
rem ========================================================

echo Token file will be written to:
echo   %TOKEN_FILE_PATH%
echo.

if exist token-agent.exe (
    echo Found: token-agent.exe
    echo.
    token-agent.exe
) else if exist python.exe (
    echo Found: python.exe
    echo Starting from source...
    python main.py
) else if exist python3.exe (
    echo Found: python3.exe
    echo Starting from source...
    python3 main.py
) else (
    echo ERROR: Neither token-agent.exe nor python found!
    echo.
    echo Please install Python 3.10+ from https://python.org
    echo Or download the pre-built token-agent.exe
    echo.
    pause
    exit /b 1
)

echo.
echo Agent stopped.
pause
