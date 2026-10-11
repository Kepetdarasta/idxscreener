import { sql } from "./db";
import { Bar, Series, checklist, levels } from "./analysis";
import type { PhaseBand, PhaseRow, PricePoint, StockDetailData, StockRow, TradeSetup } from "./types";

type Rec = Record<string, unknown>;
const rows = (r: unknown) => r as unknown as Rec[];

// ── IHSG ────────────────────────────────────────────────────────────────────
export async function getIndexSeries(limit = 200): Promise<Series[]> {
  try {
    const r = rows(await sql`
      SELECT to_char(trade_date,'YYYY-MM-DD') AS d, close_price::float AS c
      FROM market_index WHERE index_code = 'IHSG' ORDER BY trade_date DESC LIMIT ${limit}`);
    return (r as unknown as Series[]).reverse();
  } catch {
    return []; // tabel belum ada / belum terisi: fitur IHSG dilewati
  }
}

export async function getIndexBar() {
  const s = await getIndexSeries(2);
  if (s.length === 0) return null;
  const last = s[s.length - 1];
  const prev = s.length > 1 ? s[s.length - 2] : null;
  return { date: last.d, close: last.c, chg: prev ? (last.c / prev.c - 1) * 100 : null };
}

// ── Daftar saham ─────────────────────────────────────────────────────────────
async function latestChanges() {
  const r = rows(await sql`
    SELECT stock_code, last_close::float AS last_close, prev_close::float AS prev_close FROM (
      SELECT stock_code, close_price AS last_close,
             LAG(close_price) OVER (PARTITION BY stock_code ORDER BY trade_date) AS prev_close,
             ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date DESC) AS rn
      FROM daily_ohlcv WHERE trade_date >= CURRENT_DATE - 14
    ) t WHERE rn = 1`);
  const m = new Map<string, { close: number; chg: number | null }>();
  for (const x of r) {
    const c = x.last_close as number, p = x.prev_close as number | null;
    m.set(x.stock_code as string, { close: c, chg: p ? (c / p - 1) * 100 : null });
  }
  return m;
}

/** Semua saham aktif + sinyal terbaru (phase/score/rr null bila tidak ada sinyal hari itu). */
export async function getStockRows(): Promise<{ rows: StockRow[]; screenDate: string | null }> {
  const [stocks, scr, chg] = await Promise.all([
    sql`SELECT stock_code, stock_name, sector FROM stocks WHERE is_active ORDER BY stock_code`,
    sql`SELECT stock_code, signal_score, phase, risk_reward_ratio::float AS rr,
               to_char(screen_date,'YYYY-MM-DD') AS d FROM v_screening_latest`,
    latestChanges(),
  ]);
  const sig = new Map(rows(scr).map((x) => [x.stock_code as string, x]));
  const out: StockRow[] = rows(stocks).map((s) => {
    const code = s.stock_code as string, g = sig.get(code), c = chg.get(code);
    return {
      code, name: s.stock_name as string, sector: (s.sector as string | null) ?? null,
      phase: g ? (g.phase as string) : null,
      score: g ? Number(g.signal_score) : null,
      rr: g && g.rr != null ? Number(g.rr) : null,
      close: c?.close ?? null, chg: c?.chg ?? null,
    };
  });
  const first = rows(scr)[0];
  return { rows: out, screenDate: first ? (first.d as string) : null };
}

// ── Detail satu saham ────────────────────────────────────────────────────────
function toBands(prices: PricePoint[], phases: { phase: string; start: string; end: string | null }[]): PhaseBand[] {
  const first = prices[0]?.d, last = prices[prices.length - 1]?.d;
  const out: PhaseBand[] = [];
  if (!first || !last) return out;
  for (const p of phases) {
    const end = p.end ?? last;
    if (end < first) continue;
    const from = prices.find((x) => x.d >= p.start)?.d;
    const to = [...prices].reverse().find((x) => x.d <= end)?.d;
    if (from && to && from <= to) out.push({ phase: p.phase, from, to });
  }
  return out;
}

export async function getStockDetail(codeRaw: string): Promise<StockDetailData | null> {
  const code = codeRaw.toUpperCase();
  if (!/^[A-Z0-9]{1,10}$/.test(code)) return null;

  const [stock, ohlcv, phases, latest, index] = await Promise.all([
    sql`SELECT stock_name, sector FROM stocks WHERE stock_code = ${code}`,
    sql`SELECT to_char(trade_date,'YYYY-MM-DD') AS d, high_price::float AS h, low_price::float AS l,
               close_price::float AS c, volume::float AS v
        FROM daily_ohlcv WHERE stock_code = ${code} ORDER BY trade_date DESC LIMIT 160`,
    sql`SELECT phase, to_char(phase_start,'YYYY-MM-DD') AS start, to_char(phase_end,'YYYY-MM-DD') AS "end",
               duration_days, price_at_start::float AS price_start, price_at_end::float AS price_end,
               price_change_pct::float AS change_pct
        FROM phase_history WHERE stock_code = ${code} ORDER BY phase_start DESC`,
    sql`SELECT phase, signal_score, to_char(screen_date,'YYYY-MM-DD') AS d,
               entry_price::float AS entry, stop_loss::float AS stop,
               target_price::float AS target, risk_reward_ratio::float AS rr
        FROM screening_results WHERE stock_code = ${code} ORDER BY screen_date DESC LIMIT 1`,
    getIndexSeries(),
  ]);
  const s = rows(stock)[0];
  if (!s) return null;

  const bars = (rows(ohlcv) as unknown as Bar[]).slice().reverse();
  if (bars.length === 0) return null;
  const lastBar = bars[bars.length - 1], prevBar = bars[bars.length - 2];

  const sig = rows(latest)[0];
  const fresh = sig && (sig.d as string) === lastBar.d; // sinyal hanya dipakai bila sama dengan data harga terakhir
  const setup: TradeSetup | null =
    fresh && sig.phase === "markup" && sig.entry != null && sig.stop != null && sig.target != null && sig.rr != null
      ? { entry: sig.entry as number, stop: sig.stop as number, target: sig.target as number, rr: sig.rr as number, date: sig.d as string }
      : null;

  const prices: PricePoint[] = bars.slice(-120).map((b) => ({ d: b.d, close: b.c }));
  const ph = rows(phases);

  return {
    code, name: s.stock_name as string, sector: (s.sector as string | null) ?? null,
    last: { d: lastBar.d, close: lastBar.c, chg: prevBar ? (lastBar.c / prevBar.c - 1) * 100 : null },
    signal: fresh ? { phase: sig.phase as string, score: Number(sig.signal_score) } : null,
    setup,
    levels: levels(bars, 20),
    prices,
    bands: toBands(prices, ph.map((p) => ({ phase: p.phase as string, start: p.start as string, end: (p.end as string | null) ?? null }))),
    checklist: checklist(bars, index, setup ? setup.rr : null),
    history: ph.map((p): PhaseRow => ({
      phase: p.phase as string, start: p.start as string, end: (p.end as string | null) ?? null,
      days: p.duration_days == null ? null : Number(p.duration_days),
      priceStart: p.price_start as number, priceEnd: (p.price_end as number | null) ?? null,
      changePct: (p.change_pct as number | null) ?? null,
    })),
  };
}
