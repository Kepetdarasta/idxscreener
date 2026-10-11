import type { CheckItem, Levels } from "./types";

export type Bar = { d: string; h: number; l: number; c: number; v: number };
export type Series = { d: string; c: number };

// Ambang checklist — ubah di sini bila ingin lebih ketat/longgar.
export const BASE_MIN_DAYS = 30;     // basis konsolidasi minimal (hari bursa)
export const BASE_MAX_RANGE = 0.2;   // lebar range basis maksimal (20%)
export const RR_TARGET = 2;          // risk:reward yang dianggap memadai

const idr = (n: number) => Math.round(n).toLocaleString("id-ID");
const compact = (n: number) => new Intl.NumberFormat("id-ID", { notation: "compact" }).format(n);
const sgn = (n: number) => `${n > 0 ? "+" : ""}${(n * 100).toFixed(1)}%`;
const min = (a: number[]) => Math.min(...a);
const max = (a: number[]) => Math.max(...a);
const mean = (a: number[]) => a.reduce((s, x) => s + x, 0) / a.length;

/** Support & resistance sederhana: low/high terendah-tertinggi N hari terakhir. */
export function levels(bars: Bar[], n = 20): Levels | null {
  const w = bars.slice(-n);
  if (w.length === 0) return null;
  return { support: min(w.map((b) => b.l)), resistance: max(w.map((b) => b.h)) };
}

/** Panjang basis: berapa hari bursa terakhir yang seluruhnya muat dalam range <= maxRange. */
export function baseDays(bars: Bar[], maxRange = BASE_MAX_RANGE): number {
  let hi = -Infinity, lo = Infinity, k = 0;
  for (let i = bars.length - 1; i >= 0; i--) {
    hi = Math.max(hi, bars[i].h);
    lo = Math.min(lo, bars[i].l);
    if ((hi - lo) / lo > maxRange) break;
    k++;
  }
  return k;
}

function valueAt(series: Series[], d: string): number | null {
  let v: number | null = null;
  for (const p of series) { if (p.d <= d) v = p.c; else break; }
  return v;
}

export function checklist(bars: Bar[], index: Series[], setupRR: number | null): CheckItem[] {
  const n = bars.length;
  if (n < 25) return [];
  const out: CheckItem[] = [];
  const last = bars[n - 1];

  const l1 = min(bars.slice(-10).map((b) => b.l)), l0 = min(bars.slice(-20, -10).map((b) => b.l));
  out.push({ label: "Higher low terbentuk", ok: l1 > l0,
    detail: `Low 10 hari terakhir ${idr(l1)} vs 10 hari sebelumnya ${idr(l0)}` });

  const h1 = max(bars.slice(-10).map((b) => b.h)), h0 = max(bars.slice(-20, -10).map((b) => b.h));
  out.push({ label: "Higher high terbentuk", ok: h1 > h0,
    detail: `High 10 hari terakhir ${idr(h1)} vs 10 hari sebelumnya ${idr(h0)}` });

  const w = bars.slice(-21), up: number[] = [], down: number[] = [];
  for (let i = 1; i < w.length; i++) {
    if (w[i].c > w[i - 1].c) up.push(w[i].v);
    else if (w[i].c < w[i - 1].c) down.push(w[i].v);
  }
  if (up.length && down.length) {
    const a = mean(up), b = mean(down);
    out.push({ label: "Volume lebih besar saat harga naik", ok: a > b,
      detail: `Rata-rata volume hari naik ${compact(a)} vs hari turun ${compact(b)} (20 hari)` });
  } else {
    out.push({ label: "Volume lebih besar saat harga naik", ok: null, detail: "Data hari naik/turun belum cukup" });
  }

  const ma20 = mean(bars.slice(-20).map((b) => b.c));
  out.push({ label: "Harga di atas MA20", ok: last.c > ma20,
    detail: `Penutupan ${idr(last.c)} vs MA20 ${idr(ma20)}` });

  const k = baseDays(bars);
  out.push({ label: `Basis konsolidasi minimal ${BASE_MIN_DAYS} hari`, ok: k >= BASE_MIN_DAYS,
    detail: `${k} hari bursa terakhir berada dalam range ≤ ${BASE_MAX_RANGE * 100}%` });

  const from = bars[n - 21];
  const i0 = valueAt(index, from.d), i1 = valueAt(index, last.d);
  if (i0 && i1) {
    const sr = last.c / from.c - 1, ir = i1 / i0 - 1;
    out.push({ label: "Lebih kuat dari IHSG (20 hari)", ok: sr > ir,
      detail: `Saham ${sgn(sr)} vs IHSG ${sgn(ir)}` });
  } else {
    out.push({ label: "Lebih kuat dari IHSG (20 hari)", ok: null, detail: "Data IHSG belum tersedia" });
  }

  out.push(setupRR != null
    ? { label: `Risk:Reward minimal 1 : ${RR_TARGET}`, ok: setupRR >= RR_TARGET, detail: `Trade setup aktif: 1 : ${setupRR.toFixed(2)}` }
    : { label: `Risk:Reward minimal 1 : ${RR_TARGET}`, ok: null, detail: "Tidak ada trade setup aktif (hanya untuk sinyal Mark Up)" });

  return out;
}

export function summarize(items: CheckItem[]) {
  const scored = items.filter((i) => i.ok !== null);
  return { passed: scored.filter((i) => i.ok).length, total: scored.length };
}
