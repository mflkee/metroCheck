ARSHIN Token Agent - Polling Mode
==================================

WHAT'S NEW:
-----------
This version uses OUTGOING connections to the server (polling).
No need to open port 8003 on this PC!
Works with Netbird userspace VPN.

HOW TO RUN:
-----------
1. Double-click "run.bat" (or run "token-agent.exe")
2. Keep the window open
3. The agent will automatically connect to the server

WHAT IT DOES:
-------------
Every 30 seconds, the agent asks the server:
  "Do you need an ARSHIN token?"

If the server says YES and the agent has a token (from Chrome Extension),
it sends the token to the server automatically.

REQUIREMENTS:
-------------
- Windows 10/11
- Netbird VPN connected
- Chrome Extension installed (for capturing tokens)

FILES:
------
  token-agent.exe    - The agent program
  run.bat           - Easy launcher script

TROUBLESHOOTING:
----------------
If the agent can't connect:
1. Check that Netbird is connected
2. Check the server is online
3. Look at token-agent.log for details
