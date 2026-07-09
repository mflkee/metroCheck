const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const tokenInput = document.getElementById('token-input');
const sendBtn = document.getElementById('send-btn');
const testBtn = document.getElementById('test-btn');
const scanBtn = document.getElementById('scan-btn');
const resultBox = document.getElementById('result');

function setStatus(text, type = 'pending') {
  statusText.textContent = text;
  statusDot.className = 'dot';
  if (type === 'ok') statusDot.classList.add('ok');
  if (type === 'error') statusDot.classList.add('error');
}

function showResult(text, ok) {
  resultBox.textContent = text;
  resultBox.className = 'result' + (ok ? ' ok' : ' error');
}

async function checkAgent() {
  try {
    const response = await fetch('http://127.0.0.1:8003/health');
    if (response.ok) {
      const data = await response.json();
      setStatus(`Агент на порту 8003 — ${data.status}`, 'ok');
    } else {
      setStatus(`Агент ответил ${response.status}`, 'error');
    }
  } catch (err) {
    setStatus('Агент не доступен (127.0.0.1:8003)', 'error');
  }
}

async function sendToken(token) {
  if (!token) {
    showResult('Вставь токен', false);
    return;
  }

  sendBtn.disabled = true;
  testBtn.disabled = true;
  scanBtn.disabled = true;

  try {
    const response = await chrome.runtime.sendMessage({
      type: 'send_token',
      token: token,
      key: 'popup',
      source: 'manual',
    });

    if (response && response.ok) {
      showResult('Токен отправлен и сохранён агентом', true);
    } else {
      showResult('Ошибка: ' + (response?.error || 'неизвестная ошибка'), false);
    }
  } catch (err) {
    showResult('Ошибка: ' + err.message, false);
  } finally {
    sendBtn.disabled = false;
    testBtn.disabled = false;
    scanBtn.disabled = false;
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

sendBtn.addEventListener('click', () => sendToken(tokenInput.value.trim()));

testBtn.addEventListener('click', () => {
  const token = generateTestToken();
  tokenInput.value = token;
  sendToken(token);
});

scanBtn.addEventListener('click', async () => {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) {
      showResult('Не удалось получить активную вкладку', false);
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

    const keys = [
      ...Object.keys(dump.localStorage || {}),
      ...Object.keys(dump.sessionStorage || {}),
    ].join(', ') || 'пусто';
    showResult('Найдены ключи: ' + keys, true);
  } catch (err) {
    showResult('Ошибка сканирования: ' + err.message, false);
  }
});

checkAgent();
