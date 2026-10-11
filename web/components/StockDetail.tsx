"use client";
import Link from "next/link";
import PhaseChart from "./PhaseChart";
import StarButton from "./StarButton";
import { summarize } from "@/lib/analysis";
import { idr, pct } from "@/lib/format";
import { phaseOf } from "@/lib/phases";
import type { StockDetailData } from "@/lib/types";

export default function StockDetail({ data, full = false }: { data: StockDetailData; full?: boolean }) {
  const { passed, total } = summarize(data.checklist);
  const up = (data.last.chg ?? 0) >= 0;
  const px = data.last.close;
  const lv = data.levels;
  const ph = data.signal ? phaseOf(data.signal.phase) : null;

  return (
    <section className="detail">
      <header className="d-head">
        <div>
          <h2>{data.code}</h2>
          <p className="muted">{data.name}{data.sector ? ` · ${data.sector}` : ""}</p>
        </div>
        <div className="d-price">
          <b>{idr(px)}</b>
          <span className={up ? "pos" : "neg"}>{pct(data.last.chg)}</span>
          <StarButton code={data.code} />
        </div>
      </header>

      <p className="d-signal">
        {ph && data.signal ? (
          <><i className="dot" style={{ background: ph.color }} />{ph.label} · skor {data.signal.score}</>
        ) : (
          <span className="muted">Tidak ada sinyal pada {data.last.d}</span>
        )}
      </p>

      {lv && (
        <div className="levels">
          <div><small>Resistance 20 hari</small><b>{idr(lv.resistance)}</b><span className="muted">{pct((lv.resistance / px - 1) * 100, 1)} dari harga</span></div>
          <div><small>Support 20 hari</small><b>{idr(lv.support)}</b><span className="muted">{pct((lv.support / px - 1) * 100, 1)} dari harga</span></div>
        </div>
      )}

      <PhaseChart prices={data.prices} bands={data.bands} setup={data.setup} levels={lv} />

      {data.setup && (
        <>
          <h3>Trade setup</h3>
          <div className="scroll">
            <table>
              <thead><tr><th>Entry</th><th>Stop loss</th><th>Target</th><th className="num">Risk : Reward</th></tr></thead>
              <tbody><tr>
                <td>{idr(data.setup.entry)}</td>
                <td>{idr(data.setup.stop)} <span className="neg">({pct((data.setup.stop / data.setup.entry - 1) * 100, 1)})</span></td>
                <td>{idr(data.setup.target)} <span className="pos">({pct((data.setup.target / data.setup.entry - 1) * 100, 1)})</span></td>
                <td className="num">1 : {data.setup.rr.toFixed(2)}</td>
              </tr></tbody>
            </table>
          </div>
        </>
      )}

      {data.checklist.length > 0 && (
        <>
          <h3>Checklist teknikal <span className="muted">{passed} dari {total} terpenuhi</span></h3>
          <ul className="checks">
            {data.checklist.map((c) => (
              <li key={c.label} className={c.ok === true ? "ok" : c.ok === false ? "no" : "na"}>
                <span className="mark" aria-label={c.ok === true ? "terpenuhi" : c.ok === false ? "belum terpenuhi" : "tidak tersedia"}>
                  {c.ok === true ? "✓" : c.ok === false ? "✗" : "–"}
                </span>
                <div><b>{c.label}</b><small>{c.detail}</small></div>
              </li>
            ))}
          </ul>
        </>
      )}

      {full && (
        <>
          <h3>Riwayat fase</h3>
          {data.history.length === 0 ? <p className="muted">Belum ada fase tercatat.</p> : (
            <div className="scroll">
              <table>
                <thead><tr><th>Fase</th><th>Mulai</th><th>Selesai</th><th className="num">Hari</th><th className="num">Harga awal</th><th className="num">Harga akhir</th><th className="num">Perubahan</th></tr></thead>
                <tbody>
                  {data.history.map((p, i) => (
                    <tr key={i}>
                      <td><i className="dot" style={{ background: phaseOf(p.phase).color }} />{phaseOf(p.phase).label}</td>
                      <td>{p.start}</td><td>{p.end ?? "berjalan"}</td>
                      <td className="num">{p.days ?? "–"}</td>
                      <td className="num">{idr(p.priceStart)}</td>
                      <td className="num">{p.priceEnd != null ? idr(p.priceEnd) : "–"}</td>
                      <td className="num">{pct(p.changePct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {!full && <p><Link href={`/stocks/${data.code}`}>Buka halaman lengkap →</Link></p>}
      <p className="muted fine">Dihitung otomatis dari harga dan volume penutupan {data.last.d}. Bukan rekomendasi investasi.</p>
    </section>
  );
}
