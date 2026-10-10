import Link from "next/link";
import { notFound } from "next/navigation";
import { sql } from "@/lib/db";
import { phaseOf } from "@/lib/phases";
import PhaseChart, { PhaseBand, PricePoint, TradeSetup } from "@/components/PhaseChart";

const fmt = (n: number) => n.toLocaleString("id-ID");
const pct = (a: number, b: number) => { const v = (a / b - 1) * 100; return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`; };

export const revalidate = 900;

type Phase = {
  phase: string; start: string; end: string | null;
  price_at_start: string; price_at_end: string | null; price_change_pct: string | null; duration_days: number | null;
};

export default async function StockPage({ params }: { params: Promise<{ code: string }> }) {
  const code = (await params).code.toUpperCase();

  const stock = await sql`SELECT stock_name FROM stocks WHERE stock_code = ${code}`;
  if (stock.length === 0) notFound();

  const prices = (await sql`
    SELECT to_char(trade_date,'YYYY-MM-DD') AS d, close_price::float AS close
    FROM daily_ohlcv WHERE stock_code = ${code}
    ORDER BY trade_date DESC LIMIT 250`).reverse() as PricePoint[];

  const phases = (await sql`
    SELECT phase, to_char(phase_start,'YYYY-MM-DD') AS start, to_char(phase_end,'YYYY-MM-DD') AS "end",
           price_at_start, price_at_end, price_change_pct, duration_days
    FROM phase_history WHERE stock_code = ${code} ORDER BY phase_start DESC`) as Phase[];

  // Pita fase dipotong ke tanggal bursa yang ada di grafik
  const first = prices[0]?.d, last = prices.at(-1)?.d;
  const bands: PhaseBand[] = [];
  for (const p of phases) {
    const end = p.end ?? last;
    if (!first || !last || !end || end < first) continue;
    const from = prices.find((x) => x.d >= p.start && x.d >= first)?.d;
    const to = [...prices].reverse().find((x) => x.d <= end)?.d;
    if (from && to && from <= to) bands.push({ phase: p.phase, from, to });
  }

  // Trade setup: hanya bila sinyal terbaru saham ini Mark Up dan datanya sama-sama terbaru
  const latest = await sql`
    SELECT phase, to_char(screen_date,'YYYY-MM-DD') AS d,
           entry_price::float AS entry, stop_loss::float AS stop,
           target_price::float AS target, risk_reward_ratio::float AS rr
    FROM screening_results WHERE stock_code = ${code}
    ORDER BY screen_date DESC LIMIT 1`;
  const sig = latest[0] as
    | { phase: string; d: string; entry: number | null; stop: number | null; target: number | null; rr: number | null }
    | undefined;
  const setup: (TradeSetup & { rr: number; date: string }) | null =
    sig && sig.phase === "markup" && sig.d === last &&
    sig.entry != null && sig.stop != null && sig.target != null && sig.rr != null
      ? { entry: sig.entry, stop: sig.stop, target: sig.target, rr: sig.rr, date: sig.d }
      : null;

  return (
    <main>
      <p><Link href="/">Kembali ke daftar</Link></p>
      <h1>{code} <span className="muted">{stock[0].stock_name}</span></h1>

      {prices.length === 0 ? <p>Belum ada data harga untuk saham ini.</p> : <PhaseChart prices={prices} bands={bands} setup={setup} />}

      {setup && (
        <>
          <h2>Trade setup</h2>
          <div className="scroll">
            <table>
              <thead><tr><th>Entry</th><th>Stop loss</th><th>Target</th><th className="num">Risk : Reward</th></tr></thead>
              <tbody>
                <tr>
                  <td>{fmt(setup.entry)}</td>
                  <td>{fmt(setup.stop)} ({pct(setup.stop, setup.entry)})</td>
                  <td>{fmt(setup.target)} ({pct(setup.target, setup.entry)})</td>
                  <td className="num">1 : {setup.rr.toFixed(2)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="muted">Dihitung otomatis dari harga dan volume penutupan {setup.date}. Bukan rekomendasi investasi.</p>
        </>
      )}

      <h2>Riwayat fase</h2>
      {phases.length === 0 ? <p>Belum ada fase tercatat.</p> : (
        <div className="scroll">
          <table>
            <thead><tr><th>Fase</th><th>Mulai</th><th>Selesai</th><th className="num">Hari</th><th className="num">Harga awal</th><th className="num">Harga akhir</th><th className="num">Perubahan</th></tr></thead>
            <tbody>
              {phases.map((p, i) => (
                <tr key={i}>
                  <td><i className="dot" style={{ background: phaseOf(p.phase).color }} />{phaseOf(p.phase).label}</td>
                  <td>{p.start}</td>
                  <td>{p.end ?? "berjalan"}</td>
                  <td className="num">{p.duration_days ?? "–"}</td>
                  <td className="num">{Number(p.price_at_start).toLocaleString("id-ID")}</td>
                  <td className="num">{p.price_at_end ? Number(p.price_at_end).toLocaleString("id-ID") : "–"}</td>
                  <td className="num">{p.price_change_pct != null ? `${Number(p.price_change_pct).toFixed(2)}%` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
