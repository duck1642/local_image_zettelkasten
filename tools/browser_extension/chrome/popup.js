import { addItem, deleteItem, getItem, listItems, updateItem } from "./db.js";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

let config = { apiBaseUrl: DEFAULT_API_BASE_URL, apiKey: "" };
let pendingItems = [];
let currentIndex = 0;
let previewObjectUrl = "";
let actionInFlight = false;

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await loadConfig();
  await migrateLegacyPendingItems();
  await refreshState();
  await checkBackend();
});

function bindEvents() {
  document.getElementById("settingsToggle").addEventListener("click", () => {
    document.getElementById("settingsPanel").classList.toggle("hidden");
  });
  document.getElementById("saveSettings").addEventListener("click", saveConfig);
  document.getElementById("discardButton").addEventListener("click", discardCurrent);
  document.getElementById("commitButton").addEventListener("click", primaryAction);
  document.getElementById("prevButton").addEventListener("click", () => moveCurrent(-1));
  document.getElementById("nextButton").addEventListener("click", () => moveCurrent(1));
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

async function migrateLegacyPendingItems() {
  const result = await chrome.storage.local.get({ pendingItems: [] });
  const legacyItems = Array.isArray(result.pendingItems) ? result.pendingItems : [];
  if (!legacyItems.length) {
    return;
  }
  for (const item of legacyItems) {
    if (item.kind === "capture") {
      await addItem({
        kind: "capture",
        status: item.staged_id ? "uploaded" : "failed",
        staged_id: item.staged_id || "",
        source_url: item.source_url || "",
        media_url: item.media_url || "",
        page_title: item.page_title || "",
        platform: item.platform_guess || item.platform || "General Web",
        original_name: item.original_name || "captured_media.jpg",
        last_error: item.staged_id ? "" : "Legacy capture is missing staged id.",
        created_at: item.captured_at || undefined
      });
    } else if (item.kind === "online") {
      await addItem({
        kind: "online",
        status: "deferred",
        url: item.url || "",
        page_title: item.page_title || "",
        platform: item.platform_guess || item.platform || "General Web",
        queue_name: "normal",
        created_at: item.captured_at || undefined
      });
    }
  }
  await chrome.storage.local.remove("pendingItems");
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
  const result = await chrome.storage.local.get({ lastError: "" });
  pendingItems = await listItems();
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
    clearPreview();
    await updateBadge(0);
    return;
  }

  itemPanel.classList.remove("hidden");
  emptyPanel.classList.add("hidden");
  await updateBadge(pendingItems.length);

  const item = pendingItems[currentIndex];
  const isCapture = item.kind === "capture";
  document.getElementById("itemKind").textContent = isCapture ? "Capture" : "Online Queue";
  document.getElementById("itemTitle").textContent = item.page_title || item.original_name || item.url || "Untitled";
  document.getElementById("itemUrl").textContent = isCapture ? item.source_url || item.media_url : item.url;
  document.getElementById("itemStatus").textContent = statusText(item);
  document.getElementById("itemCounter").textContent = `${currentIndex + 1}/${pendingItems.length}`;
  document.getElementById("platformSelect").value = platformValue(item.platform);
  document.getElementById("artistInput").value = item.artist || "";
  document.getElementById("queueSelect").value = item.queue_name || "normal";
  document.getElementById("queueWrap").classList.toggle("hidden", isCapture);
  document.getElementById("prevButton").disabled = currentIndex <= 0;
  document.getElementById("nextButton").disabled = currentIndex >= pendingItems.length - 1;

  configurePrimaryButton(item);
  await loadPreview(item);
}

function statusText(item) {
  if (item.status === "cached") return "Cached locally. LMZ can be offline.";
  if (item.status === "needs_download_choice") return item.last_error || "Large image. Choose download or discard.";
  if (item.status === "downloaded") return "Downloaded to LMZ Capture. Import manually in LMZ.";
  if (item.status === "uploaded") return "Synced to LMZ staging. Ready to commit.";
  if (item.status === "deferred") return "Saved locally. Append when LMZ is online.";
  if (item.status === "failed") return item.last_error || "Capture failed.";
  if (item.status === "syncing") return "Syncing...";
  if (item.status === "committing") return "Committing to vault...";
  if (item.status === "appending") return "Appending to queue...";
  if (item.status === "downloading") return "Downloading fallback...";
  return item.status || "";
}

