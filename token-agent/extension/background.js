// background.js — service worker (Manifest V3).
// Работает в фоне, не имеет доступа к DOM, но может делать fetch и слушать сообщения.
// Подробнее: https://developer.chrome.com/docs/extensions/mv3/service_workers/

// URL локального Python-сервера.
const SERVER_URL = 'http://127.0.0.1:8003/token';


// Слушаем сообщения от content.js.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Фильтруем только нужный тип сообщения.
  if (message.type !== 'TOKEN_FOUND') {
    return false; // Не асинхронный ответ.
  }

  console.log('[BACKGROUND] Получил токен от вкладки:', sender.tab?.url);

  // Отправляем токен на локальный сервер.
  fetch(SERVER_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      token: message.token,
      url: message.url,
      timestamp: message.timestamp
    })
  })
    .then((res) => {
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      return res.json();
    })
    .then((data) => {
      console.log('[BACKGROUND] Сервер ответил:', data);
      sendResponse({ ok: true, server: data });
    })
    .catch((err) => {
      console.error('[BACKGROUND] Ошибка отправки на сервер:', err);
      sendResponse({ ok: false, error: err.message });
    });

  // true = оставляем канал открытым для асинхронного sendResponse.
  return true;
});
