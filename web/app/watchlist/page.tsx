"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import StarButton from "@/components/StarButton";
import { idr, pct } from "@/lib/format";
import { phaseOf } from "@/lib/phases";
import { useWatchlist } from "@/lib/useWatchlist";
import type { StockRow } from "@/lib/types";

export default function Watchlist() {
  const { list, ready } = useWatchlist();
  const [rows, setRows] = useState<StockRow[]>([]);
  const [loading, setLoading] = useState(false);
  const key = list.join(",");

  useEffect(() => {
    if (!ready) return;
    if (!key) { setRows([]); return; }
    const ctrl = new AbortController();
    setLoading(true);
    fetch(`/api/stocks?codes=${encodeURIComponent(key)}`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((d: StockRow[]) => { setRows(d); setLoading(false); })
      .catch(() => { /* dibatalkan */ });
    return () => ctrl.abort();
  }, [key, ready]);

  const shown = rows.filter((r) => list.includes(r.code));

  return (
    <main>
      <h1>Watchlist</h1>
      <p className="muted lead">Tersimpan di browser ini saja (tanpa login), jadi tidak ikut berpindah ke perangkat atau browser lain.</p>
      {!ready || loading ? <p className="muted">Memuat…</p>
        : shown.length === 0 ? <p className="empty">Watchlist masih kosong. Klik ikon bintang ☆ pada saham mana pun untuk menambahkannya.</p>
        : (
          <div className="scroll">
            <table>
              <thead><tr><th aria-label="Hapus" /><th>Kode</th><th>Nama</th><th>Fase</th><th className="num">Penutupan</th><th className="num">Hari ini</th></tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.code}>
                    <td><StarButton code={r.code} /></td>
                    <td><Link href={`/stocks/${r.code}`}><b>{r.code}</b></Link></td>
                    <td>{r.name}</td>
                    <td>{r.phase ? <><i className="dot" style={{ background: phaseOf(r.phase).color }} />{phaseOf(r.phase).label}</> : <span className="muted">Tanpa sinyal</span>}</td>
                    <td className="num">{idr(r.close)}</td>
                    <td className={`num ${(r.chg ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(r.chg)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </main>
  );
}
