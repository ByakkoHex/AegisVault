/**
 * popup.js — AegisVault Extension Popup
 * =======================================
 * Trzy widoki: Locked → Unlocked (lista) → Detail (szczegóły)
 */

"use strict";

// ─────────────────────────────────────────────────────────────
// STAN
// ─────────────────────────────────────────────────────────────

let allCredentials = [];    // pełna lista (bez haseł)
let filteredCredentials = [];
let selectedCredential = null;
let detailCredential = null; // z hasłem (po GET_CREDENTIAL_BY_ID)
let currentTab = null;
let sessionUsername = null;
let sessionTimerInterval = null;

// ─────────────────────────────────────────────────────────────
// ELEMENTY DOM
// ─────────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);

const views = {
  locked:   $("view-locked"),
  unlocked: $("view-unlocked"),
  detail:   $("view-detail"),
};

// ─────────────────────────────────────────────────────────────
// ROUTER WIDOKÓW
// ─────────────────────────────────────────────────────────────

function showView(name) {
  for (const [key, el] of Object.entries(views)) {
    el.classList.toggle("hidden", key !== name);
  }
}

// ─────────────────────────────────────────────────────────────
// KOMUNIKACJA Z SERVICE WORKEREM
// ─────────────────────────────────────────────────────────────

async function sw(message) {
  return chrome.runtime.sendMessage(message);
}

// ─────────────────────────────────────────────────────────────
// SPINNER
// ─────────────────────────────────────────────────────────────

function showSpinner() { $("spinner").classList.remove("hidden"); }
function hideSpinner() { $("spinner").classList.add("hidden"); }

// ─────────────────────────────────────────────────────────────
// WIDOK A: ZABLOKOWANY
// ─────────────────────────────────────────────────────────────

