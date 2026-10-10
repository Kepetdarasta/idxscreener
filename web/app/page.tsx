import Link from "next/link";
import { sql } from "@/lib/db";
import { PHASES, phaseOf } from "@/lib/phases";

export const revalidate = 900; // data baru masuk sekali per hari; cache 15 menit cukup

type Row = {
  stock_code: string; stock_name: string; sector: string | null; screen_date: string;
  close_price: string; signal_score: number; phase: string; risk_reward_ratio: string | null;
};

export default async function Home({ searchParams }: { searchParams: Promise<{ phase?: string }> }) {
  const { phase } = await searchParams;
  const valid = phase && phase in PHASES ? phase : null;

  const rows = (valid
    ? await sql`SELECT stock_code, stock_name, sector, to_char(screen_date,'YYYY-MM-DD') AS screen_date,
                       close_price, signal_score, phase, risk_reward_ratio FROM v_screening_latest WHERE phase = ${valid}`
    : await sql`SELECT stock_code, stock_name, sector, to_char(screen_date,'YYYY-MM-DD') AS screen_date,
                       close_price, signal_score, phase, risk_reward_ratio FROM v_screening_latest`) as Row[];

  return (
    <main>
      <h1>Saham IDX menurut fase siklusnya</h1>
      <p className="muted">
        {rows[0] ? `Data penutupan ${rows[0].screen_date}.` : "Belum ada data screening."} Hanya saham yang sinyalnya terdeteksi hari itu yang tampil.
      </p>

      <nav className="filters">
        <Link href="/" className={!valid ? "on" : ""}>Semua</Link>
        {(["accumulation", "markup", "distribution", "markdown"] as const).map((k) => (
          <Link key={k} href={`/?phase=${k}`} className={valid === k ? "on" : ""}>
            <i style={{ background: PHASES[k].color }} />{PHASES[k].label}
          </Link>
        ))}
      </nav>

      {rows.length === 0 ? (
        <p>Tidak ada saham di fase ini hari ini. Coba pilih fase lain.</p>
      ) : (
        <div className="scroll">
          <table>
            <thead><tr><th>Kode</th><th>Nama</th><th>Sektor</th><th>Fase</th><th className="num">Penutupan</th><th className="num">Skor</th><th className="num">RR</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.stock_code}>
                  <td><Link href={`/stocks/${r.stock_code}`}><b>{r.stock_code}</b></Link></td>
                  <td>{r.stock_name}</td>
                  <td>{r.sector ?? "–"}</td>
                  <td><i className="dot" style={{ background: phaseOf(r.phase).color }} />{phaseOf(r.phase).label}</td>
                  <td className="num">{Number(r.close_price).toLocaleString("id-ID")}</td>
                  <td className="num">{r.signal_score}</td>
                  <td className="num">{r.risk_reward_ratio ? Number(r.risk_reward_ratio).toFixed(2) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}