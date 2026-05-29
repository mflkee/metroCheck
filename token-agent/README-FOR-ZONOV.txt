ARSHIN Token Agent - Synology Drive Setup
=========================================

QUICK START (for Zonov):
-------------------------
1. Install Python 3.10+ from https://python.org (check "Add Python to PATH")
2. Open cmd in this folder
3. Run: pip install -r requirements.txt
4. Edit run.bat - change the TOKEN_FILE_PATH to your Synology Drive folder
5. Double-click run.bat

WHAT IT DOES:
-------------
This agent receives ARSHIN tokens from Chrome Extension and writes
them to a JSON file in your Synology Drive folder.

The file is automatically synced to the server by Synology Drive.

FOLDER STRUCTURE:
-----------------
Create this folder structure in your Synology Drive:
  SynologyDrive/
  └── tokens/
      └── arshin-token.json   <-- token file appears here

IMPORTANT:
----------
You MUST edit run.bat and change this line:
  set TOKEN_FILE_PATH=C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json

To your actual Synology Drive path. For example:
  set TOKEN_FILE_PATH=D:/SynologyDrive/tokens/arshin-token.json
  
Or if your Windows username is different:
  set TOKEN_FILE_PATH=C:/Users/YourName/SynologyDrive/tokens/arshin-token.json

HOW TO CHECK IF IT WORKS:
-------------------------
1. Start run.bat
2. Login to ARSHIN via Chrome
3. Token will be written to the file
4. Check that the file appears in your Synology Drive folder
5. The server will automatically pick it up

TROUBLESHOOTING:
----------------
If "python not found" - install Python and check "Add to PATH"
If "pip not found" - use: python -m pip install -r requirements.txt
If file not written - check that the folder path in run.bat is correct
