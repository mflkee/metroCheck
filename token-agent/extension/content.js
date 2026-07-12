// content.js — выполняется внутри веб-страницы в изолированном мире (isolated world).
// Имеет доступ к DOM и localStorage.

// Опрос localStorage['u'] каждые 3 секунды.
const POLL_INTERVAL_MS = 3000;

// Храним последний отправленный токен, чтобы не слать дубли.
let lastSentToken = null;


/**
 * Достаем токен из localStorage['u'].
 * В Аршине localStorage['u'] — JSON-строка с объектом, внутри которого поле token.
 */
function extractToken() {
  try {
    const raw = window.localStorage.getItem('u');
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw);
    return parsed && parsed.token ? parsed.token : null;
  } catch (err) {
    console.error('[CONTENT] Ошибка при чтении localStorage:', err);
    return null;
  }
}


/**
 * Отправляем токен в background.js (service worker).
 */
function sendToken(token) {
  if (token === lastSentToken) {
    console.log('[CONTENT] Токен не изменился, пропускаю отправку');
    return;
  }

  console.log('[CONTENT] Новый токен найден, отправляю в background.js');

  chrome.runtime.sendMessage(
    {
      type: 'TOKEN_FOUND',
      token: token,
      url: window.location.href,
      timestamp: Date.now()
    },
    (response) => {
      console.log('[CONTENT] Ответ от background.js:', response);

      // Запоминаем только при успешной отправке.
      if (response && response.ok) {
        lastSentToken = token;
      } else {
        console.log('[CONTENT] Отправка не удалась, буду повторять');
      }
    }
  );
}


function poll() {
  const token = extractToken();
  if (token) {
    sendToken(token);
  }
}


// Первый запуск сразу после загрузки страницы.
poll();

// Запускаем опрос каждые 3 секунды.
setInterval(poll, POLL_INTERVAL_MS);
