import Link from "next/link";
import { getStockRows } from "@/lib/data";
import { pct } from "@/lib/format";
import type { StockRow } from "@/lib/types";

export const revalidate = 900;

// Skala warna: ±3% = intensitas penuh. Warna dicampur ke latar panel.
const tone = (chg: number | null) => {
  if (chg == null) return "#182434";
  const k = Math.round(Math.min(Math.abs(chg) / 3, 1) * 70);
  return `color-mix(in srgb, ${chg >= 0 ? "#3fb97f" : "#e5564b"} ${k}%, #182434)`;
};

export default async function Heatmap() {
  const { rows } = await getStockRows();
  const bySector = new Map<string, StockRow[]>();
  for (const r of rows) {
    const k = r.sector ?? "Belum dikelompokkan";
    bySector.set(k, [...(bySector.get(k) ?? []), r]);
  }
  const sectors = Array.from(bySector, ([name, list]) => {
    const vals = list.map((x) => x.chg).filter((v): v is number => v != null);
    return { name, list, avg: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null };
  }).sort((a, b) => (b.avg ?? -999) - (a.avg ?? -999));

  return (
    <main className="wide">
      <h1>Heatmap sektor</h1>
      <p className="muted lead">Perubahan harga satu hari per saham, dikelompokkan per sektor. Rata-rata sektor dihitung sederhana (bobot sama), bukan berdasarkan kapitalisasi pasar.</p>
      <div className="heat">
        {sectors.map((s) => (
          <section key={s.name} className="heat-sector">
            <header style={{ background: tone(s.avg) }}>
              <b>{s.name}</b><span>{pct(s.avg)}</span>
            </header>
            <div className="heat-grid">
              {s.list.map((r) => (
                <Link key={r.code} href={`/stocks/${r.code}`} style={{ background: tone(r.chg) }} title={r.name}>
                  <b>{r.code}</b><span>{pct(r.chg, 1)}</span>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </main>
  );
}
