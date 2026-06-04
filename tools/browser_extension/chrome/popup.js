const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

let config = { apiBaseUrl: DEFAULT_API_BASE_URL, apiKey: "" };
let pendingItems = [];
let currentIndex = 0;
let previewObjectUrl = "";

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await loadConfig();
  await refreshState();
  await checkBackend();
});

function bindEvents() {
  document.getElementById("settingsToggle").addEventListener("click", () => {
    document.getElementById("settingsPanel").classList.toggle("hidden");
  });
  document.getElementById("saveSettings").addEventListener("click", saveConfig);
  document.getElementById("discardButton").addEventListener("click", discardCurrent);
  document.getElementById("commitButton").addEventListener("click", commitCurrent);
}

async function loadConfig() {
  const result = await chrome.storage.local.get(["apiBaseUrl", "apiKey"]);
  config = {
    apiBaseUrl: normalizeApiBaseUrl(result.apiBaseUrl || DEFAULT_API_BASE_URL),
    apiKey: result.apiKey || ""
  };
  document.getElementById("apiBaseUrl").value = config.apiBaseUrl;
  document.getElementById("apiKey").value = config.apiKey;
}

async function saveConfig() {
  config = {
    apiBaseUrl: normalizeApiBaseUrl(document.getElementById("apiBaseUrl").value),
    apiKey: document.getElementById("apiKey").value.trim()
  };
  await chrome.storage.local.set(config);
  document.getElementById("settingsPanel").classList.add("hidden");
  await checkBackend();
  await render();
}

function normalizeApiBaseUrl(value) {
  return String(value || DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}

async function refreshState() {
  const result = await chrome.storage.local.get({ pendingItems: [], lastError: "" });
  pendingItems = Array.isArray(result.pendingItems) ? result.pendingItems : [];
  if (currentIndex >= pendingItems.length) {
    currentIndex = Math.max(0, pendingItems.length - 1);
  }
  showError(result.lastError || "");
  await render();
}

async function checkBackend() {
  const status = document.getElementById("statusText");
  try {
    const res = await fetch(`${config.apiBaseUrl}/`);
    status.textContent = res.ok ? "Backend online" : "Backend unavailable";
  } catch {
    status.textContent = "Backend unavailable";
  }
}

async function render() {
  const itemPanel = document.getElementById("itemPanel");
  const emptyPanel = document.getElementById("emptyPanel");
  if (!pendingItems.length) {
    itemPanel.classList.add("hidden");
    emptyPanel.classList.remove("hidden");
    await updateBadge(0);
    return;
  }

  itemPanel.classList.remove("hidden");
  emptyPanel.classList.add("hidden");
  await updateBadge(pendingItems.length);

  const item = pendingItems[currentIndex];
  const isCapture = item.kind === "capture";
  document.getElementById("itemKind").textContent = isCapture ? "Capture" : "Online Queue";
  document.getElementById("itemTitle").textContent = item.page_title || item.original_name || "Untitled";
  document.getElementById("itemUrl").textContent = isCapture ? item.source_url || item.media_url : item.url;
  document.getElementById("itemCounter").textContent = `${currentIndex + 1}/${pendingItems.length}`;
  document.getElementById("platformSelect").value = platformValue(item.platform_guess);
  document.getElementById("queueWrap").classList.toggle("hidden", isCapture);
  document.getElementById("commitButton").textContent = isCapture ? "Commit to Vault" : "Append Queue";

  const previewWrap = document.getElementById("previewWrap");
  if (isCapture) {
    previewWrap.classList.remove("hidden");
    await loadPreview(item.staged_id);
  } else {
    previewWrap.classList.add("hidden");
    clearPreview();
  }
}

async function loadPreview(stagedId) {
  clearPreview();
  try {
    const res = await fetch(`${config.apiBaseUrl}/api/capture/preview/${encodeURIComponent(stagedId)}`, {
      headers: { "X-LMZ-API-KEY": config.apiKey }
    });
    if (!res.ok) {
      throw new Error(`Preview failed: ${res.status}`);
    }
    const blob = await res.blob();
    previewObjectUrl = URL.createObjectURL(blob);
    document.getElementById("previewImage").src = previewObjectUrl;
  } catch (error) {
    showError(error.message);
  }
}

function clearPreview() {
  if (previewObjectUrl) {
    URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = "";
  }
  document.getElementById("previewImage").removeAttribute("src");
}

function platformValue(value) {
  const known = ["General Web", "X", "Pixiv", "Instagram", "Pinterest"];
  return known.includes(value) ? value : "General Web";
}

async function discardCurrent() {
  const item = pendingItems[currentIndex];
  if (item?.kind === "capture") {
    await fetch(`${config.apiBaseUrl}/api/capture/stage/${encodeURIComponent(item.staged_id)}`, {
      method: "DELETE",
      headers: { "X-LMZ-API-KEY": config.apiKey }
    }).catch(() => {});
  }
  pendingItems.splice(currentIndex, 1);
  await chrome.storage.local.set({ pendingItems, lastError: "" });
  document.getElementById("artistInput").value = "";
  await refreshState();
}

async function commitCurrent() {
  const item = pendingItems[currentIndex];
  const artist = document.getElementById("artistInput").value.trim();
  const platform = document.getElementById("platformSelect").value;
  try {
    const response = item.kind === "capture"
      ? await commitCapture(item, artist, platform)
      : await appendOnlineQueue(item, artist, platform);
    const payload = await safeJson(response);
    if (!response.ok || payload.success === false) {
      throw new Error(payload.detail || payload.message || `Request failed: ${response.status}`);
    }
    pendingItems.splice(currentIndex, 1);
    await chrome.storage.local.set({ pendingItems, lastError: "" });
    document.getElementById("artistInput").value = "";
    await refreshState();
  } catch (error) {
    showError(error.message);
    await chrome.storage.local.set({ lastError: error.message });
  }
}

function commitCapture(item, artist, platform) {
  return fetch(`${config.apiBaseUrl}/api/capture/commit`, {
    method: "POST",
    headers: {
      "X-LMZ-API-KEY": config.apiKey,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      staged_id: item.staged_id,
      artist,
      platform
    })
  });
}

function appendOnlineQueue(item, artist, platform) {
  const queue = document.getElementById("queueSelect").value;
  return fetch(`${config.apiBaseUrl}/api/queue/${queue}/append`, {
    method: "POST",
    headers: {
      "X-LMZ-API-KEY": config.apiKey,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      url: item.url,
      artist,
      platform
    })
  });
}

async function updateBadge(count) {
  chrome.action.setBadgeText({ text: count > 0 ? String(count) : "" });
  chrome.action.setBadgeBackgroundColor({ color: "#1f6feb" });
}

function showError(message) {
  const panel = document.getElementById("errorPanel");
  if (!message) {
    panel.textContent = "";
    panel.classList.add("hidden");
    return;
  }
  panel.textContent = message;
  panel.classList.remove("hidden");
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}
