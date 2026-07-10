const AGENT_URL = 'http://127.0.0.1:8003';

function setStatus(text, color = '#333') {
  const el = document.getElementById('status');
  el.textContent = text;
  el.style.color = color;
}

async function checkAgent() {
  try {
    const response = await chrome.runtime.sendMessage({ type: 'check_agent' });
    if (response.ok) {
      document.getElementById('agent-status').textContent = 'OK';
      document.getElementById('agent-status').style.color = 'green';
    } else {
      document.getElementById('agent-status').textContent = 'ошибка';
      document.getElementById('agent-status').style.color = 'red';
      setStatus('Агент недоступен: ' + response.error, 'red');
    }
  } catch (e) {
    document.getElementById('agent-status').textContent = 'не доступен';
    document.getElementById('agent-status').style.color = 'red';
    setStatus('Агент не отвечает', 'red');
  }
}

async function sendToken(token) {
  if (!token) {
    setStatus('Токен пустой', 'red');
    return;
  }
  setStatus('Отправка...', '#333');
  try {
    const response = await chrome.runtime.sendMessage({
      type: 'send_token',
      token: token,
      key: 'popup',
      source: 'manual',
    });

    if (response.ok) {
      setStatus('Успех: ' + (response.cached ? 'токен уже был отправлен' : 'токен отправлен'), 'green');
    } else if (response.queued) {
      setStatus('Агент недоступен, токен поставлен в очередь', 'orange');
    } else {
      setStatus('Ошибка: ' + (response.error || 'неизвестная'), 'red');
    }
  } catch (err) {
    setStatus('Ошибка: ' + err.message, 'red');
  }
}

function generateTestToken() {
  const header = btoa(JSON.stringify({ alg: 'none', typ: 'JWT' }))
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
  const exp = Math.floor(Date.now() / 1000) + 3600;
  const payload = btoa(JSON.stringify({ exp, iat: Math.floor(Date.now() / 1000), sub: 'test' }))
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
  return `${header}.${payload}.`;
}

async function scanStorage() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) {
      setStatus('Не удалось получить активную вкладку', 'red');
      return;
    }

    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const data = { localStorage: {}, sessionStorage: {} };
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (key) data.localStorage[key] = localStorage.getItem(key);
        }
        for (let i = 0; i < sessionStorage.length; i++) {
          const key = sessionStorage.key(i);
          if (key) data.sessionStorage[key] = sessionStorage.getItem(key);
        }
        return data;
      },
    });

    const dump = results[0]?.result || {};
    chrome.runtime.sendMessage({ type: 'storage_dump', dump });

    // Попытка найти и отправить токен вручную через popup
    const keys = [
      ...Object.keys(dump.localStorage || {}),
      ...Object.keys(dump.sessionStorage || {}),
    ].join(', ') || 'пусто';
    setStatus('Найдены ключи: ' + keys, 'green');
  } catch (err) {
    setStatus('Ошибка сканирования: ' + err.message, 'red');
  }
}

document.getElementById('btn-test').addEventListener('click', () => {
  const token = generateTestToken();
  document.getElementById('manual-token').value = token;
  sendToken(token);
});

document.getElementById('btn-send').addEventListener('click', () => {
  const token = document.getElementById('manual-token').value.trim();
  sendToken(token);
});

document.getElementById('btn-scan').addEventListener('click', scanStorage);

checkAgent();
