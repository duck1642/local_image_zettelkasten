const rawApi = globalThis.browser || globalThis.chrome;
const chromeApi = globalThis.chrome;
const usesBrowserPromises = !!globalThis.browser;

if (!rawApi) {
  throw new Error("Browser extension API is unavailable.");
}

export const ext = rawApi;

function callWithCallback(target, method, args) {
  return new Promise((resolve, reject) => {
    target[method](...args, (result) => {
      const error = chromeApi?.runtime?.lastError;
      if (error) {
        reject(new Error(error.message));
        return;
      }
      resolve(result);
    });
  });
}

function callApi(target, method, ...args) {
  if (usesBrowserPromises) {
    const result = target[method](...args);
    return result && typeof result.then === "function" ? result : Promise.resolve(result);
  }
  return callWithCallback(target, method, args);
}

export function storageGet(keys) {
  return callApi(rawApi.storage.local, "get", keys);
}

export function storageSet(values) {
  return callApi(rawApi.storage.local, "set", values);
}

export function storageRemove(keys) {
  return callApi(rawApi.storage.local, "remove", keys);
}

export function removeAllContextMenus() {
  return callApi(rawApi.contextMenus, "removeAll");
}

export function createContextMenu(details) {
  rawApi.contextMenus.create(details);
}

export function setBadgeText(details) {
  return callApi(rawApi.action, "setBadgeText", details);
}

export function setBadgeBackgroundColor(details) {
  return callApi(rawApi.action, "setBadgeBackgroundColor", details);
}

export function downloadFile(details) {
  return callApi(rawApi.downloads, "download", details);
}
