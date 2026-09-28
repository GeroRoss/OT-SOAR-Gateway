const STORAGE_KEY = "ot-soar-read-alerts";

export function alertReadKey(event) {
  // Demo reset reuses database IDs. The timestamp distinguishes the new event.
  return JSON.stringify([event.event_key, event.timestamp]);
}

export function loadReadAlerts(storage) {
  try {
    const keys = JSON.parse(
      (storage ?? globalThis.localStorage).getItem(STORAGE_KEY) || "[]",
    );
    return new Set(
      Array.isArray(keys) ? keys.filter((key) => typeof key === "string") : [],
    );
  } catch {
    return new Set();
  }
}

export function saveReadAlerts(keys, storage) {
  const bounded = Array.from(keys).slice(-500);
  try {
    (storage ?? globalThis.localStorage).setItem(STORAGE_KEY, JSON.stringify(bounded));
  } catch {
    // Read state still works for this session if browser storage is unavailable.
  }
  return new Set(bounded);
}
