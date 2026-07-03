@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
echo ==========================================
echo   Агент токена ARSHIN — настройка
echo ==========================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

rem --- Проверяем, есть ли системный Python в PATH ---------------------------
for %%X in (python.exe) do (
    set "SYS_PYTHON=%%~$PATH:X"
    if not "!SYS_PYTHON!"=="" (
        echo Найден системный Python: !SYS_PYTHON!
        echo.
        echo Системный Python подходит для запуска. Дополнительная настройка не нужна.
        echo.
        pause
        exit /b 0
    )
)

for %%X in (py.exe) do (
    set "PY_LAUNCHER=%%~$PATH:X"
    if not "!PY_LAUNCHER!"=="" (
        echo Найден py launcher: !PY_LAUNCHER!
        echo.
        echo Он подходит для запуска. Дополнительная настройка не нужна.
        echo.
        pause
        exit /b 0
    )
)

rem --- Если рядом уже есть portable Python, настраиваем pip -----------------
if exist "python.exe" (
    echo Найден портативный Python рядом.
    goto :configure_portable
)

rem --- Скачиваем embedded Python --------------------------------------------
echo Системный Python не найден.
echo Скачиваю портативный Python 3.11...
echo.

set "PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
set "PYTHON_ZIP=%TEMP%\python-3.11.9-embed-amd64.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command "
    param([string]$Url, [string]$OutFile)
    try {
        Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -TimeoutSec 120
        Write-Host 'Download complete'
    } catch {
        Write-Host ('Download failed: ' + $_.Exception.Message)
        exit 1
    }
" -Url "%PYTHON_URL%" -OutFile "%PYTHON_ZIP%"

if errorlevel 1 (
    echo ОШИБКА: не удалось скачать Python.
    echo.
    echo Проверь подключение к интернету или установи Python вручную:
    echo   https://python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo Распаковываю Python в %ROOT_DIR%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%PYTHON_ZIP%' -DestinationPath '%ROOT_DIR%' -Force"

if not exist "python.exe" (
    echo ОШИБКА: после распаковки python.exe не найден.
    pause
    exit /b 1
)

echo Python распакован.
echo.

:configure_portable
rem --- Включаем site-packages и pip для embedded Python ---------------------
set "PTH_FILE="
for %%F in (python*.pth) do set "PTH_FILE=%%F"

if defined PTH_FILE (
    echo Настраиваю %PTH_FILE% для работы pip...
    (
        echo python311.zip
        echo .
        echo Lib\site-packages
        echo import site
    ) > "%PTH_FILE%"
) else (
    echo ВНИМАНИЕ: не найден python*.pth. pip может не работать.
)

rem --- Скачиваем get-pip.py, если его нет -----------------------------------
if not exist "get-pip.py" (
    echo Скачиваю get-pip.py...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "
        try {
            Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py' -UseBasicParsing -TimeoutSec 120
            Write-Host 'get-pip.py downloaded'
        } catch {
            Write-Host ('Failed to download get-pip.py: ' + $_.Exception.Message)
            exit 1
        }
    "
    if errorlevel 1 (
        echo ВНИМАНИЕ: не удалось скачать get-pip.py.
    )
)

rem --- Устанавливаем pip, если отсутствует ---------------------------------
if not exist "Scripts\pip.exe" (
    if exist "get-pip.py" (
        echo Устанавливаю pip...
        python.exe get-pip.py --no-warn-script-location
    ) else (
        echo ВНИМАНИЕ: get-pip.py не найден. Установка pip пропущена.
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
