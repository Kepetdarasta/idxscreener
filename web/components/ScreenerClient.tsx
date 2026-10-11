"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import StarButton from "./StarButton";
import StockDetail from "./StockDetail";
import { idr, pct } from "@/lib/format";
import { PHASES, PHASE_ORDER, phaseOf } from "@/lib/phases";
import type { StockDetailData, StockRow } from "@/lib/types";

type Sort = "score" | "chg" | "rr";
const SORTS: Record<Sort, string> = { score: "Skor tertinggi", chg: "Kenaikan hari ini", rr: "Risk:Reward" };
const cmp = (s: Sort) => (a: StockRow, b: StockRow) =>
  s === "score" ? (b.score ?? 0) - (a.score ?? 0)
  : s === "chg" ? (b.chg ?? -999) - (a.chg ?? -999)
  : (b.rr ?? -1) - (a.rr ?? -1);
const wide = () => window.matchMedia("(min-width: 900px)").matches;

export default function ScreenerClient({ rows, date }: { rows: StockRow[]; date: string | null }) {
  const router = useRouter();
  const [phases, setPhases] = useState<string[]>([]);
  const [sector, setSector] = useState("all");
  const [minScore, setMinScore] = useState(0);
  const [sort, setSort] = useState<Sort>("score");
  const [sel, setSel] = useState<string | null>(null);
  const [detail, setDetail] = useState<StockDetailData | null>(null);
  const [loading, setLoading] = useState(false);

  const sectors = useMemo(
    () => Array.from(new Set(rows.map((r) => r.sector).filter((s): s is string => !!s))).sort(),
    [rows],
  );
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of rows) if (r.phase) c[r.phase] = (c[r.phase] ?? 0) + 1;
    return c;
  }, [rows]);
  const list = useMemo(
    () => rows
      .filter((r) => (phases.length === 0 || phases.includes(r.phase ?? ""))
        && (sector === "all" || r.sector === sector)
        && (r.score ?? 0) >= minScore)
      .sort(cmp(sort)),
    [rows, phases, sector, minScore, sort],
  );
  const active = list.find((r) => r.code === sel)?.code ?? list[0]?.code ?? null;

  useEffect(() => {
    if (!active) { setDetail(null); return; }
    if (!wide()) return;
    const ctrl = new AbortController();
    setLoading(true);
    fetch(`/api/stock/${active}`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setDetail(d); setLoading(false); })
      .catch(() => { /* dibatalkan saat ganti pilihan */ });
    return () => ctrl.abort();
  }, [active]);

  const toggle = (p: string) => setPhases((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]));
  const open = (code: string) => { if (wide()) setSel(code); else router.push(`/stocks/${code}`); };

  return (
    <div className="split">
      <div>
        <div className="filters" role="group" aria-label="Filter fase">
          {PHASE_ORDER.map((k) => (
            <button key={k} type="button" className={`chip ${phases.includes(k) ? "on" : ""}`}
              aria-pressed={phases.includes(k)} onClick={() => toggle(k)}>
              <i className="dot" style={{ background: PHASES[k].color }} />{PHASES[k].label}
              <span className="muted">{counts[k] ?? 0}</span>
            </button>
          ))}
          {phases.length > 0 && <button type="button" className="chip reset" onClick={() => setPhases([])}>Reset</button>}
        </div>

        <div className="controls">
          <label>Sektor
            <select value={sector} onChange={(e) => setSector(e.target.value)}>
              <option value="all">Semua sektor</option>
              {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>Skor minimum: <b>{minScore}</b>
            <input type="range" min={0} max={100} step={5} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} />
          </label>
          <label>Urutkan
            <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              {(Object.keys(SORTS) as Sort[]).map((k) => <option key={k} value={k}>{SORTS[k]}</option>)}
            </select>
          </label>
        </div>

        <p className="muted count">
          {rows.length === 0 ? "Belum ada sinyal pada data terakhir." : `Menampilkan ${list.length} dari ${rows.length} saham bersinyal`}
          {date ? ` · penutupan ${date}` : ""}
        </p>

        {list.length === 0 ? (
          <p className="empty">Tidak ada saham yang memenuhi filter. Longgarkan skor minimum atau pilih fase lain.</p>
        ) : (
          <div className="scroll">
            <table className="rows">
              <thead><tr><th aria-label="Watchlist" /><th>Saham</th><th>Fase</th><th className="num">Harga</th><th className="num">Hari ini</th><th className="num">Skor</th><th className="num">RR</th></tr></thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.code} className={r.code === active ? "sel" : ""} tabIndex={0}
                    onClick={() => open(r.code)}
                    onKeyDown={(e) => { if (e.key === "Enter") open(r.code); }}>
                    <td><StarButton code={r.code} /></td>
                    <td><b>{r.code}</b><small className="muted">{r.name}{r.sector ? ` · ${r.sector}` : ""}</small></td>
                    <td><i className="dot" style={{ background: phaseOf(r.phase).color }} />{phaseOf(r.phase).label}</td>
                    <td className="num">{idr(r.close)}</td>
                    <td className={`num ${(r.chg ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(r.chg)}</td>
                    <td className="num">{r.score ?? "–"}</td>
                    <td className="num">{r.rr != null ? r.rr.toFixed(2) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <aside className="panel" aria-live="polite">
        {detail && detail.code === active ? <StockDetail data={detail} />
          : loading ? <p className="muted">Memuat detail…</p>
          : <p className="muted">Pilih saham di daftar untuk melihat detail.</p>}
      </aside>
    </div>
  );
}
