// Run with: node --test evaluation/test_dashboard_alerts.mjs
import assert from "node:assert/strict";
import test from "node:test";
import {
  alertReadKey,
  loadReadAlerts,
  saveReadAlerts,
} from "../dashboard/src/utils/alerts.js";

function memoryStorage(initial = null) {
  let value = initial;
  return {
    getItem: () => value,
    setItem: (_key, next) => {
      value = next;
    },
  };
}

const event = {
  event_key: "security:1",
  timestamp: "2026-09-22T08:00:00.000001+00:00",
};

test("a reused ID after demo reset is unread", () => {
  const read = new Set([alertReadKey(event)]);
  const afterReset = { ...event, timestamp: "2026-09-22T08:01:00.000001+00:00" };
  assert.equal(read.has(alertReadKey(afterReset)), false);
});

test("polling the same event preserves read state", () => {
  const storage = memoryStorage();
  saveReadAlerts(new Set([alertReadKey(event)]), storage);
  assert.equal(loadReadAlerts(storage).has(alertReadKey({ ...event })), true);
});

test("IDs from different event sources remain distinct", () => {
  assert.notEqual(
    alertReadKey(event),
    alertReadKey({ ...event, event_key: "response:1" }),
  );
});

test("old ID-only read entries do not hide new events", () => {
  const read = loadReadAlerts(memoryStorage('["security:1"]'));
  assert.equal(read.has(alertReadKey(event)), false);
});

test("invalid stored values do not break alert loading", () => {
  for (const value of ["broken json", "null", "{}", "42"]) {
    assert.deepEqual(loadReadAlerts(memoryStorage(value)), new Set());
  }
  assert.deepEqual(
    loadReadAlerts(memoryStorage('[null, 4, "saved"]')),
    new Set(["saved"]),
  );
});

test("only the latest 500 read entries are retained", () => {
  const storage = memoryStorage();
  const keys = new Set(Array.from({ length: 501 }, (_, i) => `event-${i}`));
  const saved = saveReadAlerts(keys, storage);
  assert.equal(saved.size, 500);
  assert.equal(saved.has("event-0"), false);
  assert.equal(saved.has("event-500"), true);
  assert.deepEqual(loadReadAlerts(storage), saved);
});

test("demo reset can clear both saved and in-memory read state", () => {
  const storage = memoryStorage();
  saveReadAlerts(new Set([alertReadKey(event)]), storage);
  assert.deepEqual(saveReadAlerts(new Set(), storage), new Set());
  assert.deepEqual(loadReadAlerts(storage), new Set());
});

test("storage failures leave session read state usable", () => {
  const storage = {
    getItem() {
      throw new Error("Storage blocked");
    },
    setItem() {
      throw new Error("Quota exceeded");
    },
  };
  assert.deepEqual(loadReadAlerts(storage), new Set());
  const read = new Set([alertReadKey(event)]);
  assert.deepEqual(saveReadAlerts(read, storage), read);
});
