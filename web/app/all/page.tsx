import Link from "next/link";
import { getStockRows } from "@/lib/data";
import { idr, pct } from "@/lib/format";
import { phaseOf } from "@/lib/phases";

export const revalidate = 900;

export default async function AllStocks({ searchParams }: { searchParams: Promise<{ sector?: string }> }) {
  const { sector } = await searchParams;
  const { rows } = await getStockRows();
  const sectors = Array.from(new Set(rows.map((r) => r.sector).filter((s): s is string => !!s))).sort();
  const cur = sector && sectors.includes(sector) ? sector : null;
  const list = rows.filter((r) => !cur || r.sector === cur);

  return (
    <main>
      <h1>Semua saham</h1>
      <p className="muted lead">{list.length} saham dalam universe yang dipantau, termasuk yang tidak sedang bersinyal.</p>
      <div className="filters">
        <Link className={`chip ${!cur ? "on" : ""}`} href="/all">Semua sektor</Link>
        {sectors.map((s) => (
          <Link key={s} className={`chip ${cur === s ? "on" : ""}`} href={`/all?sector=${encodeURIComponent(s)}`}>{s}</Link>
        ))}
      </div>
      <div className="scroll">
        <table>
          <thead><tr><th>Kode</th><th>Nama</th><th>Sektor</th><th>Fase</th><th className="num">Penutupan</th><th className="num">Hari ini</th></tr></thead>
          <tbody>
            {list.map((r) => (
              <tr key={r.code}>
                <td><Link href={`/stocks/${r.code}`}><b>{r.code}</b></Link></td>
                <td>{r.name}</td>
                <td>{r.sector ?? "–"}</td>
                <td>{r.phase ? <><i className="dot" style={{ background: phaseOf(r.phase).color }} />{phaseOf(r.phase).label}</> : <span className="muted">Tanpa sinyal</span>}</td>
                <td className="num">{idr(r.close)}</td>
                <td className={`num ${(r.chg ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(r.chg)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