function configurePrimaryButton(item) {
  const button = document.getElementById("commitButton");
  button.disabled = actionInFlight;
  if (item.kind === "online") {
    button.textContent = "Append Queue";
  } else if (item.status === "cached") {
    button.textContent = "Sync to LMZ";
  } else if (item.status === "uploaded") {
    button.textContent = "Commit to Vault";
  } else if (item.status === "needs_download_choice" || item.status === "failed") {
    button.textContent = item.media_url ? "Download" : "No Download URL";
    button.disabled = !item.media_url;
  } else if (item.status === "downloaded") {
    button.textContent = "Manual Import";
    button.disabled = true;
  } else if (item.status === "syncing") {
    button.textContent = "Syncing...";
    button.disabled = true;
  } else if (item.status === "committing") {
    button.textContent = "Committing...";
    button.disabled = true;
  } else if (item.status === "appending") {
    button.textContent = "Appending...";
    button.disabled = true;
  } else if (item.status === "downloading") {
    button.textContent = "Downloading...";
    button.disabled = true;
  } else {
    button.textContent = "Wait";
    button.disabled = true;
  }
}

async function loadPreview(item) {
  clearPreview();
  const previewWrap = document.getElementById("previewWrap");
  if (item.kind !== "capture") {
    previewWrap.classList.add("hidden");
    return;
  }
  if (item.blob) {
    previewWrap.classList.remove("hidden");
    previewObjectUrl = URL.createObjectURL(item.blob);
    document.getElementById("previewImage").src = previewObjectUrl;
    return;
  }
  if (item.staged_id) {
    try {
      const res = await fetch(`${config.apiBaseUrl}/api/capture/preview/${encodeURIComponent(item.staged_id)}`, {
        headers: { "X-LMZ-API-KEY": config.apiKey }
      });
      if (!res.ok) {
        throw new Error(`Preview failed: ${res.status}`);
      }
      const blob = await res.blob();
      previewWrap.classList.remove("hidden");
      previewObjectUrl = URL.createObjectURL(blob);
      document.getElementById("previewImage").src = previewObjectUrl;
      return;
    } catch (error) {
      showError(error.message);
    }
  }
  previewWrap.classList.add("hidden");
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

async function moveCurrent(delta) {
  const next = currentIndex + delta;
  if (next < 0 || next >= pendingItems.length) {
    return;
  }
  currentIndex = next;
  await render();
}

async function discardCurrent() {
  const item = pendingItems[currentIndex];
  if (!item) return;
  if (item.kind === "capture" && item.staged_id) {
    await fetch(`${config.apiBaseUrl}/api/capture/stage/${encodeURIComponent(item.staged_id)}`, {
      method: "DELETE",
      headers: { "X-LMZ-API-KEY": config.apiKey }
    }).catch(() => {});
  }
  await deleteItem(item.id);
  document.getElementById("artistInput").value = "";
  await chrome.storage.local.set({ lastError: "" });
  await refreshState();
}

async function primaryAction() {
  if (actionInFlight) return;
  const item = pendingItems[currentIndex];
  if (!item) return;
  actionInFlight = true;
  document.getElementById("commitButton").disabled = true;
  await saveItemForm(item);
  const fresh = await getItem(item.id);
  if (!fresh) {
    actionInFlight = false;
    return;
  }
  try {
    if (fresh.kind === "online") {
      await appendOnlineQueue(fresh);
    } else if (fresh.status === "cached") {
      await syncCapture(fresh);
    } else if (fresh.status === "uploaded") {
      await commitCapture(fresh);
    } else if (fresh.status === "needs_download_choice" || fresh.status === "failed") {
      await downloadFallback(fresh);
    }
    await chrome.storage.local.set({ lastError: "" });
    await refreshState();
  } catch (error) {
    const message = error?.message || String(error);
    showError(message);
    await updateItem(fresh.id, { status: restoreStatus(fresh.status), last_error: message });
    await chrome.storage.local.set({ lastError: message });
    await refreshState();
  } finally {
    actionInFlight = false;
    await render();
  }
}

function restoreStatus(status) {
  if (status === "syncing") return "cached";
  if (status === "committing") return "uploaded";
  if (status === "appending") return "deferred";
  if (status === "downloading") return "failed";
  return status;
}

async function saveItemForm(item) {
  await updateItem(item.id, {
    artist: document.getElementById("artistInput").value.trim(),
    platform: document.getElementById("platformSelect").value,
    queue_name: document.getElementById("queueSelect").value
  });
}

async function syncCapture(item) {
  if (!item.blob) {
    throw new Error("Cached image bytes are missing.");
  }
  await updateItem(item.id, { status: "syncing", last_error: "" });
  const formData = new FormData();
  formData.append("file", item.blob, item.original_name || "captured_media.jpg");
  formData.append("source_url", item.source_url || "");
  formData.append("media_url", item.media_url || "");
  formData.append("page_title", item.page_title || "");

  const response = await fetch(`${config.apiBaseUrl}/api/capture/stage`, {
    method: "POST",
    headers: { "X-LMZ-API-KEY": config.apiKey },
    body: formData
  });
  const payload = await safeJson(response);
  if (!response.ok) {
    throw new Error(payload.detail || `Capture stage failed: ${response.status}`);
  }
  await updateItem(item.id, {
    status: "uploaded",
    staged_id: payload.staged_id,
    source_url: payload.source_url || item.source_url,
    media_url: payload.media_url || item.media_url,
    page_title: payload.page_title || item.page_title,
    platform: item.platform || payload.platform_guess || "General Web",
    original_name: payload.original_name || item.original_name,
    last_error: ""
  });
}

async function commitCapture(item) {
  await updateItem(item.id, { status: "committing", last_error: "" });
  const response = await fetch(`${config.apiBaseUrl}/api/capture/commit`, {
    method: "POST",
    headers: {
      "X-LMZ-API-KEY": config.apiKey,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      staged_id: item.staged_id,
      artist: item.artist || "Unknown",
      platform: item.platform || "General Web"
    })
  });
  const payload = await safeJson(response);
  if (!response.ok || payload.success === false) {
    throw new Error(payload.detail || payload.message || `Commit failed: ${response.status}`);
  }
  await deleteItem(item.id);
}

