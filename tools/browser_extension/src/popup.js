import { addItem, deleteItem, getItem, listItems, updateItem } from "./db.js";
import {
  downloadFile,
  storageGet,
  storageRemove,
  storageSet,
  updateBadge
} from "./api.js";
import { iconHtml } from "./icons.js";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const METADATA_SAVE_DEBOUNCE_MS = 300;
const PLATFORM_OPTIONS = [
  "X",
  "Pixiv",
  "Pinterest",
  "YouTube",
  "Bluesky",
  "DeviantArt",
  "Reddit",
  "General Web"
];

let config = { apiBaseUrl: DEFAULT_API_BASE_URL, apiKey: "" };
let pendingItems = [];
let currentIndex = 0;
let previewObjectUrl = "";
let actionInFlight = false;
let metadataSaveTimer = null;

document.addEventListener("DOMContentLoaded", async () => {
  setupStaticIcons();
  bindEvents();
  await loadConfig();
  await migrateLegacyPendingItems();
  await refreshState();
  await checkBackend();
});

function setupStaticIcons() {
  setButtonContent("bulkToggle", "merge", "Bulk");
  setButtonContent("settingsToggle", "server", "API");
  setButtonContent("prevButton", "chevronLeft", "");
  setButtonContent("nextButton", "chevronRight", "");
  setButtonContent("discardButton", "trash", "Discard");
  setButtonContent("bulkCommitAll", "checkCircle", "Commit all cached");
  setButtonContent("bulkDiscardAll", "trash", "Discard all");
}

function setButtonContent(buttonOrId, iconName, label) {
  const button = typeof buttonOrId === "string" ? document.getElementById(buttonOrId) : buttonOrId;
  if (!button) return;
  button.innerHTML = iconHtml(iconName, label);
}

function bindEvents() {
  document.getElementById("settingsToggle").addEventListener("click", () => {
    togglePanel("settingsPanel", "bulkPanel");
  });
  document.getElementById("bulkToggle").addEventListener("click", () => {
    togglePanel("bulkPanel", "settingsPanel");
  });
  document.getElementById("saveSettings").addEventListener("click", saveConfig);
  document.getElementById("artistInput").addEventListener("input", scheduleMetadataSave);
  document.getElementById("artistInput").addEventListener("change", () => saveVisibleItem().catch(showSaveError));
  document.getElementById("platformSelect").addEventListener("change", () => saveVisibleItem().catch(showSaveError));
  document.getElementById("queueSelect").addEventListener("change", () => saveVisibleItem().catch(showSaveError));
  document.getElementById("discardButton").addEventListener("click", discardCurrent);
  document.getElementById("commitButton").addEventListener("click", primaryAction);
  document.getElementById("bulkCommitAll").addEventListener("click", commitAllCached);
  document.getElementById("bulkDiscardAll").addEventListener("click", discardAllItems);
  document.getElementById("prevButton").addEventListener("click", () => moveCurrent(-1).catch(showSaveError));
  document.getElementById("nextButton").addEventListener("click", () => moveCurrent(1).catch(showSaveError));
}

function togglePanel(openId, closeId) {
  const openPanel = document.getElementById(openId);
  const closePanel = document.getElementById(closeId);
  closePanel.classList.add("hidden");
  openPanel.classList.toggle("hidden");
  updatePanelToggles();
  resetPopupScroll();
}

function updatePanelToggles() {
  document.getElementById("settingsToggle").classList.toggle(
    "active",
    !document.getElementById("settingsPanel").classList.contains("hidden")
  );
  document.getElementById("bulkToggle").classList.toggle(
    "active",
    !document.getElementById("bulkPanel").classList.contains("hidden")
  );
}

function bulkCounts(items = pendingItems) {
  let cachedCaptures = 0;
  let uploadedCaptures = 0;
  let cachedLinks = 0;
  let skipped = 0;
  for (const item of items) {
    if (item.kind === "capture" && item.status === "cached") {
      cachedCaptures += 1;
    } else if (item.kind === "capture" && item.status === "uploaded") {
      uploadedCaptures += 1;
    } else if (item.kind === "online" && item.status === "deferred") {
      cachedLinks += 1;
    } else {
      skipped += 1;
    }
  }
  return { cachedCaptures, uploadedCaptures, cachedLinks, skipped };
}

