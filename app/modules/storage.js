const DATABASE = "scientific-slides-recovery";
const STORE = "snapshots";
const MAX_SNAPSHOTS = 20;

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      const store = database.createObjectStore(STORE, { keyPath: "key" });
      store.createIndex("deck", "deck", { unique: false });
      store.createIndex("timestamp", "timestamp", { unique: false });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transaction(database, mode, operation) {
  return new Promise((resolve, reject) => {
    const tx = database.transaction(STORE, mode);
    const store = tx.objectStore(STORE);
    let result;
    try { result = operation(store); } catch (error) { reject(error); return; }
    tx.oncomplete = () => resolve(result);
    tx.onerror = () => reject(tx.error);
  });
}

export async function saveSnapshot(deck, source) {
  if (!source?.trim()) return;
  const database = await openDatabase();
  const timestamp = Date.now();
  await transaction(database, "readwrite", store => store.put({
    key: `${deck}:${timestamp}`,
    deck,
    timestamp,
    source,
  }));
  const snapshots = await listSnapshots(deck);
  for (const snapshot of snapshots.slice(MAX_SNAPSHOTS)) {
    await transaction(database, "readwrite", store => store.delete(snapshot.key));
  }
  database.close();
}

export async function listSnapshots(deck) {
  const database = await openDatabase();
  const values = await new Promise((resolve, reject) => {
    const tx = database.transaction(STORE, "readonly");
    const index = tx.objectStore(STORE).index("deck");
    const request = index.getAll(IDBKeyRange.only(deck));
    request.onsuccess = () => resolve(request.result.sort((a, b) => b.timestamp - a.timestamp));
    request.onerror = () => reject(request.error);
  });
  database.close();
  return values;
}
