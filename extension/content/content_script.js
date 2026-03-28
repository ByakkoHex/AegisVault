/**
 * content_script.js — AegisVault Autofill Content Script
 * ========================================================
 * Wykrywa formularze logowania, wyświetla chip autouzupełniania
 * i wypełnia pola poświadczeniami z AegisVault.
 *
 * Bezpieczeństwo:
 *  - Cały UI w zamkniętym Shadow DOM (mode: "closed")
 *  - Brak dostępu do prywatnych danych z poziomu strony
 *  - Komunikacja wyłącznie przez chrome.runtime.sendMessage → service worker
 */

(() => {
  "use strict";

  // Zapobiega wielokrotnemu wstrzyknięciu
  if (window.__aegisvaultInjected) return;
  window.__aegisvaultInjected = true;

  // ─────────────────────────────────────────────────────────────
  // WYKRYWANIE FORMULARZY
  // ─────────────────────────────────────────────────────────────

  const IGNORED_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "IFRAME", "OBJECT"]);

  /** Zwraca wszystkie widoczne pola hasła na stronie */
  function findPasswordFields() {
    return Array.from(document.querySelectorAll('input[type="password"]')).filter(
      (el) => !isHidden(el)
    );
  }

  function isHidden(el) {
    if (!el.offsetParent && el.style.display === "none") return true;
    const style = window.getComputedStyle(el);
    return style.display === "none" || style.visibility === "hidden" || style.opacity === "0";
  }

  /**
   * Szuka pola użytkownika skojarzonego z danym polem hasła.
   * Strategia: szuka w obrębie wspólnego rodzica formularza lub sekcji.
   */
  function findUsernameField(passwordField) {
    const USERNAME_TYPES = ["text", "email", "tel"];
    const USERNAME_ATTRS = /username|email|login|user|mail|phone|telefon/i;

    // Znajdź wspólnego przodka (form lub 5 poziomów wyżej)
    let container = passwordField.closest("form") || passwordField;
    for (let i = 0; i < 5 && container.parentElement; i++) {
      container = container.parentElement;
    }

    const candidates = Array.from(
      container.querySelectorAll('input:not([type="password"]):not([type="hidden"])')
    ).filter(
      (el) =>
        USERNAME_TYPES.includes(el.type || "text") &&
        !isHidden(el) &&
        (USERNAME_ATTRS.test(el.name || "") ||
          USERNAME_ATTRS.test(el.id || "") ||
          USERNAME_ATTRS.test(el.autocomplete || "") ||
          USERNAME_ATTRS.test(el.placeholder || "") ||
          el.type === "email")
    );

    // Preferuj kandydata bezpośrednio przed polem hasła w DOM
    if (candidates.length === 0) return null;

    // Zwróć ten który jest najbliżej (przed) polem hasła
    const passwordIndex = getDocumentIndex(passwordField);
    let best = candidates[0];
    let bestDist = Math.abs(getDocumentIndex(best) - passwordIndex);

    for (const c of candidates) {
      const dist = Math.abs(getDocumentIndex(c) - passwordIndex);
      if (dist < bestDist) {
        best = c;
        bestDist = dist;
      }
    }

    return best;
  }

  function getDocumentIndex(el) {
    return Array.from(document.querySelectorAll("*")).indexOf(el);
  }

  // ─────────────────────────────────────────────────────────────
  // CHIP AUTOUZUPEŁNIANIA (Shadow DOM)
  // ─────────────────────────────────────────────────────────────

  let activeChip = null;

  function removeChip() {
    if (activeChip) {
      activeChip.remove();
      activeChip = null;
    }
  }

  function createChip(credentials, usernameField, passwordField) {
    removeChip();

    const host = document.createElement("div");
    host.setAttribute("data-aegisvault", "chip");
    document.body.appendChild(host);

    const shadow = host.attachShadow({ mode: "closed" });

    // Style w shadow DOM
    const style = document.createElement("style");
    style.textContent = `
      :host { all: initial; }
      .chip {
        position: fixed;
        z-index: 2147483647;
        background: #1e1e2e;
        border: 1px solid #4F8EF7;
        border-radius: 8px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
        font-size: 13px;
        color: #e0e0e0;
        min-width: 260px;
        max-width: 340px;
        overflow: hidden;
        animation: fadeIn 0.15s ease;
      }
      @keyframes fadeIn { from { opacity:0; transform:translateY(-4px); } to { opacity:1; transform:none; } }
      .chip-header {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        background: #2a2a3e;
        border-bottom: 1px solid #333;
      }
      .chip-logo {
        width: 18px; height: 18px;
        background: #4F8EF7;
        border-radius: 4px;
        display: flex; align-items: center; justify-content: center;
        font-size: 11px; font-weight: bold; color: white;
        flex-shrink: 0;
      }
      .chip-title { font-weight: 600; color: #aabbff; flex: 1; }
      .chip-close {
        cursor: pointer; color: #777; font-size: 16px; line-height: 1;
        padding: 0 2px;
      }
      .chip-close:hover { color: #fff; }
      .chip-item {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 12px;
        cursor: pointer;
        border-bottom: 1px solid #2a2a2a;
        transition: background 0.1s;
      }
      .chip-item:last-child { border-bottom: none; }
      .chip-item:hover { background: #2d2d44; }
      .chip-avatar {
        width: 30px; height: 30px; border-radius: 6px;
        background: #4F8EF7;
        display: flex; align-items: center; justify-content: center;
        font-weight: bold; font-size: 13px; color: white;
        flex-shrink: 0;
      }
      .chip-info { flex: 1; min-width: 0; }
      .chip-site { font-weight: 600; font-size: 13px; color: #e0e0e0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .chip-user { font-size: 11px; color: #888; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .chip-fill-icon { color: #4F8EF7; font-size: 16px; }
    `;
    shadow.appendChild(style);

    const chip = document.createElement("div");
    chip.className = "chip";

    // Header
    const header = document.createElement("div");
    header.className = "chip-header";
    header.innerHTML = `
      <div class="chip-logo">AV</div>
      <span class="chip-title">Uzupełnij przez AegisVault</span>
      <span class="chip-close" title="Zamknij">✕</span>
    `;
    header.querySelector(".chip-close").addEventListener("click", removeChip);
    chip.appendChild(header);

    // Lista poświadczeń
    for (const cred of credentials) {
      const item = document.createElement("div");
      item.className = "chip-item";

      const initial = (cred.title || cred.username || "?")[0].toUpperCase();
      item.innerHTML = `
        <div class="chip-avatar">${initial}</div>
        <div class="chip-info">
          <div class="chip-site">${escapeHtml(cred.title)}</div>
          <div class="chip-user">${escapeHtml(cred.username || "")}</div>
        </div>
        <span class="chip-fill-icon">→</span>
      `;

      item.addEventListener("click", () => {
        fillFields(cred, usernameField, passwordField);
        removeChip();
      });

      chip.appendChild(item);
    }

    shadow.appendChild(chip);

    // Pozycjonowanie pod polem hasła/użytkownika
    const targetField = usernameField || passwordField;
    positionChip(host, chip, targetField);

    // Zamknij przy kliknięciu poza chipem
    document.addEventListener("click", handleOutsideClick, { once: false, capture: true });
    document.addEventListener("keydown", handleEscKey);

    activeChip = host;
    return host;
  }

  function positionChip(host, chip, targetField) {
    const rect = targetField.getBoundingClientRect();
    const scrollX = window.scrollX;
    const scrollY = window.scrollY;

    host.style.cssText = `position:absolute;top:0;left:0;pointer-events:none;z-index:2147483647;`;
    chip.style.position = "fixed";
    chip.style.top = `${rect.bottom + 4}px`;
    chip.style.left = `${rect.left}px`;

    // Jeśli chip wychodzi za prawy brzeg
    requestAnimationFrame(() => {
      const chipRect = chip.getBoundingClientRect();
      if (chipRect.right > window.innerWidth - 8) {
        chip.style.left = `${window.innerWidth - chipRect.width - 8}px`;
      }
      // Jeśli chip wychodzi za dolny brzeg — pokaż nad polem
      if (chipRect.bottom > window.innerHeight - 8) {
        chip.style.top = `${rect.top - chipRect.height - 4}px`;
      }
    });

    host.style.pointerEvents = "auto";
  }

  function handleOutsideClick(e) {
    if (activeChip && !activeChip.contains(e.target)) {
      removeChip();
      document.removeEventListener("click", handleOutsideClick, { capture: true });
      document.removeEventListener("keydown", handleEscKey);
    }
  }

  function handleEscKey(e) {
    if (e.key === "Escape") {
      removeChip();
      document.removeEventListener("click", handleOutsideClick, { capture: true });
      document.removeEventListener("keydown", handleEscKey);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // WYPEŁNIANIE PÓL
  // ─────────────────────────────────────────────────────────────

  function fillFields(credential, usernameField, passwordField) {
    if (usernameField && credential.username) {
      setNativeValue(usernameField, credential.username);
    }
    if (passwordField && credential.password) {
      setNativeValue(passwordField, credential.password);
    }
    showToast("AegisVault uzupełnił dane ✓");
  }

  /**
   * Ustawia wartość pola w sposób kompatybilny z React/Vue/Angular.
   * Dispatchuje zdarzenia input i change żeby frameworki zaktualizowały swój stan.
   */
  function setNativeValue(element, value) {
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value"
    )?.set;

    if (nativeInputValueSetter) {
      nativeInputValueSetter.call(element, value);
    } else {
      element.value = value;
    }

    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // ─────────────────────────────────────────────────────────────
  // TOAST (krótkie powiadomienie)
  // ─────────────────────────────────────────────────────────────

  function showToast(message) {
    const existing = document.querySelector("[data-aegisvault='toast']");
    if (existing) existing.remove();

    const host = document.createElement("div");
    host.setAttribute("data-aegisvault", "toast");
    document.body.appendChild(host);

    const shadow = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = `
      .toast {
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: #1e1e2e;
        border: 1px solid #4F8EF7;
        color: #e0e0e0;
        border-radius: 8px;
        padding: 10px 16px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
        font-size: 13px;
        z-index: 2147483647;
        animation: slideIn 0.2s ease;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      }
      @keyframes slideIn { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:none; } }
    `;
    shadow.appendChild(style);

    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    shadow.appendChild(toast);

    setTimeout(() => host.remove(), 2500);
  }

  // ─────────────────────────────────────────────────────────────
  // GŁÓWNA LOGIKA
  // ─────────────────────────────────────────────────────────────

  async function processPasswordField(passwordField) {
    const usernameField = findUsernameField(passwordField);

    // Pobierz pasujące poświadczenia z serwisu workera
    let response;
    try {
      response = await chrome.runtime.sendMessage({
        type: "GET_CREDENTIALS_FOR_URL",
        url: window.location.href,
      });
    } catch (_) {
      return; // Service worker niedostępny
    }

    if (!response?.ok || !response.data?.credentials?.length) return;

    const credentials = response.data.credentials;

    // Listener na focus pola
    passwordField.addEventListener("focus", () => {
      createChip(credentials, usernameField, passwordField);
    });

    if (usernameField) {
      usernameField.addEventListener("focus", () => {
        createChip(credentials, usernameField, passwordField);
      });
    }
  }

  async function scanForForms() {
    const passwordFields = findPasswordFields();
    for (const field of passwordFields) {
      if (!field.__aegisvaultProcessed) {
        field.__aegisvaultProcessed = true;
        processPasswordField(field);
      }
    }
  }

  // Obserwator mutacji dla SPA (React, Vue, Angular)
  const observer = new MutationObserver((mutations) => {
    let hasNewInputs = false;
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) {
          if (
            node.matches?.('input[type="password"]') ||
            node.querySelector?.('input[type="password"]')
          ) {
            hasNewInputs = true;
            break;
          }
        }
      }
      if (hasNewInputs) break;
    }
    if (hasNewInputs) {
      setTimeout(scanForForms, 100); // Czekaj chwilę aż DOM się ustabilizuje
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });

  // Skanowanie przy starcie
  scanForForms();

  // ─────────────────────────────────────────────────────────────
  // WIADOMOŚCI OD SERVICE WORKERA
  // ─────────────────────────────────────────────────────────────

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "FILL_FIELDS") {
      const passwordFields = findPasswordFields();
      if (passwordFields.length === 0) {
        sendResponse({ ok: false, error: "NO_PASSWORD_FIELD" });
        return;
      }

      const passwordField = passwordFields[0];
      const usernameField = findUsernameField(passwordField);
      fillFields(message.credential, usernameField, passwordField);
      sendResponse({ ok: true });
    }

    if (message.type === "TRIGGER_AUTOFILL") {
      const passwordFields = findPasswordFields();
      if (passwordFields.length > 0) {
        passwordFields[0].dispatchEvent(new Event("focus", { bubbles: true }));
      }
    }
  });

  // ─────────────────────────────────────────────────────────────
  // UTILS
  // ─────────────────────────────────────────────────────────────

  function escapeHtml(str) {
    return (str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
})();
