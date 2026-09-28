/** Table sorting, including rankings for states and priority labels. */

import { useMemo, useState } from "react";

export const TABLE_RANKINGS = {
  criticality: {
    safety_critical: 0,
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
  },
  security: {
    quarantined: 0,
    suspicious: 1,
    normal: 2,
  },
  security_state: {
    quarantined: 0,
    suspicious: 1,
    normal: 2,
  },
  state: {
    quarantined: 0,
    suspicious: 1,
    normal: 2,
  },
  operational: {
    "offline / off": 0,
    offline: 0,
    unknown: 1,
    "online / on": 2,
    online: 2,
  },
  enabled: {
    enabled: 0,
    true: 0,
    disabled: 1,
    false: 1,
  },
  active: {
    active: 0,
    true: 0,
    inactive: 1,
    false: 1,
  },
  effect: {
    deny: 0,
    allow: 1,
  },
};

function compareValues(a, b, { ranking, numeric = false, date = false } = {}) {
  if (ranking) {
    const aKey = String(a ?? "").toLowerCase();
    const bKey = String(b ?? "").toLowerCase();
    const aRank = ranking[aKey];
    const bRank = ranking[bKey];

    if (aRank !== undefined || bRank !== undefined) {
      if (aRank === undefined) return 1;
      if (bRank === undefined) return -1;
      if (aRank !== bRank) return aRank - bRank;
    }
  }

  if (numeric) {
    const aNumber = Number(a);
    const bNumber = Number(b);
    if (Number.isFinite(aNumber) && Number.isFinite(bNumber)) {
      return aNumber - bNumber;
    }
  }

  if (date) {
    const aTime = new Date(a).getTime();
    const bTime = new Date(b).getTime();
    if (Number.isFinite(aTime) && Number.isFinite(bTime)) {
      return aTime - bTime;
    }
  }

  return String(a ?? "").localeCompare(String(b ?? ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

export function useTableSort(
  rows,
  {
    defaultKey,
    defaultDirection = "asc",
    valueGetters = {},
    rankings = {},
    numericKeys = [],
    dateKeys = [],
  },
) {
  const [sort, setSort] = useState({
    key: defaultKey,
    direction: defaultDirection,
  });

  function requestSort(key) {
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: "asc" },
    );
  }

  const sortedRows = useMemo(() => {
    const getterFor = (key) => valueGetters[key] || ((row) => row?.[key]);
    const getter = getterFor(sort.key);
    const ranking = rankings[sort.key] || TABLE_RANKINGS[sort.key];

    return [...rows].sort((a, b) => {
      const result = compareValues(getter(a), getter(b), {
        ranking,
        numeric: numericKeys.includes(sort.key),
        date: dateKeys.includes(sort.key),
      });
      return sort.direction === "asc" ? result : -result;
    });
  }, [rows, sort, valueGetters, rankings, numericKeys, dateKeys]);

  return { sortedRows, sort, requestSort };
}

export function SortHead({ field, sort, onSort, children }) {
  const active = sort.key === field;
  const arrow = active ? (sort.direction === "asc" ? " ▲" : " ▼") : "";

  return (
    <button
      type="button"
      className="sort-button"
      onClick={() => onSort(field)}
      aria-sort={
        active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"
      }
    >
      {children}
      {arrow}
    </button>
  );
}
