@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ==========================================
echo   Агент токена ARSHIN
echo ==========================================
echo.

rem --- Определяем папку с main.py -------------------------------------------
set "AGENT_DIR=%~dp0token-agent"
if not exist "%AGENT_DIR%\main.py" (
    set "AGENT_DIR=%~dp0"
)

if not exist "%AGENT_DIR%\main.py" (
    echo ОШИБКА: не найден main.py в папке %AGENT_DIR%
    echo.
    pause
    exit /b 1
)

echo Папка агента: %AGENT_DIR%

rem --- Ищем Python: рядом, системный, py launcher ---------------------------
set "PYTHON_EXE="

if exist "%~dp0python.exe" (
    set "PYTHON_EXE=%~dp0python.exe"
    goto :python_found
)

if exist "%~dp0..\python.exe" (
    set "PYTHON_EXE=%~dp0..\python.exe"
    goto :python_found
)

for %%X in (python.exe) do (
    set "PYTHON_EXE=%%~$PATH:X"
    if not "!PYTHON_EXE!"=="" goto :python_found
)

for %%X in (py.exe) do (
    set "PY_LAUNCHER=%%~$PATH:X"
    if not "!PY_LAUNCHER!"=="" (
        set "PYTHON_EXE=py -3"
        goto :python_found
    )
)

:python_not_found
echo ОШИБКА: не найден python.exe.
echo.
echo Сначала запусти setup.cmd — он скачает или найдёт Python.
echo.
pause
exit /b 1

:python_found
echo Python: %PYTHON_EXE%
echo.

rem --- Создаём .env, если его нет -------------------------------------------
if not exist "%AGENT_DIR%\.env" (
    echo Создаю файл настроек .env...
    (
        echo # Настройки агента токена ARSHIN
        echo # ЗАМЕНИ REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH на реальный путь к Synology Drive
        echo TOKEN_FILE_PATH=REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH/tokens/arshin-token.json
        echo TOKEN_AGENT_HOST=127.0.0.1
        echo TOKEN_AGENT_PORT=8003
    ) > "%AGENT_DIR%\.env"
    echo Создан: %AGENT_DIR%\.env
    echo.
)

rem --- Читаем TOKEN_FILE_PATH из .env ---------------------------------------
set "TOKEN_FILE_PATH="
for /f "usebackq tokens=1,* delims==" %%a in ("%AGENT_DIR%\.env") do (
    set "KEY=%%a"
    set "VAL=%%b"
    call :trim KEY
    call :trim VAL
    if "!KEY!"=="TOKEN_FILE_PATH" set "TOKEN_FILE_PATH=!VAL!"
)

if not defined TOKEN_FILE_PATH (
    echo ОШИБКА: в .env не задан TOKEN_FILE_PATH.
    echo Отредактируй %AGENT_DIR%\.env
    echo.
    pause
    exit /b 1
)

echo %TOKEN_FILE_PATH% | findstr /I "REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH" >nul
if %errorlevel% == 0 (
    echo ОШИБКА: в .env не заменён путь к Synology Drive.
    echo.
    echo Отредактируй %AGENT_DIR%\.env
    echo Замени REPLACE_WITH_YOUR_SYNOLOGY_DRIVE_PATH на реальный путь, например:
    echo   TOKEN_FILE_PATH=C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json
    echo.
    pause
    exit /b 1
)

echo Файл токена: %TOKEN_FILE_PATH%
echo.

rem --- Проверяем и при необходимости создаём папку --------------------------
set "TOKEN_DIR=%TOKEN_FILE_PATH:/=\%"
for %%F in ("%TOKEN_DIR%") do set "TOKEN_DIR=%%~dpF"

if not exist "%TOKEN_DIR%" (
    echo Папка для токена не найдена. Создаю: %TOKEN_DIR%
    mkdir "%TOKEN_DIR%" 2>nul
    if not exist "%TOKEN_DIR%" (
        echo ОШИБКА: не удалось создать папку. Проверь путь в .env.
        echo.
        pause
        exit /b 1
    )
    echo Папка создана.
    echo.
)

rem --- Запускаем агента -----------------------------------------------------
echo Запускаю агента...
echo.

%PYTHON_EXE% "%AGENT_DIR%\main.py"

if errorlevel 1 (
    echo.
    echo Агент завершился с ошибкой. Подробности в token-agent.log.
    pause
    exit /b 1
)

echo.
echo Агент остановлен.
pause
exit /b 0

:trim
setlocal EnableDelayedExpansion
set "V=!%~1!"
set "V=!V: =!"
set "V=!V:	=!"
endlocal & set "%~1=%V%"
goto :eof