function updateBulkPanel() {
  const counts = bulkCounts();
  const eligible = counts.cachedCaptures + counts.uploadedCaptures + counts.cachedLinks;
  document.getElementById("bulkCachedCaptures").textContent = String(counts.cachedCaptures);
  document.getElementById("bulkUploadedCaptures").textContent = String(counts.uploadedCaptures);
  document.getElementById("bulkCachedLinks").textContent = String(counts.cachedLinks);
  document.getElementById("bulkSkippedItems").textContent = String(counts.skipped);
  setButtonContent("bulkCommitAll", "checkCircle", actionInFlight ? "Working..." : `Commit all cached${eligible ? ` (${eligible})` : ""}`);
  setButtonContent("bulkDiscardAll", "trash", `Discard all${pendingItems.length ? ` (${pendingItems.length})` : ""}`);
  document.getElementById("bulkCommitAll").disabled = actionInFlight || eligible === 0;
  document.getElementById("bulkDiscardAll").disabled = actionInFlight || pendingItems.length === 0;
}

async function loadConfig() {
  const result = await storageGet(["apiBaseUrl", "apiKey"]);
  config = {
    apiBaseUrl: normalizeApiBaseUrl(result.apiBaseUrl || DEFAULT_API_BASE_URL),
    apiKey: result.apiKey || ""
  };
  document.getElementById("apiBaseUrl").value = config.apiBaseUrl;
  document.getElementById("apiKey").value = config.apiKey;
}

async function migrateLegacyPendingItems() {
  const result = await storageGet({ pendingItems: [] });
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
  await storageRemove("pendingItems");
}

async function saveConfig() {
  config = {
    apiBaseUrl: normalizeApiBaseUrl(document.getElementById("apiBaseUrl").value),
    apiKey: document.getElementById("apiKey").value.trim()
  };
  await storageSet(config);
  document.getElementById("settingsPanel").classList.add("hidden");
  updatePanelToggles();
  await checkBackend();
  await render();
  resetPopupScroll();
}

function normalizeApiBaseUrl(value) {
  return String(value || DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}

async function refreshState() {
  const result = await storageGet({ lastError: "" });
  pendingItems = await listItems();
  if (currentIndex >= pendingItems.length) {
    currentIndex = Math.max(0, pendingItems.length - 1);
  }
  showError(result.lastError || "");
  await render();
  resetPopupScroll();
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
  updateBulkPanel();
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
  document.getElementById("itemKind").innerHTML = iconHtml(isCapture ? "image" : "externalLink", isCapture ? "Capture" : "Online Queue");
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
    setPrimaryButton(button, "plus", "Append", "Append Queue");
  } else if (item.status === "cached") {
    setPrimaryButton(button, "upload", "Sync", "Sync to LMZ");
  } else if (item.status === "uploaded") {
    setPrimaryButton(button, "checkCircle", "Commit", "Commit to Vault");
  } else if (item.status === "needs_download_choice" || item.status === "failed") {
    setPrimaryButton(button, item.media_url ? "download" : "externalLink", item.media_url ? "Download" : "No URL", item.media_url ? "Download fallback" : "No Download URL");
    button.disabled = !item.media_url;
  } else if (item.status === "downloaded") {
    setPrimaryButton(button, "download", "Manual", "Manual Import");
    button.disabled = true;
  } else if (item.status === "syncing") {
    setPrimaryButton(button, "upload", "Syncing");
    button.disabled = true;
  } else if (item.status === "committing") {
    setPrimaryButton(button, "checkCircle", "Committing");
    button.disabled = true;
  } else if (item.status === "appending") {
    setPrimaryButton(button, "plus", "Appending");
    button.disabled = true;
  } else if (item.status === "downloading") {
    setPrimaryButton(button, "download", "Downloading");
    button.disabled = true;
  } else {
    setPrimaryButton(button, "externalLink", "Wait");
    button.disabled = true;
  }
}

function setPrimaryButton(button, iconName, label, title = label) {
  setButtonContent(button, iconName, label);
  button.title = title;
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
  return PLATFORM_OPTIONS.includes(value) ? value : "General Web";
}

async function moveCurrent(delta) {
  const next = currentIndex + delta;
  if (next < 0 || next >= pendingItems.length) {
    return;
  }
  await saveVisibleItem();
  currentIndex = next;
  await render();
  resetPopupScroll();
}

function resetPopupScroll() {
  const scroll = document.getElementById("popupScroll");
  if (scroll) {
    scroll.scrollTop = 0;
  }
}

async function discardCurrent() {
  clearMetadataSaveTimer();
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
  await storageSet({ lastError: "" });
  await refreshState();
}

function isBulkCommitEligible(item) {
  return (
    (item.kind === "capture" && (item.status === "cached" || item.status === "uploaded"))
    || (item.kind === "online" && item.status === "deferred")
  );
}

