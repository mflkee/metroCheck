@echo off
REM Build token-agent.exe using PyInstaller
REM Requires Python + PyInstaller installed
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile --console --name token-agent --distpath . main.py
echo.
echo Build complete! Executable: token-agent.exe
