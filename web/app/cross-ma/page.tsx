import Link from "next/link";
import { getSwingTrades, SwingTrade } from "@/lib/swing";
import { idr, pct } from "@/lib/format";

export const revalidate = 900;

const WARN: Record<string, string> = {
  ma_down: "MA5 sudah di bawah MA20 — menunggu dead cross MACD",
  macd_down: "MACD dead cross — menunggu MA5 cross down",
};
const median = (a: number[]) => {
  if (!a.length) return null;
  const s = [...a].sort((x, y) => x - y), m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const cls = (v: number | null) => ((v ?? 0) >= 0 ? "pos" : "neg");
const Stock = ({ t }: { t: SwingTrade }) => (
  <td><Link href={`/stocks/${t.code}`}><b>{t.code}</b></Link><small className="muted">{t.name}</small></td>
);

export default async function CrossMA() {
  const all = await getSwingTrades();

  if (all === null) {
    return (
      <main>
        <h1>Cross MA</h1>
        <p className="empty">Data posisi swing belum tersedia. Jalankan migrasi <code>006_swing_trades.sql</code> di database, lalu jalankan <code>etl_swing.py</code> satu kali.</p>
      </main>
    );
  }

  const open = all.filter((t) => t.status === "open").sort((a, b) => (b.ret ?? 0) - (a.ret ?? 0));
  const pending = all.filter((t) => t.status === "pending").sort((a, b) => (a.days ?? 0) - (b.days ?? 0));
  const closed = all.filter((t) => t.status === "closed").sort((a, b) => (b.exitDate ?? "").localeCompare(a.exitDate ?? ""));
  const warned = open.filter((t) => t.warning).length;
  const rets = closed.map((t) => t.ret).filter((v): v is number => v != null);
  const wins = rets.filter((v) => v > 0).length;
  const avg = rets.length ? rets.reduce((a, b) => a + b, 0) / rets.length : null;
  const avgDays = closed.length ? closed.reduce((a, t) => a + (t.days ?? 0), 0) / closed.length : null;
  const deepest = [...closed, ...open].map((t) => t.worst).filter((v): v is number => v != null);
  const asOf = all.map((t) => t.lastDate).sort().at(-1) ?? null;

  return (
    <main className="wide">
      <h1>Cross MA</h1>
      <p className="muted lead">Swing jangka menengah dari persilangan MA5 dan MA20 yang dikonfirmasi MACD{asOf ? ` · data sampai ${asOf}` : ""}.</p>

      <div className="rule">
        <p><b>Beli</b> saat MA5 menembus MA20 ke atas dan MACD golden cross terjadi berdekatan (dalam jendela hari bursa yang ditetapkan). Harga acuan adalah penutupan hari konfirmasi.</p>
        <p><b>Tahan</b> sampai MA5 berada di bawah MA20 <em>dan</em> MACD dead cross sama-sama terjadi setelah tanggal beli. Aturan ini tidak memakai stop loss, jadi lihat kolom &ldquo;Terdalam&rdquo; untuk mengetahui seberapa dalam harga pernah turun selama posisi dipegang.</p>
      </div>

      <div className="cards">
        <div className="card"><small>Sedang di-hold</small><b>{open.length}</b></div>
        <div className="card"><small>Peringatan keluar</small><b className={warned ? "warn" : ""}>{warned}</b></div>
        <div className="card"><small>Menunggu konfirmasi MACD</small><b>{pending.length}</b></div>
        <div className="card"><small>Posisi tertutup</small><b>{closed.length}</b></div>
      </div>

      <h2>Sedang di-hold</h2>
      {open.length === 0 ? <p className="empty">Tidak ada posisi aktif saat ini.</p> : (
        <div className="scroll"><table>
          <thead><tr><th>Saham</th><th>Masuk</th><th className="num">Harga masuk</th><th className="num">Sekarang</th><th className="num">P/L</th><th className="num">Hari</th><th className="num">Terdalam</th><th>Status</th></tr></thead>
          <tbody>{open.map((t) => (
            <tr key={t.code + t.entryDate}>
              <Stock t={t} />
              <td>{t.entryDate}</td>
              <td className="num">{idr(t.entryPrice)}</td>
              <td className="num">{idr(t.lastPrice)}</td>
              <td className={`num ${cls(t.ret)}`}>{pct(t.ret)}</td>
              <td className="num">{t.days}</td>
              <td className="num neg">{pct(t.worst)}</td>
              <td>{t.warning ? <span className="tag warn">{WARN[t.warning] ?? t.warning}</span> : <span className="tag ok">Tren masih utuh</span>}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}

      <h2>Menunggu konfirmasi MACD</h2>
      <p className="muted">MA5 sudah menembus MA20 ke atas, tetapi MACD golden cross belum terjadi.</p>
      {pending.length === 0 ? <p className="empty">Tidak ada saham yang sedang menunggu.</p> : (
        <div className="scroll"><table>
          <thead><tr><th>Saham</th><th>MA5 cross up</th><th className="num">Hari sejak cross</th><th className="num">Harga sekarang</th><th className="num">Sejak cross</th></tr></thead>
          <tbody>{pending.map((t) => (
            <tr key={t.code}>
              <Stock t={t} />
              <td>{t.maCrossDate}</td>
              <td className="num">{t.days}</td>
              <td className="num">{idr(t.lastPrice)}</td>
              <td className={`num ${cls(t.ret)}`}>{pct(t.ret)}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}

      <h2>Riwayat posisi tertutup</h2>
      {closed.length === 0 ? <p className="empty">Belum ada posisi yang tertutup pada data yang tersedia.</p> : (
        <>
          <div className="cards">
            <div className="card"><small>Menguntungkan</small><b>{rets.length ? `${Math.round((wins / rets.length) * 100)}%` : "–"}</b><small>{wins} dari {rets.length} posisi</small></div>
            <div className="card"><small>Rata-rata return</small><b className={cls(avg)}>{pct(avg)}</b><small>median {pct(median(rets))}</small></div>
            <div className="card"><small>Rata-rata lama hold</small><b>{avgDays != null ? Math.round(avgDays) : "–"} hari</b></div>
            <div className="card"><small>Penurunan terdalam</small><b className="neg">{deepest.length ? pct(Math.min(...deepest)) : "–"}</b><small>selama hold, tanpa stop loss</small></div>
          </div>
          <div className="scroll"><table>
            <thead><tr><th>Saham</th><th>Masuk</th><th>Keluar</th><th className="num">Harga masuk</th><th className="num">Harga keluar</th><th className="num">Return</th><th className="num">Hari</th><th className="num">Terdalam</th></tr></thead>
            <tbody>{closed.slice(0, 60).map((t, i) => (
              <tr key={t.code + t.entryDate + i}>
                <Stock t={t} />
                <td>{t.entryDate}</td><td>{t.exitDate}</td>
                <td className="num">{idr(t.entryPrice)}</td><td className="num">{idr(t.exitPrice)}</td>
                <td className={`num ${cls(t.ret)}`}>{pct(t.ret)}</td>
                <td className="num">{t.days}</td><td className="num neg">{pct(t.worst)}</td>
              </tr>
            ))}</tbody>
          </table></div>
          {closed.length > 60 && <p className="muted">Menampilkan 60 posisi terbaru dari {closed.length}.</p>}
          <p className="muted fine">Statistik ini berasal dari simulasi aturan pada histori yang tersedia, dengan harga acuan penutupan hari sinyal dan tanpa biaya transaksi. Hasil historis tidak menjamin hasil ke depan, dan bukan rekomendasi investasi.</p>
        </>
      )}
    </main>
  );
}
