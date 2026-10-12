import type { StockRow } from "./types";
import type { SwingTrade } from "./swing";
import { phaseOf } from "./phases";

export type ComboCategory = "kuat" | "awal" | "fase" | "waspada";

export const CATEGORIES: Record<ComboCategory, { label: string; desc: string; order: number }> = {
  kuat: { label: "Selaras kuat", desc: "Fase akumulasi/mark up dan posisi swing sedang di-hold tanpa peringatan", order: 0 },
  awal: { label: "Selaras awal", desc: "Fase akumulasi/mark up dan MA5 sudah cross up, menunggu golden cross MACD", order: 1 },
  fase: { label: "Fase mendukung", desc: "Fase akumulasi/mark up, tetapi belum ada persilangan swing yang dikonfirmasi", order: 2 },
  waspada: { label: "Waspada", desc: "Posisi swing masih di-hold, namun ada peringatan keluar atau fase ADMD memburuk", order: 3 },
};

export type ComboRow = { stock: StockRow; swing: SwingTrade | null; category: ComboCategory; note: string };

const GOOD = new Set(["accumulation", "markup"]);
const BAD = new Set(["distribution", "markdown"]);
const WARN: Record<string, string> = {
  ma_down: "MA5 sudah di bawah MA20, menunggu dead cross MACD",
  macd_down: "MACD sudah dead cross, menunggu MA5 cross down",
};

/** Gabungkan fase ADMD (hari ini) dengan posisi swing yang sedang berjalan (open/pending). */
export function combine(stocks: StockRow[], trades: SwingTrade[]): ComboRow[] {
  const current = new Map<string, SwingTrade>();
  for (const t of trades) if (t.status === "open" || t.status === "pending") current.set(t.code, t);

  const out: ComboRow[] = [];
  for (const s of stocks) {
    const sw = current.get(s.code) ?? null;
    const good = s.phase != null && GOOD.has(s.phase);
    const bad = s.phase != null && BAD.has(s.phase);
    let category: ComboCategory | null = null;
    let note = "";

    if (sw?.status === "open") {
      if (bad) { category = "waspada"; note = `ADMD menunjukkan ${phaseOf(s.phase).label}, sementara posisi swing masih di-hold`; }
      else if (sw.warning) { category = "waspada"; note = WARN[sw.warning] ?? sw.warning; }
      else if (good) { category = "kuat"; note = "Fase dan tren swing searah"; }
    } else if (sw?.status === "pending") {
      if (good) { category = "awal"; note = `MA5 cross up ${sw.maCrossDate ?? ""}, tinggal menunggu golden cross MACD`.replace("  ", " "); }
    } else if (good) {
      category = "fase"; note = "Belum ada persilangan MA5/MA20 yang dikonfirmasi MACD";
    }

    if (category) out.push({ stock: s, swing: sw, category, note });
  }
  return out.sort((a, b) =>
    CATEGORIES[a.category].order - CATEGORIES[b.category].order || (b.stock.score ?? 0) - (a.stock.score ?? 0));
}
