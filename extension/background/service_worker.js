/**
 * service_worker.js — AegisVault Background Service Worker
 * ==========================================================
 * Zarządza połączeniem z natywnym hostem (aegisvault_host.py),
 * stanem sesji i routingiem wiadomości między popup ↔ content script ↔ host.
 *
 * Architektura:
 *   Popup / ContentScript
 *       ↕ chrome.runtime.sendMessage
 *   Service Worker (ten plik)
 *       ↕ chrome.runtime.connectNative("com.aegisvault.host")
 *   Python Native Host (native_host/aegisvault_host.py)
 */

const HOST_NAME = "com.aegisvault.host";
const SESSION_TIMEOUT_MS = 5 * 60 * 1000; // 5 minut = jak w desktop

// Port do natywnego hosta (może być null gdy host nie jest połączony)
let nativePort = null;

// Mapa oczekujących żądań: request_id → { resolve, reject, timer }
const pendingRequests = new Map();

// ─────────────────────────────────────────────────────────────
// ZARZĄDZANIE POŁĄCZENIEM Z NATYWNYM HOSTEM
// ─────────────────────────────────────────────────────────────

function connectToHost() {
  if (nativePort) return nativePort;

  try {
    nativePort = chrome.runtime.connectNative(HOST_NAME);

    nativePort.onMessage.addListener((message) => {
      const pending = pendingRequests.get(message.request_id);
      if (pending) {
        clearTimeout(pending.timer);
        pendingRequests.delete(message.request_id);
        if (message.ok) {
          pending.resolve(message);
        } else {
          pending.reject(new Error(message.error || "UNKNOWN_ERROR"));
        }
      }
    });

    nativePort.onDisconnect.addListener(() => {
      nativePort = null;
      // Odrzuć wszystkie oczekujące żądania
      for (const [id, pending] of pendingRequests) {
        clearTimeout(pending.timer);
        pending.reject(new Error("HOST_DISCONNECTED"));
      }
      pendingRequests.clear();
      // Uaktualnij stan sesji
      setSessionLocked();
    });

    console.log("[AegisVault SW] Połączono z hostem natywnym.");
    return nativePort;
  } catch (err) {
    console.error("[AegisVault SW] Błąd połączenia z hostem:", err);
    nativePort = null;
    return null;
  }
}

/**
 * Wysyła wiadomość do natywnego hosta i zwraca Promise z odpowiedzią.
 * Timeout: 10 sekund (dla UNLOCK może być dłużej przez PBKDF2).
 */
function sendToHost(message, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const port = connectToHost();
    if (!port) {
      reject(new Error("NATIVE_HOST_UNAVAILABLE"));
      return;
    }

    const requestId = crypto.randomUUID();
    const fullMessage = { ...message, request_id: requestId };

    const timer = setTimeout(() => {
      pendingRequests.delete(requestId);
      reject(new Error("HOST_TIMEOUT"));
    }, timeoutMs);

    pendingRequests.set(requestId, { resolve, reject, timer });

    try {
      port.postMessage(fullMessage);
    } catch (err) {
      clearTimeout(timer);
      pendingRequests.delete(requestId);
      reject(err);
    }
  });
}

// ─────────────────────────────────────────────────────────────
// ZARZĄDZANIE SESJĄ (chrome.storage.session)
// ─────────────────────────────────────────────────────────────

async function getSessionState() {
  const data = await chrome.storage.session.get(["unlocked", "username", "session_expires_at"]);
  return {
    unlocked: data.unlocked === true,
    username: data.username || null,
    expiresAt: data.session_expires_at ? new Date(data.session_expires_at) : null,
  };
}

async function setSessionUnlocked(username) {
  const expiresAt = new Date(Date.now() + SESSION_TIMEOUT_MS);
  await chrome.storage.session.set({
    unlocked: true,
    username,
    session_expires_at: expiresAt.toISOString(),
  });
  updateBadge(true);
  scheduleSessionCheck();
}

async function setSessionLocked() {
  await chrome.storage.session.set({
    unlocked: false,
    username: null,
    session_expires_at: null,
  });
  updateBadge(false);
}

async function isSessionValid() {
  const state = await getSessionState();
  if (!state.unlocked) return false;
  if (!state.expiresAt || state.expiresAt <= new Date()) {
    await setSessionLocked();
    return false;
  }
  return true;
}

async function refreshSessionExpiry() {
  const state = await getSessionState();
  if (state.unlocked) {
    const expiresAt = new Date(Date.now() + SESSION_TIMEOUT_MS);
    await chrome.storage.session.set({ session_expires_at: expiresAt.toISOString() });
  }
}

// ─────────────────────────────────────────────────────────────
// BADGE
// ─────────────────────────────────────────────────────────────

