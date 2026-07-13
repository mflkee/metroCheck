// Ключи хранилища, в которых может лежать токен ARSHIN.
// Порядок важен: перебираем от более вероятных к менее вероятным.
const TOKEN_KEYS = ['u', 'user', 'profile', 'auth', 'token', 'accessToken', 'arshin_token'];

function looksLikeJwt(value) {
  return typeof value === 'string' && value.startsWith('eyJ') && value.split('.').length >= 2;
}

function extractToken(value) {
  if (looksLikeJwt(value)) return value;
  if (typeof value !== 'string') return null;
  try {
    const parsed = JSON.parse(value);
    if (parsed && typeof parsed === 'object') {
      for (const k of Object.keys(parsed)) {
        if (looksLikeJwt(parsed[k])) return parsed[k];
      }
    }
  } catch (_) {}
  return null;
}

function checkForToken() {
  for (const store of [localStorage, sessionStorage]) {
    for (const key of TOKEN_KEYS) {
      try {
        const raw = store.getItem(key);
        if (!raw) continue;
        const token = extractToken(raw);
        if (token) {
          chrome.runtime.sendMessage({
            type: 'token_found',
            token,
            key,
            source: store === localStorage ? 'localStorage' : 'sessionStorage',
          });
          return true;
        }
      } catch (_) {}
    }
  }

  // Fallback: ищем JWT в любом значении localStorage/sessionStorage
  for (const store of [localStorage, sessionStorage]) {
    for (let i = 0; i < store.length; i++) {
      try {
        const key = store.key(i);
        if (!key) continue;
        const raw = store.getItem(key);
        const token = extractToken(raw);
        if (token) {
          chrome.runtime.sendMessage({
            type: 'token_found',
            token,
            key,
            source: store === localStorage ? 'localStorage' : 'sessionStorage',
          });
          return true;
        }
      } catch (_) {}
    }
  }

  return false;
}

checkForToken();
setInterval(checkForToken, 3000);
