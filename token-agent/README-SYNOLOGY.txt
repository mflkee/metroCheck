ARSHIN Token Agent - File Sync Mode
====================================

WHAT'S NEW:
-----------
This version writes the token to a JSON file instead of network polling.
The file is synced to the server via Synology Drive (or any cloud sync).

HOW IT WORKS:
-------------
1. Chrome Extension detects token on fgis.gost.ru
2. Extension sends token to this agent (localhost:8003)
3. Agent writes token to arshin-token.json file
4. Synology Drive syncs the file to the server
5. Server reads token from the synced file

SETUP:
------
1. Install Synology Drive Client on this PC
2. Create a shared folder (e.g., C:/Users/Zonov/SynologyDrive/tokens/)
3. Place token-agent.exe in any folder
4. Set environment variable or use run.bat

ENVIRONMENT VARIABLE:
---------------------
TOKEN_FILE_PATH = path to the shared JSON file

Example:
  set TOKEN_FILE_PATH=C:/Users/Zonov/SynologyDrive/tokens/arshin-token.json

Or use run.bat which sets it automatically.

FILE FORMAT:
------------
The agent creates a file like this:

{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "updated_at": 1748423456,
  "expires_in": 3600,
  "source": "chrome-extension"
}

The server reads this file and deletes it after use.

NO NETWORK CONFIG NEEDED:
-------------------------
- No need to open ports
- No need for Netbird/VPN
- No need for firewall rules
- Just file sync via Synology Drive

TROUBLESHOOTING:
----------------
If token doesn't reach server:
1. Check that Synology Drive is syncing the folder
2. Check that TOKEN_FILE_PATH points to the synced folder
3. Look at token-agent.log for errors
