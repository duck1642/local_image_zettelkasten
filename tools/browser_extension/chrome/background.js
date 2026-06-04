const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "lmz_capture_image",
    title: "Capture image to LMZ",
    contexts: ["image"]
  });
  chrome.contextMenus.create({
    id: "lmz_queue_page",
    title: "Send page to LMZ online queue",
    contexts: ["page"]
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "lmz_capture_image") {
    stageImageCapture(info, tab).catch((error) => recordError(error));
  } else if (info.menuItemId === "lmz_queue_page") {
    stageOnlineQueue(info, tab).catch((error) => recordError(error));
  }
});

async function getConfig() {
  const result = await chrome.storage.local.get(["apiBaseUrl", "apiKey"]);
  return {
    apiBaseUrl: normalizeApiBaseUrl(result.apiBaseUrl || DEFAULT_API_BASE_URL),
    apiKey: result.apiKey || ""
  };
}

function normalizeApiBaseUrl(value) {
  return String(value || DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}

async function stageImageCapture(info, tab) {
  const mediaUrl = info.srcUrl || "";
  const sourceUrl = info.pageUrl || tab?.url || "";
  if (!mediaUrl) {
    throw new Error("No image URL was available from the page.");
  }

  const config = await getConfig();
  const response = await fetch(mediaUrl, { credentials: "include" });
  if (!response.ok) {
    throw new Error(`Image fetch failed: ${response.status}`);
  }

  const blob = await response.blob();
  const filename = filenameFromUrl(mediaUrl, blob.type);
  const formData = new FormData();
  formData.append("file", blob, filename);
  formData.append("source_url", sourceUrl);
  formData.append("media_url", mediaUrl);
  formData.append("page_title", tab?.title || "");

  const stageResponse = await fetch(`${config.apiBaseUrl}/api/capture/stage`, {
    method: "POST",
    headers: { "X-LMZ-API-KEY": config.apiKey },
    body: formData
  });
  if (!stageResponse.ok) {
    const payload = await safeJson(stageResponse);
    throw new Error(payload.detail || `Capture stage failed: ${stageResponse.status}`);
  }

  const payload = await stageResponse.json();
  await pushPendingItem({
    kind: "capture",
    staged_id: payload.staged_id,
    source_url: payload.source_url || sourceUrl,
    media_url: payload.media_url || mediaUrl,
    page_title: payload.page_title || tab?.title || "",
    platform_guess: payload.platform_guess || "General Web",
    original_name: payload.original_name || filename,
    captured_at: new Date().toISOString()
  });
}

async function stageOnlineQueue(info, tab) {
  const pageUrl = info.pageUrl || tab?.url || "";
  if (!pageUrl) {
    throw new Error("No page URL was available.");
  }
  await pushPendingItem({
    kind: "online",
    url: pageUrl,
    page_title: tab?.title || "",
    platform_guess: guessPlatform(pageUrl),
    captured_at: new Date().toISOString()
  });
}

async function pushPendingItem(item) {
  const result = await chrome.storage.local.get({ pendingItems: [] });
  const pendingItems = Array.isArray(result.pendingItems) ? result.pendingItems : [];
  pendingItems.push(item);
  await chrome.storage.local.set({ pendingItems, lastError: "" });
  await updateBadge(pendingItems.length);
}

async function recordError(error) {
  const message = error?.message || String(error);
  await chrome.storage.local.set({ lastError: message });
  chrome.action.setBadgeText({ text: "!" });
  chrome.action.setBadgeBackgroundColor({ color: "#c2410c" });
}

async function updateBadge(count) {
  chrome.action.setBadgeText({ text: count > 0 ? String(count) : "" });
  chrome.action.setBadgeBackgroundColor({ color: "#1f6feb" });
}

function filenameFromUrl(url, mimeType) {
  try {
    const parsed = new URL(url);
    const name = decodeURIComponent(parsed.pathname.split("/").filter(Boolean).pop() || "");
    if (/\.[a-z0-9]{2,5}$/i.test(name)) {
      return name;
    }
  } catch {
    // Fall through to MIME fallback.
  }
  const ext = extensionFromMime(mimeType);
  return `captured_media${ext}`;
}

function extensionFromMime(mimeType) {
  const mime = String(mimeType || "").toLowerCase();
  if (mime.includes("png")) return ".png";
  if (mime.includes("webp")) return ".webp";
  if (mime.includes("gif")) return ".gif";
  if (mime.includes("jpeg") || mime.includes("jpg")) return ".jpg";
  return ".jpg";
}

function guessPlatform(url) {
  const lower = String(url || "").toLowerCase();
  if (lower.includes("pixiv.net")) return "Pixiv";
  if (lower.includes("twitter.com") || lower.includes("x.com")) return "X";
  if (lower.includes("instagram.com")) return "Instagram";
  if (lower.includes("pinterest.") || lower.includes("pin.it")) return "Pinterest";
  return "General Web";
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}
