const AGENT_URL = 'http://127.0.0.1:8003';
let knownTokens = new Set();

function sendTokenToAgent(token, key = 'manual', source = 'popup') {
  if (knownTokens.has(token)) return;
  knownTokens.add(token);
  console.log('[ARSHIN] Sending token to agent:', key, '(' + source + ')');
  return fetch(AGENT_URL + '/token/callback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, key, source }),
  });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  switch (msg.type) {
    case 'token_found':
      sendTokenToAgent(msg.token, msg.key, msg.source)
        .then((response) => {
          if (response && response.ok) {
            sendResponse({ ok: true });
          } else {
            sendResponse({ ok: false, error: 'agent returned ' + (response ? response.status : 'no response') });
          }
        })
        .catch((err) => {
          console.debug('[ARSHIN] Agent offline, will retry later');
          sendResponse({ ok: false, error: err.message });
        });
      return true;

    case 'storage_dump':
      console.log('[ARSHIN] Storage dump:', msg.dump);
      fetch(AGENT_URL + '/token/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(msg.dump),
      }).catch(() => {});
      break;

    case 'send_token':
      sendTokenToAgent(msg.token, msg.key, msg.source)
        .then(async (response) => {
          if (!response) {
            sendResponse({ ok: false, error: 'Нет ответа от агента' });
            return;
          }
          const text = await response.text();
          try {
            const data = JSON.parse(text);
            sendResponse({ ok: response.ok, status: response.status, data });
          } catch {
            sendResponse({ ok: response.ok, status: response.status, text });
          }
        })
        .catch((err) => {
          sendResponse({ ok: false, error: err.message });
        });
      return true;
  }
});
