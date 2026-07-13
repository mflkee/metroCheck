@echo off
chcp 65001 >nul

cd /d "%~dp0"
python serve_fake_page.py
pause
