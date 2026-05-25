const AGENT_URL = 'http://127.0.0.1:8003';
let knownTokens = new Set();

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  switch (msg.type) {
    case 'token_found':
      if (knownTokens.has(msg.token)) return;
      knownTokens.add(msg.token);
      console.log('[ARSHIN] Token found:', msg.key, '(' + msg.source + ')');
      fetch(AGENT_URL + '/token/callback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: msg.token,
          key: msg.key,
          source: msg.source,
        }),
      }).catch(() => {
        console.debug('[ARSHIN] Agent offline, will retry later');
      });
      break;

    case 'storage_dump':
      console.log('[ARSHIN] Storage dump:', msg.dump);
      fetch(AGENT_URL + '/token/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(msg.dump),
      }).catch(() => {});
      break;
  }
});
