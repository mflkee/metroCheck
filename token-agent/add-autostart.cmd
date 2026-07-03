@echo off
chcp 65001 >nul
echo ==========================================
echo   ARSHIN Token Agent - Add to Autostart
echo ==========================================
echo.

set "ROOT_DIR=%~dp0"
set "RUN_CMD=%ROOT_DIR%run.cmd"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\ARSHIN Token Agent.lnk"

if not exist "%RUN_CMD%" (
    echo ERROR: run.cmd not found in %ROOT_DIR%
    pause
    exit /b 1
)

echo Creating autostart shortcut...
echo   Source: %RUN_CMD%
echo   Target: %SHORTCUT%
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
    echo SUCCESS: Autostart shortcut created.
    echo Agent will start automatically when Windows boots.
    echo.
    echo IMPORTANT:
    echo   - The agent will wait up to 60 seconds for the Synology Drive folder.
    echo   - Keep the .env file inside token-agent\ folder.
) else (
    echo ERROR: Could not create shortcut.
)

echo.
pause
