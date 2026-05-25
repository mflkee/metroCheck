@echo off
chcp 65001 >nul
echo ==========================================
echo  ARSHIN Token Agent — Debug Launch
echo ==========================================
echo.
echo If the agent crashes, this window will stay open.
echo Log file: token-agent.log (in the same folder)
echo.
"%~dp0token-agent.exe"
echo.
echo ------------------------------------------
echo Agent exited with code: %ERRORLEVEL%
echo.
if %ERRORLEVEL% NEQ 0 (
    echo *** ERROR DETECTED ***
    echo Check token-agent.log for details.
)
pause
