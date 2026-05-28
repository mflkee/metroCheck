@echo off
echo Starting ARSHIN Token Agent (Synology Drive mode)...
echo.

rem Set the path where token JSON file will be written
rem This folder must be synced by Synology Drive to the server
set TOKEN_FILE_PATH=C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json

echo Token file: %TOKEN_FILE_PATH%
echo.
echo This agent will write tokens to the file above.
echo Synology Drive must sync this folder to the server.
echo.

token-agent.exe

echo.
echo Agent stopped.
pause
