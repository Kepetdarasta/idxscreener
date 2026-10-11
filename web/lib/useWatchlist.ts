"use client";
import { useCallback, useEffect, useState } from "react";

const KEY = "watchlist:v1";

function read(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

/** Watchlist disimpan di browser (localStorage): tanpa login, tidak sinkron antar perangkat. */
export function useWatchlist() {
  const [list, setList] = useState<string[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setList(read());
    setReady(true);
    const on = (e: StorageEvent) => { if (e.key === KEY) setList(read()); };
    window.addEventListener("storage", on);
    return () => window.removeEventListener("storage", on);
  }, []);

  const toggle = useCallback((code: string) => {
    setList((prev) => {
      const next = prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code];
      try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* storage penuh/diblokir */ }
      return next;
    });
  }, []);

  return { list, ready, has: (c: string) => list.includes(c), toggle };
}
