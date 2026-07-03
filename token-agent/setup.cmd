@echo off
chcp 65001 >nul
echo ==========================================
echo   Агент токена ARSHIN — настройка
echo ==========================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

if not exist "python.exe" (
    echo ОШИБКА: не найден python.exe в %ROOT_DIR%
    echo.
    echo В этой папке должен находиться портативный Python:
    echo   python.exe, python3.dll, python311.dll, Lib\ и другие.
    echo.
    pause
    exit /b 1
)

echo Найден портативный Python.
echo.

rem --- Включаем site-packages и pip для embedded Python ---------------------
set "PTH_FILE="
for %%F in (python*.pth) do set "PTH_FILE=%%F"

if defined PTH_FILE (
    echo Обновляю %PTH_FILE% для работы pip...
    (
        echo python311.zip
        echo .
        echo Lib\site-packages
        echo import site
    ) > "%PTH_FILE%"
) else (
    echo ВНИМАНИЕ: не найден python*.pth. pip может не работать.
)

rem --- Устанавливаем pip, если отсутствует ---------------------------------
if not exist "Scripts\pip.exe" (
    if exist "get-pip.py" (
        echo Устанавливаю pip...
        python.exe get-pip.py --no-warn-script-location
    ) else (
        echo ВНИМАНИЕ: не найден get-pip.py. Установка pip пропущена.
    )
) else (
    echo pip уже установлен.
)

echo.
echo ==========================================
echo   Настройка завершена
echo ==========================================
echo.
echo Дальше:
echo   1. Отредактируй token-agent\.env и укажи TOKEN_FILE_PATH
echo   2. Запусти run.cmd
echo.
pause