function updateBadge(unlocked) {
  if (unlocked) {
    chrome.action.setBadgeText({ text: "" });
    chrome.action.setTitle({ title: "AegisVault — Odblokowany" });
  } else {
    chrome.action.setBadgeText({ text: "🔒" });
    chrome.action.setBadgeBackgroundColor({ color: "#cc3333" });
    chrome.action.setTitle({ title: "AegisVault — Zablokowany" });
  }
}

// ─────────────────────────────────────────────────────────────
// ALARMY (sprawdzanie wygaśnięcia sesji)
// ─────────────────────────────────────────────────────────────

function scheduleSessionCheck() {
  chrome.alarms.create("session_check", { periodInMinutes: 1 });
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "session_check") {
    const valid = await isSessionValid();
    if (!valid) {
      chrome.alarms.clear("session_check");
    }
  }
});

// ─────────────────────────────────────────────────────────────
// HANDLERY WIADOMOŚCI
// ─────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender)
    .then(sendResponse)
    .catch((err) => sendResponse({ ok: false, error: err.message }));
  return true; // keep channel open for async response
});

async function handleMessage(message, sender) {
  switch (message.type) {
    case "CHECK_SESSION": {
      const state = await getSessionState();
      const valid = await isSessionValid();
      return { ok: true, unlocked: valid, username: state.username };
    }

    case "UNLOCK": {
      const response = await sendToHost({
        type: "UNLOCK",
        username: message.username,
        master_password: message.master_password,
        totp_code: message.totp_code || null,
      });
      if (response.ok) {
        await setSessionUnlocked(message.username);
      }
      return response;
    }

    case "LOCK": {
      try {
        await sendToHost({ type: "LOCK" });
      } catch (_) {
        // Ignoruj błąd hosta — i tak zablokujemy sesję lokalnie
      }
      await setSessionLocked();
      return { ok: true };
    }

    case "GET_CREDENTIALS_FOR_URL": {
      if (!(await isSessionValid())) return { ok: false, error: "SESSION_EXPIRED" };
      const resp = await sendToHost({
        type: "GET_CREDENTIALS_FOR_URL",
        url: message.url,
      });
      if (resp.ok) await refreshSessionExpiry();
      return resp;
    }

    case "GET_ALL_CREDENTIALS": {
      if (!(await isSessionValid())) return { ok: false, error: "SESSION_EXPIRED" };
      const resp = await sendToHost({
        type: "GET_ALL_CREDENTIALS",
        search: message.search || null,
      });
      if (resp.ok) await refreshSessionExpiry();
      return resp;
    }

    case "GET_CREDENTIAL_BY_ID": {
      if (!(await isSessionValid())) return { ok: false, error: "SESSION_EXPIRED" };
      const resp = await sendToHost({
        type: "GET_CREDENTIAL_BY_ID",
        id: message.id,
      });
      if (resp.ok) await refreshSessionExpiry();
      return resp;
    }

    case "FILL_FORM": {
      // Przekaż dane do content script aktywnej karty
      if (!(await isSessionValid())) return { ok: false, error: "SESSION_EXPIRED" };

      const credResp = await sendToHost({
        type: "GET_CREDENTIAL_BY_ID",
        id: message.credential_id,
      });
      if (!credResp.ok) return credResp;

      const tabId = message.tab_id;
      await chrome.tabs.sendMessage(tabId, {
        type: "FILL_FIELDS",
        credential: credResp.data,
      });
      await refreshSessionExpiry();
      return { ok: true };
    }

    case "PING": {
      try {
        const resp = await sendToHost({ type: "PING" });
        return resp;
      } catch (err) {
        return { ok: false, error: err.message };
      }
    }

    default:
      return { ok: false, error: "UNKNOWN_MESSAGE_TYPE" };
  }
}

// ─────────────────────────────────────────────────────────────
// SKRÓT KLAWISZOWY (Alt+Shift+F)
// ─────────────────────────────────────────────────────────────

chrome.commands.onCommand.addListener(async (command) => {
  if (command === "autofill") {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) return;

    if (!(await isSessionValid())) {
      // Otwórz popup żeby użytkownik się zalogował
      chrome.action.openPopup();
      return;
    }

    chrome.tabs.sendMessage(tab.id, { type: "TRIGGER_AUTOFILL" });
  }
});

// ─────────────────────────────────────────────────────────────
// INICJALIZACJA
// ─────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  setSessionLocked();
  console.log("[AegisVault SW] Rozszerzenie zainstalowane.");
});

// Przy starcie service workera odśwież stan badge
getSessionState().then((state) => {
  isSessionValid().then((valid) => updateBadge(valid));
});
