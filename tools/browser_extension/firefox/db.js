const DB_NAME = "lmz_capture";
const DB_VERSION = 1;
const ITEM_STORE = "items";

export const MAX_AUTO_CACHE_BYTES = 100 * 1024 * 1024;

export function newItemId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function addItem(item) {
  const now = new Date().toISOString();
  const record = {
    ...item,
    id: item.id || newItemId(),
    created_at: item.created_at || now,
    updated_at: now
  };
  const db = await openDb();
  const tx = db.transaction(ITEM_STORE, "readwrite");
  const done = transactionDone(tx);
  await requestToPromise(tx.objectStore(ITEM_STORE).put(record));
  await done;
  return record;
}

export async function updateItem(id, patch) {
  const current = await getItem(id);
  if (!current) {
    return null;
  }
  const next = {
    ...current,
    ...patch,
    id,
    updated_at: new Date().toISOString()
  };
  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined) {
      delete next[key];
    }
  }
  const db = await openDb();
  const tx = db.transaction(ITEM_STORE, "readwrite");
  const done = transactionDone(tx);
  const store = tx.objectStore(ITEM_STORE);
  await requestToPromise(store.put(next));
  await done;
  return next;
}

export async function deleteItem(id) {
  const db = await openDb();
  const tx = db.transaction(ITEM_STORE, "readwrite");
  const done = transactionDone(tx);
  await requestToPromise(tx.objectStore(ITEM_STORE).delete(id));
  await done;
}

export async function getItem(id) {
  const db = await openDb();
  return requestToPromise(db.transaction(ITEM_STORE, "readonly").objectStore(ITEM_STORE).get(id));
}

export async function listItems() {
  const db = await openDb();
  const items = await requestToPromise(db.transaction(ITEM_STORE, "readonly").objectStore(ITEM_STORE).getAll());
  return items.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
}

export async function countItems() {
  const db = await openDb();
  return requestToPromise(db.transaction(ITEM_STORE, "readonly").objectStore(ITEM_STORE).count());
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(ITEM_STORE)) {
        const store = db.createObjectStore(ITEM_STORE, { keyPath: "id" });
        store.createIndex("created_at", "created_at", { unique: false });
        store.createIndex("status", "status", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function requestToPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transactionDone(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}
