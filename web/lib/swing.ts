import { sql } from "./db";

export type SwingTrade = {
  code: string; name: string; sector: string | null;
  status: "pending" | "open" | "closed";
  entryDate: string | null; entryPrice: number | null;
  exitDate: string | null; exitPrice: number | null;
  lastDate: string; lastPrice: number;
  ret: number | null; days: number | null; worst: number | null;
  warning: string | null; maCrossDate: string | null; macdCrossDate: string | null;
};

/** null = tabel swing_trades belum ada (migrasi 006 belum dijalankan). */
export async function getSwingTrades(): Promise<SwingTrade[] | null> {
  try {
    const r = (await sql`
      SELECT t.stock_code, s.stock_name, s.sector, t.status,
             to_char(t.entry_date,'YYYY-MM-DD') AS entry_date, t.entry_price::float AS entry_price,
             to_char(t.exit_date,'YYYY-MM-DD') AS exit_date, t.exit_price::float AS exit_price,
             to_char(t.last_date,'YYYY-MM-DD') AS last_date, t.last_price::float AS last_price,
             t.return_pct::float AS ret, t.days_held, t.worst_pct::float AS worst, t.warning,
             to_char(t.ma_cross_date,'YYYY-MM-DD') AS ma_cross_date,
             to_char(t.macd_cross_date,'YYYY-MM-DD') AS macd_cross_date
      FROM swing_trades t JOIN stocks s ON s.stock_code = t.stock_code
      ORDER BY t.entry_date DESC NULLS LAST`) as unknown as Record<string, unknown>[];
    return r.map((x) => ({
      code: x.stock_code as string, name: x.stock_name as string, sector: (x.sector as string | null) ?? null,
      status: x.status as SwingTrade["status"],
      entryDate: (x.entry_date as string | null) ?? null, entryPrice: (x.entry_price as number | null) ?? null,
      exitDate: (x.exit_date as string | null) ?? null, exitPrice: (x.exit_price as number | null) ?? null,
      lastDate: x.last_date as string, lastPrice: x.last_price as number,
      ret: (x.ret as number | null) ?? null, days: x.days_held == null ? null : Number(x.days_held),
      worst: (x.worst as number | null) ?? null, warning: (x.warning as string | null) ?? null,
      maCrossDate: (x.ma_cross_date as string | null) ?? null, macdCrossDate: (x.macd_cross_date as string | null) ?? null,
    }));
  } catch {
    return null;
  }
}
