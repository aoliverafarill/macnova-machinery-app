/**
 * Macnova Fleet — Service Worker
 * Provides:
 *   1. App shell caching (offline form access)
 *   2. Background Sync: sends queued reports when connectivity returns
 */

const CACHE_NAME = "macnova-v1";

// Files to cache for offline access
const APP_SHELL = [
  "/static/fleet/js/offline_queue.js",
  "https://cdn.jsdelivr.net/npm/signature_pad@4.1.7/dist/signature_pad.umd.min.js",
];

// ── Install: pre-cache static assets ───────────────────────────────────────
self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

// ── Activate: clean old caches ─────────────────────────────────────────────
self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ── Fetch: network-first for API, cache-first for static assets ────────────
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);

  // Always go network for POST / API calls
  if (event.request.method !== "GET") return;

  // For the form page (QR link) — network first, fallback to cache
  if (url.pathname.startsWith("/m/") && !url.pathname.endsWith("/submit/")) {
    event.respondWith(
      fetch(event.request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Static files — cache first
  if (url.pathname.startsWith("/static/") || url.hostname.includes("jsdelivr")) {
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
    return;
  }
});

// ── Background Sync: send queued offline reports ───────────────────────────
self.addEventListener("sync", event => {
  if (event.tag === "report-sync") {
    event.waitUntil(syncPendingReports());
  }
});

async function syncPendingReports() {
  // We need to open IndexedDB from inside the service worker
  const db = await openIDB();
  const records = await getUnsynced(db);

  for (const record of records) {
    const submitUrl = `/m/${record.machine_qr}/submit/`;
    try {
      const res = await fetch(submitUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(record.payload),
      });
      if (res.ok) {
        await markSynced(db, record.id);
        // Notify any open windows
        const clients = await self.clients.matchAll();
        clients.forEach(c => c.postMessage({ type: "REPORT_SYNCED", id: record.id }));
      }
    } catch (e) {
      // Network still unavailable — will retry on next sync event
      console.warn("[SW] Could not sync report", record.id, e);
    }
  }
}

// ── Minimal IndexedDB helpers (service worker context) ────────────────────
function openIDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("macnova_offline", 1);
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains("pending_reports")) {
        const store = db.createObjectStore("pending_reports", { keyPath: "id", autoIncrement: true });
        store.createIndex("synced", "synced", { unique: false });
      }
    };
  });
}

function getUnsynced(db) {
  return new Promise((resolve, reject) => {
    const tx    = db.transaction("pending_reports", "readonly");
    const store = tx.objectStore("pending_reports");
    const idx   = store.index("synced");
    const req   = idx.getAll(IDBKeyRange.only(false));
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}

function markSynced(db, id) {
  return new Promise((resolve, reject) => {
    const tx    = db.transaction("pending_reports", "readwrite");
    const store = tx.objectStore("pending_reports");
    const req   = store.get(id);
    req.onsuccess = e => {
      const record = e.target.result;
      if (!record) { resolve(); return; }
      record.synced = true;
      const put = store.put(record);
      put.onsuccess = () => resolve();
      put.onerror   = e2 => reject(e2.target.error);
    };
    req.onerror = e => reject(e.target.error);
  });
}
