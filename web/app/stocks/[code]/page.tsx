import Link from "next/link";
import { notFound } from "next/navigation";
import { sql } from "@/lib/db";
import { phaseOf } from "@/lib/phases";
import PhaseChart, { PhaseBand, PricePoint } from "@/components/PhaseChart";

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

  return (
    <main>
      <p><Link href="/">Kembali ke daftar</Link></p>
      <h1>{code} <span className="muted">{stock[0].stock_name}</span></h1>

      {prices.length === 0 ? <p>Belum ada data harga untuk saham ini.</p> : <PhaseChart prices={prices} bands={bands} />}

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