async function appendOnlineQueue(item) {
  await updateItem(item.id, { status: "appending", last_error: "" });
  const queue = item.queue_name || "normal";
  const response = await fetch(`${config.apiBaseUrl}/api/queue/${queue}/append`, {
    method: "POST",
    headers: {
      "X-LMZ-API-KEY": config.apiKey,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      url: item.url,
      artist: item.artist || "",
      platform: item.platform || "General Web"
    })
  });
  const payload = await safeJson(response);
  if (!response.ok || payload.success === false) {
    throw new Error(payload.detail || payload.message || `Queue append failed: ${response.status}`);
  }
  await deleteItem(item.id);
}

async function downloadFallback(item) {
  await updateItem(item.id, { status: "downloading", last_error: "" });
  const downloadId = await chrome.downloads.download({
    url: item.media_url,
    filename: downloadFilename(item),
    conflictAction: "uniquify",
    saveAs: false
  });
  await updateItem(item.id, {
    status: "downloaded",
    download_id: downloadId,
    blob: undefined,
    last_error: ""
  });
}

function downloadFilename(item) {
  const day = new Date().toISOString().slice(0, 10);
  return `LMZ Capture/${day}/${sanitizeFilename(item.original_name || "captured_media.jpg")}`;
}

function sanitizeFilename(value) {
  return String(value || "captured_media.jpg").replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").slice(0, 180);
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
