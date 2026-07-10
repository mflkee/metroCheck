@echo off
chcp 65001 > nul
title Token Agent Setup
cd /d "%~dp0"

echo ============================================
echo Token Agent - Setup
echo ============================================

where python > nul 2> nul
if %errorlevel% == 0 (
    echo [OK] Python найден: %PATH:python=%
    goto create_env
)

where python3 > nul 2> nul
if %errorlevel% == 0 (
    echo [OK] Python3 найден
    goto create_env
)

if exist "C:\Program Files\PostgreSQL\17\pgAdmin 4\python\python.exe" (
    echo [OK] Найден Python из pgAdmin
    goto create_env
)

echo [ERROR] Python не найден. Установи Python с https://python.org/downloads/
echo         Или запускай сервер вручную с полным путем к python.exe.
pause
exit /b 1

:create_env
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" > nul
        echo [OK] Создан .env из .env.example. Отредактируй путь к TOKEN_FILE_PATH.
    ) else (
        echo [WARN] .env.example не найден. Создай .env вручную.
    )
) else (
    echo [OK] .env уже существует
)

echo.
echo [OK] Настройка завершена.
echo Запускай run.cmd для старта агента.
pause
