import { MAX_AUTO_CACHE_BYTES, addItem, countItems } from "./db.js";
import {
  createContextMenu,
  ext,
  removeAllContextMenus,
  setBadgeBackgroundColor,
  setBadgeText,
  storageSet
} from "./api.js";

ext.runtime.onInstalled.addListener(() => {
  removeAllContextMenus().then(() => {
    createContextMenu({
      id: "lmz_capture_image",
      title: "Capture image to LMZ",
      contexts: ["image"]
    });
    createContextMenu({
      id: "lmz_queue_page",
      title: "Send page to LMZ online queue",
      contexts: ["page", "image"]
    });
  }).catch((error) => recordError(error));
  updateBadgeFromDb().catch(() => {});
});

ext.runtime.onStartup.addListener(() => {
  updateBadgeFromDb().catch(() => {});
});

ext.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "lmz_capture_image") {
    cacheImageCapture(info, tab).catch((error) => recordError(error));
  } else if (info.menuItemId === "lmz_queue_page") {
    cacheOnlineQueue(info, tab).catch((error) => recordError(error));
  }
});

async function cacheImageCapture(info, tab) {
  const mediaUrl = info.srcUrl || "";
  const sourceUrl = info.pageUrl || tab?.url || "";
  const pageTitle = tab?.title || "";
  if (!mediaUrl) {
    throw new Error("No image URL was available from the page.");
  }

  try {
    const response = await fetch(mediaUrl, { credentials: "include" });
    if (!response.ok) {
      throw new Error(`Image fetch failed: ${response.status}`);
    }

    const blob = await response.blob();
    const filename = filenameFromUrl(mediaUrl, blob.type);
    const base = captureRecord({
      sourceUrl,
      mediaUrl,
      pageTitle,
      filename,
      platform: guessPlatform(sourceUrl || mediaUrl),
      size: blob.size,
      mimeType: blob.type
    });

    if (blob.size > MAX_AUTO_CACHE_BYTES) {
      await addItem({
        ...base,
        status: "needs_download_choice",
        last_error: `Image is larger than ${formatBytes(MAX_AUTO_CACHE_BYTES)}.`
      });
    } else {
      await addItem({
        ...base,
        status: "cached",
        blob
      });
    }
  } catch (error) {
    await addItem({
      ...captureRecord({
        sourceUrl,
        mediaUrl,
        pageTitle,
        filename: filenameFromUrl(mediaUrl, ""),
        platform: guessPlatform(sourceUrl || mediaUrl)
      }),
      status: "failed",
      last_error: error?.message || String(error)
    });
  }

  await updateBadgeFromDb();
}

async function cacheOnlineQueue(info, tab) {
  const pageUrl = info.pageUrl || tab?.url || "";
  if (!pageUrl) {
    throw new Error("No page URL was available.");
  }
  await addItem({
    kind: "online",
    status: "deferred",
    url: pageUrl,
    page_title: tab?.title || "",
    platform: guessPlatform(pageUrl),
    queue_name: "normal"
  });
  await updateBadgeFromDb();
}

function captureRecord({ sourceUrl, mediaUrl, pageTitle, filename, platform, size, mimeType }) {
  return {
    kind: "capture",
    source_url: sourceUrl,
    media_url: mediaUrl,
    page_title: pageTitle,
    platform,
    original_name: filename,
    size: size || 0,
    mime_type: mimeType || ""
  };
}

async function recordError(error) {
  const message = error?.message || String(error);
  await storageSet({ lastError: message });
  await setBadgeText({ text: "!" });
  await setBadgeBackgroundColor({ color: "#c2410c" });
}

async function updateBadgeFromDb() {
  const count = await countItems();
  await setBadgeText({ text: count > 0 ? String(count) : "" });
  await setBadgeBackgroundColor({ color: "#1f6feb" });
}

function filenameFromUrl(url, mimeType) {
  try {
    const parsed = new URL(url);
    const name = decodeURIComponent(parsed.pathname.split("/").filter(Boolean).pop() || "");
    if (/\.[a-z0-9]{2,5}$/i.test(name)) {
      return sanitizeFilename(name);
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

function sanitizeFilename(value) {
  return String(value || "captured_media.jpg").replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").slice(0, 180);
}

function guessPlatform(url) {
  const lower = String(url || "").toLowerCase();
  if (lower.includes("pixiv.net")) return "Pixiv";
  if (lower.includes("twitter.com") || lower.includes("x.com")) return "X";
  if (lower.includes("instagram.com")) return "Instagram";
  if (lower.includes("pinterest.") || lower.includes("pin.it")) return "Pinterest";
  return "General Web";
}

function formatBytes(bytes) {
  return `${Math.round(bytes / 1024 / 1024)} MB`;
}