function showError(msg) {
  const el = $("error-msg");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function hideError() {
  $("error-msg").classList.add("hidden");
}

$("btn-toggle-pw").addEventListener("click", () => {
  const inp = $("input-password");
  inp.type = inp.type === "password" ? "text" : "password";
});

$("btn-unlock").addEventListener("click", handleUnlock);
$("input-password").addEventListener("keydown", (e) => {
  if (e.key === "Enter") handleUnlock();
});
$("input-totp").addEventListener("keydown", (e) => {
  if (e.key === "Enter") handleUnlock();
});

async function handleUnlock() {
  const username = $("input-username").value.trim();
  const password = $("input-password").value;
  const totp     = $("input-totp").value.trim() || null;

  if (!username) { showError("Podaj nazwę użytkownika."); return; }
  if (!password) { showError("Podaj hasło główne."); return; }

  hideError();
  $("btn-unlock").disabled = true;
  showSpinner();

  try {
    const resp = await sw({ type: "UNLOCK", username, master_password: password, totp_code: totp });

    if (resp.ok) {
      $("input-password").value = "";
      sessionUsername = username;
      await loadUnlockedView();
    } else if (resp.error === "TOTP_REQUIRED") {
      $("totp-section").classList.remove("hidden");
      $("input-totp").focus();
      showError("Wymagany kod 2FA.");
    } else if (resp.error === "INVALID_TOTP") {
      showError("Nieprawidłowy kod 2FA.");
      $("input-totp").value = "";
      $("input-totp").focus();
    } else {
      showError("Nieprawidłowy login lub hasło.");
      $("input-password").value = "";
    }
  } catch (err) {
    showError("Błąd połączenia z hostem AegisVault. Czy aplikacja jest zainstalowana?");
    console.error("[AegisVault Popup] UNLOCK error:", err);
  } finally {
    $("btn-unlock").disabled = false;
    hideSpinner();
  }
}

// ─────────────────────────────────────────────────────────────
// WIDOK B: ODBLOKOWANY
// ─────────────────────────────────────────────────────────────

async function loadUnlockedView() {
  showSpinner();
  try {
    const resp = await sw({ type: "GET_ALL_CREDENTIALS" });
    if (!resp.ok) {
      if (resp.error === "SESSION_EXPIRED") { showView("locked"); return; }
      throw new Error(resp.error);
    }

    allCredentials = resp.data.credentials || [];
    filteredCredentials = [...allCredentials];

    $("lbl-username").textContent = sessionUsername;
    showView("unlocked");
    renderCredentialList(filteredCredentials);
    startSessionTimer();
    await checkCurrentTabForFillBar();
  } catch (err) {
    console.error("[AegisVault Popup] loadUnlockedView error:", err);
    showView("locked");
  } finally {
    hideSpinner();
  }
}

function renderCredentialList(credentials) {
  const list = $("cred-list");
  const empty = $("cred-empty");
  list.innerHTML = "";

  if (credentials.length === 0) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  for (const cred of credentials) {
    const item = createCredentialItem(cred);
    list.appendChild(item);
  }
}

function createCredentialItem(cred) {
  const div = document.createElement("div");
  div.className = "cred-item";
  if (selectedCredential?.id === cred.id) div.classList.add("selected");

  const initial = (cred.title || cred.username || "?")[0].toUpperCase();
  const avatarClass = getCategoryClass(cred.category);

  div.innerHTML = `
    <div class="cred-avatar ${avatarClass}">${escapeHtml(initial)}</div>
    <div class="cred-info">
      <div class="cred-title">${escapeHtml(cred.title)}</div>
      <div class="cred-user">${escapeHtml(cred.username || "")}</div>
    </div>
    <span class="cred-arrow">›</span>
  `;

  div.addEventListener("click", () => openDetail(cred));
  return div;
}

function getCategoryClass(category) {
  const map = {
    "Social Media": "cat-social",
    "Praca":        "cat-work",
    "Bankowość":    "cat-bank",
    "Rozrywka":     "cat-entertainment",
    "Inne":         "cat-other",
  };
  return map[category] || "cat-other";
}

// Wyszukiwanie
$("input-search").addEventListener("input", (e) => {
  const query = e.target.value.toLowerCase();
  filteredCredentials = allCredentials.filter((c) =>
    (c.title || "").toLowerCase().includes(query) ||
    (c.username || "").toLowerCase().includes(query) ||
    (c.url || "").toLowerCase().includes(query)
  );
  renderCredentialList(filteredCredentials);
});

// Przycisk blokady
$("btn-lock").addEventListener("click", async () => {
  await sw({ type: "LOCK" });
  stopSessionTimer();
  showView("locked");
});

// ─────────────────────────────────────────────────────────────
// FILL BAR (uzupełnij aktualną stronę)
// ─────────────────────────────────────────────────────────────

async function checkCurrentTabForFillBar() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    currentTab = tab;
    if (!tab?.url) return;

    const resp = await sw({ type: "GET_CREDENTIALS_FOR_URL", url: tab.url });
    if (resp.ok && resp.data?.credentials?.length > 0) {
      const count = resp.data.credentials.length;
      const host = new URL(tab.url).hostname;
      $("fill-bar-text").textContent = `${count} wpis${count > 1 ? "y" : ""} dla ${host}`;
      $("fill-bar").classList.remove("hidden");
    }
  } catch (_) {}
}

$("btn-fill-page").addEventListener("click", async () => {
  if (!selectedCredential || !currentTab) return;
  await fillOnTab(selectedCredential.id, currentTab.id);
  window.close();
});

async function fillOnTab(credentialId, tabId) {
  showSpinner();
  try {
    await sw({ type: "FILL_FORM", credential_id: credentialId, tab_id: tabId });
  } catch (err) {
    console.error("[AegisVault Popup] fillOnTab error:", err);
  } finally {
    hideSpinner();
  }
}

// ─────────────────────────────────────────────────────────────
// WIDOK C: SZCZEGÓŁY
// ─────────────────────────────────────────────────────────────

