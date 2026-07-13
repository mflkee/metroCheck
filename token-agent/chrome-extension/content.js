// На странице Аршина токен JWT всегда лежит в localStorage['u'] внутри поля 'token'.
const STORAGE_KEY = 'u';
const TOKEN_FIELD = 'token';

function looksLikeJwt(value) {
  return typeof value === 'string' && value.startsWith('eyJ') && value.split('.').length >= 2;
}

function extractTokenFromU(raw) {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') {
      const token = parsed[TOKEN_FIELD];
      if (looksLikeJwt(token)) return token;
    }
  } catch (_) {}
  return null;
}

function checkForToken() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const token = extractTokenFromU(raw);
    if (token) {
      chrome.runtime.sendMessage({
        type: 'token_found',
        token,
        key: STORAGE_KEY,
        source: 'localStorage',
      });
      return true;
    }
  } catch (_) {}
  return false;
}

checkForToken();
setInterval(checkForToken, 3000);
