@echo off
chcp 65001 >nul
echo ==========================================
echo   Агент токена ARSHIN — автозагрузка
echo ==========================================
echo.

set "ROOT_DIR=%~dp0"
set "RUN_CMD=%ROOT_DIR%run.cmd"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\ARSHIN Token Agent.lnk"

if not exist "%RUN_CMD%" (
    echo ОШИБКА: не найден run.cmd в %ROOT_DIR%
    pause
    exit /b 1
)

echo Создаю ярлык автозагрузки...
echo   Источник: %RUN_CMD%
echo   Куда: %SHORTCUT%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "
    $WshShell = New-Object -ComObject WScript.Shell;
    $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%');
    $Shortcut.TargetPath = '%RUN_CMD%';
    $Shortcut.WorkingDirectory = '%ROOT_DIR%';
    $Shortcut.WindowStyle = 1;
    $Shortcut.Description = 'ARSHIN Token Agent';
    $Shortcut.Save();
"

if exist "%SHORTCUT%" (
    echo ГОТОВО: агент будет запускаться автоматически при включении Windows.
) else (
    echo ОШИБКА: не удалось создать ярлык.
)

echo.
pause
