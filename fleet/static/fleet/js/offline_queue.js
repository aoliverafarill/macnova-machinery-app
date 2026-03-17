/**
 * OfflineQueue — IndexedDB persistence layer for offline report submission.
 * Stores reports (including base64 photos) locally so they survive page closes
 * and are sent to the server when internet is restored.
 *
 * Usage:
 *   await OfflineQueue.saveReport(machineQr, payload)  → returns localId
 *   await OfflineQueue.markSynced(localId)
 *   await OfflineQueue.getSyncQueue()                  → [{id, machine_qr, payload}, ...]
 *   await OfflineQueue.getPendingCount()               → number
 */

const OfflineQueue = (() => {
  const DB_NAME    = "macnova_offline";
  const DB_VERSION = 1;
  const STORE      = "pending_reports";

  let _db = null;

  function openDB() {
    if (_db) return Promise.resolve(_db);
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);

      req.onupgradeneeded = e => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
          store.createIndex("synced",      "synced",      { unique: false });
          store.createIndex("machine_qr",  "machine_qr",  { unique: false });
          store.createIndex("created_at",  "created_at",  { unique: false });
        }
      };

      req.onsuccess = e => { _db = e.target.result; resolve(_db); };
      req.onerror   = e => reject(e.target.error);
    });
  }

  function tx(mode) {
    return openDB().then(db => {
      const t = db.transaction(STORE, mode);
      const s = t.objectStore(STORE);
      return { t, s };
    });
  }

  function req2promise(r) {
    return new Promise((res, rej) => {
      r.onsuccess = e => res(e.target.result);
      r.onerror   = e => rej(e.target.error);
    });
  }

  /**
   * Save a report to IndexedDB.
   * @param {string} machineQr
   * @param {object} payload — the full JSON body to be POSTed to the server
   * @returns {Promise<number>} the auto-assigned local ID
   */
  async function saveReport(machineQr, payload) {
    const { s } = await tx("readwrite");
    const record = {
      machine_qr:  machineQr,
      payload:     payload,
      created_at:  new Date().toISOString(),
      synced:      false,
    };
    return req2promise(s.add(record));
  }

  /**
   * Mark a local record as synced (after successful server response).
   * @param {number} localId
   */
  async function markSynced(localId) {
    const { s } = await tx("readwrite");
    const record = await req2promise(s.get(localId));
    if (record) {
      record.synced = true;
      await req2promise(s.put(record));
    }
  }

  /**
   * Return all unsynced records ready to be sent.
   * @returns {Promise<Array>}
   */
  async function getSyncQueue() {
    const { s } = await tx("readonly");
    const idx = s.index("synced");
    return req2promise(idx.getAll(IDBKeyRange.only(false)));
  }

  /**
   * Count of unsynced reports.
   * @returns {Promise<number>}
   */
  async function getPendingCount() {
    const { s } = await tx("readonly");
    const idx = s.index("synced");
    return req2promise(idx.count(IDBKeyRange.only(false)));
  }

  return { saveReport, markSynced, getSyncQueue, getPendingCount };
})();
