@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ==========================================
echo   ARSHIN Token Agent - Launcher
echo ==========================================
echo.

rem --- Find script directory ------------------------------------------------
set "AGENT_DIR=%~dp0token-agent"
if not exist "%AGENT_DIR%\main.py" (
    set "AGENT_DIR=%~dp0"
)

if not exist "%AGENT_DIR%\main.py" (
    echo ERROR: main.py not found in %AGENT_DIR%
    echo.
    pause
    exit /b 1
)

echo Agent directory: %AGENT_DIR%

rem --- Locate Python --------------------------------------------------------
set "PYTHON_EXE="

rem 1) Portable python.exe next to this script (preferred)
if exist "%~dp0python.exe" (
    set "PYTHON_EXE=%~dp0python.exe"
    goto :python_found
)

rem 2) Portable python.exe one level up
if exist "%~dp0..\python.exe" (
    set "PYTHON_EXE=%~dp0..\python.exe"
    goto :python_found
)

rem 3) python.exe in PATH
for %%X in (python.exe) do (
    set "PYTHON_EXE=%%~$PATH:X"
    if not "!PYTHON_EXE!"=="" goto :python_found
)

rem 4) py launcher
for %%X in (py.exe) do (
    set "PY_LAUNCHER=%%~$PATH:X"
    if not "!PY_LAUNCHER!"=="" (
        set "PYTHON_EXE=py -3"
        goto :python_found
    )
)

:python_not_found
echo ERROR: python.exe not found.
echo.
echo Options:
echo   1. Place portable python.exe next to this script, OR
echo   2. Install Python 3.10+ from https://python.org and check "Add Python to PATH"
echo.
pause
exit /b 1

:python_found
echo Python: %PYTHON_EXE%
echo.

rem --- Ensure .env exists with placeholder ----------------------------------
if not exist "%AGENT_DIR%\.env" (
    echo Creating default .env file...
    (
        echo # ARSHIN Token Agent configuration
        echo # IMPORTANT: Replace REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH with your real Synology Drive path
        echo TOKEN_FILE_PATH=REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH/tokens/arshin-token.json
        echo TOKEN_AGENT_HOST=127.0.0.1
        echo TOKEN_AGENT_PORT=8003
    ) > "%AGENT_DIR%\.env"
    echo Created: %AGENT_DIR%\.env
    echo.
)

rem --- Read TOKEN_FILE_PATH from .env ---------------------------------------
set "TOKEN_FILE_PATH="
for /f "usebackq tokens=1,* delims==" %%a in ("%AGENT_DIR%\.env") do (
    set "KEY=%%a"
    set "VAL=%%b"
    call :trim KEY
    call :trim VAL
    if "!KEY!"=="TOKEN_FILE_PATH" set "TOKEN_FILE_PATH=!VAL!"
)

if not defined TOKEN_FILE_PATH (
    echo ERROR: TOKEN_FILE_PATH not set in .env file!
    echo.
    echo Please edit %AGENT_DIR%\.env
    echo and replace REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH with your real path.
    echo Example: TOKEN_FILE_PATH=C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json
    echo.
    pause
    exit /b 1
)

rem --- Detect placeholder and stop ------------------------------------------
echo %TOKEN_FILE_PATH% | findstr /I "REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH" >nul
if %errorlevel% == 0 (
    echo ERROR: You did not set your real Synology Drive path in .env!
    echo.
    echo Please edit %AGENT_DIR%\.env
    echo and replace REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH with your real path.
    echo Example: TOKEN_FILE_PATH=C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json
    echo.
    pause
    exit /b 1
)

echo TOKEN_FILE_PATH: %TOKEN_FILE_PATH%
echo.

rem --- Normalize path separators for mkdir ----------------------------------
set "TOKEN_DIR=%TOKEN_FILE_PATH:/=\%"
for %%F in ("%TOKEN_DIR%") do set "TOKEN_DIR=%%~dpF"

if not exist "%TOKEN_DIR%" (
    echo Token directory does not exist yet.
    echo Creating: %TOKEN_DIR%
    mkdir "%TOKEN_DIR%" 2>nul
    if not exist "%TOKEN_DIR%" (
        echo WARNING: Could not create directory. The agent will wait for Synology Drive.
        echo.
    ) else (
        echo Directory created.
        echo.
    )
)

rem --- Start agent ----------------------------------------------------------
echo Starting agent...
echo.
echo If a Windows Firewall dialog appears, allow access for private networks.
echo.

%PYTHON_EXE% "%AGENT_DIR%\main.py"

if errorlevel 1 (
    echo.
    echo Agent exited with error. Check token-agent.log for details.
    pause
    exit /b 1
)

echo.
echo Agent stopped.
pause
exit /b 0

:trim
setlocal EnableDelayedExpansion
set "V=!%~1!"
set "V=!V: =!"
set "V=!V:	=!"
endlocal & set "%~1=%V%"
goto :eof
