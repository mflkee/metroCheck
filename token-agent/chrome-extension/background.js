const AGENT_URL = 'http://127.0.0.1:8003';
let knownTokens = new Set();
let pendingTokens = [];

function log(...args) {
  console.log('[ARSHIN]', ...args);
}

async function sendTokenToAgent(token, key = 'manual', source = 'popup') {
  if (knownTokens.has(token)) {
    log('Токен уже отправлялся, пропускаем');
    return { ok: true, cached: true };
  }

  try {
    const response = await fetch(AGENT_URL + '/token/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, key, source }),
    });

    if (response.ok) {
      knownTokens.add(token);
      log('Токен успешно отправлен агенту');
      return { ok: true };
    } else {
      const text = await response.text();
      log('Агент ответил с ошибкой:', response.status, text);
      return { ok: false, error: 'HTTP ' + response.status + ': ' + text };
    }
  } catch (err) {
    log('Агент недоступен, токен поставлен в очередь:', err.message);
    queueToken(token, key, source);
    return { ok: false, error: err.message, queued: true };
  }
}

function queueToken(token, key, source) {
  if (pendingTokens.some(t => t.token === token)) return;
  pendingTokens.push({ token, key, source, ts: Date.now() });
  startRetryTimer();
}

let retryTimer = null;
function startRetryTimer() {
  if (retryTimer) return;
  retryTimer = setInterval(async () => {
    if (pendingTokens.length === 0) {
      clearInterval(retryTimer);
      retryTimer = null;
      return;
    }
    log('Повторная попытка отправить', pendingTokens.length, 'токен(ов)');
    const copy = pendingTokens.slice();
    pendingTokens = [];
    for (const item of copy) {
      const result = await sendTokenToAgent(item.token, item.key, item.source);
      if (!result.ok && !result.cached) {
        queueToken(item.token, item.key, item.source);
      }
    }
  }, 5000);
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  switch (msg.type) {
    case 'token_found':
      sendTokenToAgent(msg.token, msg.key, msg.source)
        .then(result => sendResponse(result))
        .catch(err => sendResponse({ ok: false, error: err.message }));
      return true;

    case 'storage_dump':
      log('Storage dump:', msg.dump);
      fetch(AGENT_URL + '/token/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(msg.dump),
      }).catch(() => {});
      sendResponse({ ok: true });
      break;

    case 'send_token':
      sendTokenToAgent(msg.token, msg.key, msg.source)
        .then(result => sendResponse(result))
        .catch(err => sendResponse({ ok: false, error: err.message }));
      return true;

    case 'check_agent':
      fetch(AGENT_URL + '/health')
        .then(r => r.json().then(data => sendResponse({ ok: true, data })))
        .catch(err => sendResponse({ ok: false, error: err.message }));
      return true;
  }
});
