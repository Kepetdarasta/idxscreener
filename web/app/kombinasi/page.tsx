import Link from "next/link";
import { CATEGORIES, ComboCategory, combine } from "@/lib/combo";
import { getStockRows } from "@/lib/data";
import { idr, pct } from "@/lib/format";
import { phaseOf } from "@/lib/phases";
import { getSwingTrades } from "@/lib/swing";

export const revalidate = 900;

const tagClass: Record<ComboCategory, string> = { kuat: "tag ok", awal: "tag", fase: "tag", waspada: "tag warn" };

export default async function Kombinasi({ searchParams }: { searchParams: Promise<{ view?: string }> }) {
  const { view } = await searchParams;
  const [{ rows, screenDate }, trades] = await Promise.all([getStockRows(), getSwingTrades()]);

  if (trades === null) {
    return (
      <main>
        <h1>Kombinasi</h1>
        <p className="empty">Data posisi swing belum tersedia. Jalankan migrasi <code>006_swing_trades.sql</code> lalu <code>etl_swing.py</code>.</p>
      </main>
    );
  }

  const all = combine(rows, trades);
  const keys = Object.keys(CATEGORIES) as ComboCategory[];
  const counts = Object.fromEntries(keys.map((k) => [k, all.filter((r) => r.category === k).length])) as Record<ComboCategory, number>;
  const cur = view && (keys as string[]).includes(view) ? (view as ComboCategory) : null;
  const list = all.filter((r) => !cur || r.category === cur);

  return (
    <main className="wide">
      <h1>Kombinasi</h1>
      <p className="muted lead">
        Menyandingkan dua sistem: fase siklus (ADMD) dan posisi swing MA5/MA20 + MACD{screenDate ? ` · penutupan ${screenDate}` : ""}.
        Saham yang kedua sistemnya searah punya dukungan lebih kuat daripada yang hanya lolos salah satu.
      </p>

      <div className="cards">
        <Link href="/kombinasi" className={`card ${!cur ? "on" : ""}`}><small>Semua kategori</small><b>{all.length}</b></Link>
        {keys.map((k) => (
          <Link key={k} href={`/kombinasi?view=${k}`} className={`card ${cur === k ? "on" : ""}`}>
            <small>{CATEGORIES[k].label}</small><b className={k === "waspada" && counts[k] ? "warn" : ""}>{counts[k]}</b>
          </Link>
        ))}
      </div>
      {cur && <p className="muted">{CATEGORIES[cur].desc}.</p>}

      {list.length === 0 ? (
        <p className="empty">Tidak ada saham pada kategori ini saat ini.</p>
      ) : (
        <div className="scroll">
          <table>
            <thead><tr><th>Kategori</th><th>Saham</th><th>Fase ADMD</th><th>Posisi swing</th><th className="num">Harga</th><th className="num">Hari ini</th><th>Catatan</th></tr></thead>
            <tbody>
              {list.map(({ stock: s, swing: w, category, note }) => (
                <tr key={s.code}>
                  <td><span className={tagClass[category]}>{CATEGORIES[category].label}</span></td>
                  <td><Link href={`/stocks/${s.code}`}><b>{s.code}</b></Link><small className="muted">{s.name}</small></td>
                  <td>{s.phase ? <><i className="dot" style={{ background: phaseOf(s.phase).color }} />{phaseOf(s.phase).label}<small className="muted">skor {s.score}</small></> : <span className="muted">Tanpa sinyal</span>}</td>
                  <td>
                    {w?.status === "open" ? <>Hold <span className={(w.ret ?? 0) >= 0 ? "pos" : "neg"}>{pct(w.ret)}</span><small className="muted">sejak {w.entryDate} · {w.days} hari</small></>
                      : w?.status === "pending" ? <>Menunggu MACD<small className="muted">MA5 cross up {w.maCrossDate}</small></>
                      : <span className="muted">–</span>}
                  </td>
                  <td className="num">{idr(s.close)}</td>
                  <td className={`num ${(s.chg ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(s.chg)}</td>
                  <td className="note">{note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted fine">Penyaringan otomatis dari dua indikator berbasis harga dan volume, bukan jaminan hasil dan bukan rekomendasi investasi. Saham yang tidak masuk kategori mana pun tidak ditampilkan di sini.</p>
    </main>
  );
}
