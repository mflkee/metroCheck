@echo off
chcp 65001 >nul
echo ==========================================
echo   ARSHIN Token Agent - First-time Setup
echo ==========================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

if not exist "python.exe" (
    echo ERROR: python.exe not found in %ROOT_DIR%
    echo.
    echo This folder must contain portable Python files:
    echo   python.exe, python3.dll, python311.dll, Lib\, etc.
    echo.
    pause
    exit /b 1
)

echo Found portable Python.
echo.

rem --- Enable site-packages and pip for embedded Python ---------------------
set "PTH_FILE="
for %%F in (python*.pth) do set "PTH_FILE=%%F"

if defined PTH_FILE (
    echo Updating %PTH_FILE% to enable pip...
    (
        echo python311.zip
        echo .
        echo Lib\site-packages
        echo import site
    ) > "%PTH_FILE%"
) else (
    echo WARNING: python*.pth not found. pip may not work.
)

rem --- Install pip if missing -----------------------------------------------
if not exist "Scripts\pip.exe" (
    if exist "get-pip.py" (
        echo Installing pip...
        python.exe get-pip.py --no-warn-script-location
    ) else (
        echo WARNING: get-pip.py not found. Skipping pip install.
    )
) else (
    echo pip already installed.
)

echo.
echo ==========================================
echo   Setup complete
echo ==========================================
echo.
echo Next steps:
echo   1. Edit token-agent\.env and set your TOKEN_FILE_PATH
echo   2. Double-click run.cmd
echo.
pause
