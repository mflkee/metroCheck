@echo off
chcp 65001 > nul
title Token Agent
cd /d "%~dp0"

echo ============================================
echo Token Agent
echo ============================================
echo.

if not exist ".env" (
    echo [ERROR] .env не найден. Сначала запусти setup.cmd.
    pause
    exit /b 1
)

set "PYTHON_CMD=python"

where python > nul 2> nul
if %errorlevel% == 0 goto run

where python3 > nul 2> nul
if %errorlevel% == 0 (
    set "PYTHON_CMD=python3"
    goto run
)

if exist "C:\Program Files\PostgreSQL\17\pgAdmin 4\python\python.exe" (
    set "PYTHON_CMD=C:\Program Files\PostgreSQL\17\pgAdmin 4\python\python.exe"
    goto run
)

echo [ERROR] Python не найден. Установи Python или укажи полный путь в этом файле.
pause
exit /b 1

:run
echo Запуск с помощью: %PYTHON_CMD%
echo.
%PYTHON_CMD% server.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Агент завершился с ошибкой. Проверь лог token-agent.log.
    pause
)
