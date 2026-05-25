const TOKEN_KEYS = ['u'];
const KNOWN_TOKEN = 'u';  // confirmed: localStorage['u'] = {"orgId":"2163","token":"eyJ..."}

function checkForToken() {
  for (const store of [localStorage, sessionStorage]) {
    try {
      const raw = store.getItem(KNOWN_TOKEN);
      if (!raw) continue;
      let parsed;
      try { parsed = JSON.parse(raw); } catch (_) { continue; }
      if (parsed && parsed.token && parsed.token.startsWith('eyJ')) {
        chrome.runtime.sendMessage({
          type: 'token_found',
          token: parsed.token,
          key: KNOWN_TOKEN,
          source: store === localStorage ? 'localStorage' : 'sessionStorage',
        });
        return true;
      }
    } catch (_) {}
  }
  return false;
}

checkForToken();
setInterval(checkForToken, 3000);