async function commitAllCached() {
  if (actionInFlight) return;
  clearMetadataSaveTimer();
  await saveVisibleItem();
  actionInFlight = true;
  await render();
  let completed = 0;
  let failed = 0;
  let skipped = 0;
  try {
    const items = await listItems();
    for (const item of items) {
      if (!isBulkCommitEligible(item)) {
        skipped += 1;
        continue;
      }
      try {
        if (item.kind === "online") {
          await appendOnlineQueue(item);
        } else if (item.status === "cached") {
          await syncCapture(item);
          const uploaded = await getItem(item.id);
          if (!uploaded) {
            completed += 1;
            continue;
          }
          await commitCapture(uploaded);
        } else if (item.status === "uploaded") {
          await commitCapture(item);
        }
        completed += 1;
      } catch (error) {
        failed += 1;
        const latest = await getItem(item.id);
        if (latest) {
          await updateItem(latest.id, {
            status: restoreStatus(latest.status),
            last_error: error?.message || String(error)
          });
        }
      }
    }
    const summary = `Bulk finished: ${completed} done, ${failed} failed, ${skipped} skipped.`;
    await storageSet({ lastError: summary });
    showError(summary);
  } finally {
    actionInFlight = false;
    await refreshState();
  }
}

async function discardAllItems() {
  if (actionInFlight) return;
  if (!pendingItems.length) return;
  const ok = globalThis.confirm("Discard all cached LMZ extension items? Downloaded files will not be deleted.");
  if (!ok) return;
  clearMetadataSaveTimer();
  actionInFlight = true;
  await render();
  let discarded = 0;
  try {
    const items = await listItems();
    for (const item of items) {
      if (item.kind === "capture" && item.staged_id) {
        await fetch(`${config.apiBaseUrl}/api/capture/stage/${encodeURIComponent(item.staged_id)}`, {
          method: "DELETE",
          headers: { "X-LMZ-API-KEY": config.apiKey }
        }).catch(() => {});
      }
      await deleteItem(item.id);
      discarded += 1;
    }
    const summary = `Discarded ${discarded} item${discarded === 1 ? "" : "s"}.`;
    await storageSet({ lastError: summary });
    showError(summary);
  } finally {
    actionInFlight = false;
    await refreshState();
  }
}

async function primaryAction() {
  if (actionInFlight) return;
  const item = pendingItems[currentIndex];
  if (!item) return;
  actionInFlight = true;
  document.getElementById("commitButton").disabled = true;
  let fresh = null;
  try {
    await saveVisibleItem();
    fresh = await getItem(item.id);
    if (!fresh) {
      return;
    }
    if (fresh.kind === "online") {
      await appendOnlineQueue(fresh);
    } else if (fresh.status === "cached") {
      await syncCapture(fresh);
    } else if (fresh.status === "uploaded") {
      await commitCapture(fresh);
    } else if (fresh.status === "needs_download_choice" || fresh.status === "failed") {
      await downloadFallback(fresh);
    }
    await storageSet({ lastError: "" });
    await refreshState();
  } catch (error) {
    const message = error?.message || String(error);
    showError(message);
    if (fresh) {
      await updateItem(fresh.id, { status: restoreStatus(fresh.status), last_error: message });
    }
    await storageSet({ lastError: message });
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
  return updateItem(item.id, currentMetadataPatch());
}

async function saveVisibleItem() {
  clearMetadataSaveTimer();
  const item = pendingItems[currentIndex];
  if (!item) return null;
  const updated = await saveItemForm(item);
  if (updated) {
    pendingItems[currentIndex] = updated;
  }
  return updated;
}

function scheduleMetadataSave() {
  clearMetadataSaveTimer();
  const item = pendingItems[currentIndex];
  if (!item) return;
  const itemId = item.id;
  const patch = currentMetadataPatch();
  metadataSaveTimer = setTimeout(async () => {
    metadataSaveTimer = null;
    try {
      const updated = await updateItem(itemId, patch);
      if (updated && pendingItems[currentIndex]?.id === itemId) {
        pendingItems[currentIndex] = updated;
      }
    } catch (error) {
      showSaveError(error);
    }
  }, METADATA_SAVE_DEBOUNCE_MS);
}

function clearMetadataSaveTimer() {
  if (metadataSaveTimer) {
    clearTimeout(metadataSaveTimer);
    metadataSaveTimer = null;
  }
}

function currentMetadataPatch() {
  return {
    artist: document.getElementById("artistInput").value.trim(),
    platform: currentPlatformValue(),
    queue_name: document.getElementById("queueSelect").value
  };
}

function currentPlatformValue() {
  return document.getElementById("platformSelect").value || "General Web";
}

function showSaveError(error) {
  showError(`Metadata save failed: ${error?.message || String(error)}`);
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
  const downloadId = await downloadFile({
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