async function openDetail(cred) {
  selectedCredential = cred;

  // Zaznacz w liście
  document.querySelectorAll(".cred-item").forEach((el) => el.classList.remove("selected"));

  showSpinner();
  try {
    const resp = await sw({ type: "GET_CREDENTIAL_BY_ID", id: cred.id });
    if (!resp.ok) {
      if (resp.error === "SESSION_EXPIRED") { showView("locked"); return; }
      throw new Error(resp.error);
    }

    detailCredential = resp.data;
    renderDetailView(detailCredential);
    showView("detail");
  } catch (err) {
    console.error("[AegisVault Popup] openDetail error:", err);
  } finally {
    hideSpinner();
  }
}

function renderDetailView(cred) {
  $("detail-title").textContent    = cred.title || "";
  $("detail-username").textContent = cred.username || "—";
  $("detail-category").textContent = cred.category || "Inne";

  // Hasło — domyślnie zamaskowane
  $("detail-password").textContent = "••••••••";
  $("detail-password").classList.add("masked");
  $("detail-password").dataset.plain = cred.password || "";

  // URL
  const urlRow = $("detail-url-row");
  if (cred.url) {
    $("detail-url").textContent = cred.url;
    urlRow.classList.remove("hidden");
  } else {
    urlRow.classList.add("hidden");
  }

  // Notatki
  const notesRow = $("detail-notes-row");
  if (cred.notes) {
    $("detail-notes").textContent = cred.notes;
    notesRow.classList.remove("hidden");
  } else {
    notesRow.classList.add("hidden");
  }

  // Przycisk "Uzupełnij stronę"
  $("btn-fill-detail").classList.toggle("hidden", !currentTab);
}

$("btn-back").addEventListener("click", () => {
  showView("unlocked");
});

$("btn-reveal").addEventListener("click", () => {
  const el = $("detail-password");
  if (el.classList.contains("masked")) {
    el.textContent = el.dataset.plain;
    el.classList.remove("masked");
  } else {
    el.textContent = "••••••••";
    el.classList.add("masked");
  }
});

// Kopiowanie
document.querySelectorAll(".btn-copy[data-copy]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const field = btn.dataset.copy;
    let text = "";
    if (field === "username") text = detailCredential?.username || "";
    if (field === "password") text = detailCredential?.password || "";

    if (!text) return;
    await navigator.clipboard.writeText(text);

    const original = btn.textContent;
    btn.textContent = "✓";
    setTimeout(() => { btn.textContent = original; }, 1500);
  });
});

$("btn-fill-detail").addEventListener("click", async () => {
  if (!detailCredential || !currentTab) return;
  await fillOnTab(detailCredential.id, currentTab.id);
  window.close();
});

// ─────────────────────────────────────────────────────────────
// TIMER SESJI
// ─────────────────────────────────────────────────────────────

function startSessionTimer() {
  stopSessionTimer();
  sessionTimerInterval = setInterval(updateSessionTimer, 5000);
  updateSessionTimer();
}

function stopSessionTimer() {
  if (sessionTimerInterval) {
    clearInterval(sessionTimerInterval);
    sessionTimerInterval = null;
  }
}

async function updateSessionTimer() {
  try {
    const data = await chrome.storage.session.get("session_expires_at");
    if (!data.session_expires_at) { stopSessionTimer(); return; }

    const remaining = new Date(data.session_expires_at) - new Date();
    if (remaining <= 0) {
      stopSessionTimer();
      showView("locked");
      return;
    }

    const minutes = Math.ceil(remaining / 60000);
    $("session-timer").textContent = `🔒 za ${minutes} min`;
  } catch (_) {}
}

// ─────────────────────────────────────────────────────────────
// INICJALIZACJA
// ─────────────────────────────────────────────────────────────

async function init() {
  const resp = await sw({ type: "CHECK_SESSION" });
  if (resp.unlocked) {
    sessionUsername = resp.username;
    await loadUnlockedView();
  } else {
    showView("locked");
  }
}

function escapeHtml(str) {
  return (str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

init();
