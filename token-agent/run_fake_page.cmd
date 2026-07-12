@echo off
chcp 65001 >nul

set PYTHON= "python.exe"

cd /d "%~dp0"
%PYTHON% -m http.server 8080
pause
