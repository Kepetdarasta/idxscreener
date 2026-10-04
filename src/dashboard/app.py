# =============================================================================
# src/dashboard/app.py — IDX Screener (V2 — baca dari Neon PostgreSQL)
#
# Dua mode TERPISAH (pilih di sidebar):
#   🏛️ Wyckoff (ADMD) — jangka panjang, berbasis fase aktif
#   📈 Swing (MA & MACD cross) — lihat swing_view.py
#
# Dashboard ini TIDAK menjalankan screener secara live. Semua data (OHLCV,
# foreign flow, sinyal, fase) berasal dari database yang diisi oleh
# etl_pipeline.py (dijalankan otomatis tiap hari via GitHub Actions).
#
# Cara jalankan:
#   streamlit run src/dashboard/app.py
#
# Butuh DATABASE_URL di .env (sama seperti etl_pipeline.py).
# =============================================================================

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

import config as cfg
from src.dashboard import db
from src.dashboard.components import render_ohlcv_chart, render_foreign_flow_chart, render_phase_timeline_chart

st.set_page_config(
    page_title=cfg.DASHBOARD_TITLE,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
div[data-testid="stMetric"] {
    background:#f8fafc;border-radius:8px;
    padding:12px;border:1px solid #e2e8f0;
}
</style>
""", unsafe_allow_html=True)

SIGNAL_COLOR = {"Akumulasi": "#22c55e", "Distribusi": "#f97316", "Mark Up": "#3b82f6", "Mark Down": "#ef4444"}
SIGNAL_EMOJI = {"Akumulasi": "🟢", "Distribusi": "🟠", "Mark Up": "🔵", "Mark Down": "🔴"}
PHASE_TO_SIGNAL = {
    "accumulation": "Akumulasi",
    "distribution": "Distribusi",
    "markup": "Mark Up",
    "markdown": "Mark Down",
}


CYCLE = ["Akumulasi", "Mark Up", "Distribusi", "Mark Down"]

# =============================================================================
# ROUTER MODE — Wyckoff vs Swing (tidak saling berbagi data/filter)
# =============================================================================

with st.sidebar:
    mode = st.radio(
        "Mode analisis",
        ["🏛️ Wyckoff — jangka panjang", "📈 Swing — MA & MACD cross"],
        key="mode_analisis",
    )
    st.markdown("---")

if mode.startswith("📈"):
    from src.dashboard.swing_view import render_swing
    render_swing()
    st.stop()

# =============================================================================
# MODE WYCKOFF — LOAD DATA (cache 5 menit di db.py)
# =============================================================================

try:
    df_latest = db.get_latest_screening()   # sinyal HARI INI saja
    df_phase = db.get_active_phases()       # fase yang SEDANG BERJALAN
except Exception as e:
    st.error(
        "❌ Gagal konek ke database. Cek DATABASE_URL di file .env.\n\n"
        f"Detail error: {e}"
    )
    st.stop()

if df_phase.empty:
    st.warning(
        "⚠️ Belum ada fase aktif di database. "
        "Jalankan `python etl_pipeline.py` dulu untuk mengisi data."
    )
    st.stop()

latest_date = df_latest["screen_date"].iloc[0] if not df_latest.empty else "—"

# Satu tabel gabungan: fase aktif (sumber utama) + penanda sinyal hari ini.
# Dengan ini tab Screening dan Timeline Fase memakai definisi yang sama.
view_all = df_phase.copy()
if "sector" not in view_all.columns:
    view_all["sector"] = None
view_all["signal_name"] = view_all["phase"].map(PHASE_TO_SIGNAL).fillna(view_all["phase"])
view_all["price_change_pct"] = (
    (view_all["current_price"] - view_all["price_at_start"]) / view_all["price_at_start"] * 100
).round(2)

if df_latest.empty:
    view_all["signal_today"] = None
    view_all["signal_score"] = None
else:
    view_all = view_all.merge(
        df_latest[["stock_code", "signal_type", "signal_score"]].rename(columns={"signal_type": "signal_today"}),
        on="stock_code", how="left",
    )
view_all["konfirmasi"] = (view_all["signal_today"] == view_all["signal_name"]).map(
    {True: "✅ hari ini", False: "—"}
)

# =============================================================================
# SIDEBAR (WYCKOFF)
# =============================================================================

with st.sidebar:
    st.title("⚙️ Kontrol Wyckoff")
    st.markdown("---")

    st.caption(f"📅 Sinyal terbaru: **{latest_date}**")

    try:
        last_run = db.get_last_etl_run()
        if not last_run.empty:
            r = last_run.iloc[0]
            status_emoji = "✅" if r["status"] == "success" else "⚠️"
            st.caption(f"{status_emoji} ETL terakhir: {r['finished_at']}")
    except Exception:
        pass

    st.markdown("---")

    sector_opt = st.multiselect(
        "Sektor",
        sorted(view_all["sector"].dropna().unique().tolist()),
        default=[],
        help="Kosongkan untuk tampilkan semua sektor",
    )
    show_signals = st.multiselect("Tampilkan fase", CYCLE, default=CYCLE)
    only_today = st.checkbox("Hanya yang terkonfirmasi sinyal hari ini", value=False)
    min_score = st.slider("Min. Signal Score (sinyal hari ini)", 0, 100, 0, 5)

    st.markdown("---")
    st.caption("📡 Sumber data: Neon PostgreSQL (hasil ETL harian)")

filtered = view_all.copy()
if sector_opt:
    filtered = filtered[filtered["sector"].isin(sector_opt)]
if show_signals:
    filtered = filtered[filtered["signal_name"].isin(show_signals)]
if only_today:
    filtered = filtered[filtered["konfirmasi"] != "—"]
if min_score > 0:
    filtered = filtered[filtered["signal_score"] >= min_score]

# =============================================================================
# HEADER
# =============================================================================

st.title("📊 IDX Screener — Wyckoff (ADMD)")
st.caption(f"Akumulasi · Mark Up · Distribusi · Mark Down — jangka panjang · sinyal terbaru {latest_date}")
st.markdown("---")

cols = st.columns(4)
for i, sig in enumerate(CYCLE):
    sub = view_all[view_all["signal_name"] == sig]
    n_today = int((sub["konfirmasi"] != "—").sum())
    cols[i].metric(
        f"{SIGNAL_EMOJI[sig]} {sig}", f"{len(sub)} saham",
        delta=f"{n_today} sinyal hari ini", delta_color="off",
    )

st.markdown("---")

tab1, tab3, tab4, tab5 = st.tabs(
    ["📋 Screening Fase", "🔍 Detail Saham", "📂 Export", "ℹ️ Keterangan"]
)

# =============================================================================
# TAB 1 — SCREENING FASE (fase aktif + penanda sinyal hari ini)
# =============================================================================

with tab1:
    st.caption(
        "Menampilkan semua saham yang **sedang berada** di suatu fase. Fase tetap berjalan "
        "walau sinyal harian tidak muncul; kolom *Sinyal Hari Ini* menandai konfirmasi ulang."
    )
    if filtered.empty:
        st.info("Tidak ada saham sesuai filter.")
    else:
        for signal in CYCLE:
            if signal not in show_signals:
                continue
            subset = filtered[filtered["signal_name"] == signal].sort_values(
                ["konfirmasi", "days_in_phase"], ascending=[False, False]
            )
            if subset.empty:
                continue

            st.markdown(
                f'<h3 style="color:{SIGNAL_COLOR[signal]};margin-top:1.5rem">'
                f'{SIGNAL_EMOJI[signal]} {signal} '
                f'<span style="font-size:14px;color:#94a3b8">({len(subset)} saham)</span>'
                f'</h3>', unsafe_allow_html=True,
            )

            show = subset[[
                "stock_code", "stock_name", "sector", "days_in_phase",
                "price_at_start", "current_price", "price_change_pct",
                "konfirmasi", "signal_score",
            ]].rename(columns={
                "stock_code": "Ticker", "stock_name": "Nama", "sector": "Sektor",
                "days_in_phase": "Hari di Fase Ini",
                "price_at_start": "Harga Masuk", "current_price": "Harga Sekarang",
                "price_change_pct": "Δ (%)",
                "konfirmasi": "Sinyal Hari Ini", "signal_score": "Score",
            }).copy()
            show["Harga Masuk"] = show["Harga Masuk"].apply(lambda x: f"Rp {x:,.0f}")
            show["Harga Sekarang"] = show["Harga Sekarang"].apply(
                lambda x: f"Rp {x:,.0f}" if pd.notna(x) else "—"
            )
            st.dataframe(show, use_container_width=True, hide_index=True)

# =============================================================================
# TAB 3 — DETAIL SAHAM
# =============================================================================

with tab3:
    all_tickers = sorted(view_all["stock_code"].unique())
    selected = st.selectbox("Pilih saham", all_tickers, key="detail_ticker")

    row = view_all[view_all["stock_code"] == selected].iloc[0]
    signal = row["signal_name"]
    color = SIGNAL_COLOR.get(signal, "#64748b")
    emoji = SIGNAL_EMOJI.get(signal, "⚪")

    st.markdown(
        f'<h2>{selected}&nbsp;'
        f'<span style="background:{color};color:white;'
        f'padding:3px 16px;border-radius:14px;font-size:16px">'
        f'{emoji} {signal or "—"}</span></h2>',
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Harga", f"Rp {row['current_price']:,.0f}" if pd.notna(row["current_price"]) else "—")
    m2.metric("Hari di Fase Ini", f"{row['days_in_phase']} hari")
    m3.metric("Δ sejak masuk fase", f"{row['price_change_pct']:+.1f}%" if pd.notna(row["price_change_pct"]) else "—")
    m4.metric(
        "Signal Score hari ini",
        f"{row['signal_score']:.0f}/100" if pd.notna(row["signal_score"]) else "Tidak ada sinyal hari ini",
    )

    st.markdown("#### Chart Harga & Volume")
    ohlcv = db.get_ohlcv(selected, days=90)
    if not ohlcv.empty:
        render_ohlcv_chart(selected, ohlcv)
    else:
        st.info("Belum ada data OHLCV historis untuk saham ini.")

    st.markdown("#### Net Buy/Sell Asing Harian")
    ff = db.get_foreign_flow(selected, days=30)
    if not ff.empty:
        render_foreign_flow_chart(selected, ff)
    else:
        st.info("Belum ada data foreign flow untuk saham ini.")

    st.markdown("#### Timeline Pergerakan Fase")
    phase_hist = db.get_phase_history(selected)
    if not phase_hist.empty:
        earliest_phase = pd.to_datetime(phase_hist["phase_start"].min())
        days_needed = (pd.Timestamp.today() - earliest_phase).days + 30
        price_for_phase = db.get_ohlcv(selected, days=max(days_needed, 90))
        render_phase_timeline_chart(selected, price_for_phase, phase_hist)

    st.markdown("#### Riwayat Fase")
    if not phase_hist.empty:
        show_hist = phase_hist.copy()
        show_hist["phase"] = show_hist["phase"].map(PHASE_TO_SIGNAL).fillna(show_hist["phase"])
        show_hist = show_hist.rename(columns={
            "phase": "Fase", "phase_start": "Mulai", "phase_end": "Selesai",
            "duration_days": "Durasi (hari)", "price_at_start": "Harga Awal",
            "price_at_end": "Harga Akhir", "price_change_pct": "Δ (%)",
            "ff_net_cumulative": "Net Asing Kumulatif (lot)",
        })
        st.dataframe(show_hist, use_container_width=True, hide_index=True)
    else:
        st.info("Belum ada riwayat fase untuk saham ini.")

# =============================================================================
# TAB 4 — EXPORT
# =============================================================================

with tab4:
    st.subheader("Export Screening Fase")
    export_df = view_all.drop(columns=["signal_name"], errors="ignore")
    st.dataframe(export_df, use_container_width=True)
    st.download_button(
        "⬇️ Download Hasil CSV",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name=f"idx_wyckoff_{latest_date}.csv",
        mime="text/csv",
        use_container_width=True,
    )

# =============================================================================
# TAB 5 — EXPLAINER / KETERANGAN
# =============================================================================

def _rp_miliar(nominal: int) -> str:
    """Format angka rupiah besar jadi 'Rp XXX miliar' biar gampang dibaca."""
    return f"Rp {nominal / 1_000_000_000:,.0f} miliar".replace(",", ".")


with tab5:
    st.subheader("Apa itu Siklus ADMD?")
    st.markdown(
        """
Setiap saham secara umum bergerak melalui 4 fase berulang, mengikuti prinsip
**Wyckoff Method** — teori yang menjelaskan bagaimana pemodal besar ("smart money")
mengumpulkan lalu melepas posisi mereka secara bertahap, tanpa membuat harga
bergerak drastis di awal.

Screener ini mendeteksi 4 fase tersebut secara otomatis setiap hari berdasarkan
kombinasi **pergerakan harga**, **volume**, dan **arus transaksi asing (foreign flow)**.

Sebuah fase dianggap **berjalan** sampai screener mendeteksi fase *lain* untuk saham tersebut — fase tidak berakhir hanya karena sinyal harian tidak muncul. Kolom **Sinyal Hari Ini** pada tab Screening menandai saham yang fasenya terkonfirmasi ulang oleh sinyal hari itu.

Metode swing (MA cross & MACD cross) ada di mode terpisah pada sidebar.
"""
    )

    st.markdown("---")

    # ---------------------------------------------------------------
    # AKUMULASI
    # ---------------------------------------------------------------
    with st.expander("🟢 Akumulasi (Accumulation)", expanded=True):
        st.markdown(
            f"""
**Apa itu:** Fase di mana pemodal besar diam-diam mulai mengoleksi saham dalam
jumlah besar, biasanya setelah harga sudah lama turun atau bergerak sideways.
Harga sengaja dijaga agar tidak naik terlalu cepat, supaya tidak menarik
perhatian ritel dan harga beli tetap murah.

**Kriteria yang dipakai sistem:**
- Net **beli** asing minimal **{_rp_miliar(cfg.ACCUM_NET_BUY_MIN)}** dalam **{cfg.ACCUM_WINDOW_DAYS} hari** terakhir
- Perubahan harga selama periode tersebut antara **{cfg.ACCUM_PRICE_CHANGE_MIN:.0%}** sampai **+{cfg.ACCUM_PRICE_CHANGE_MAX:.0%}** (harga stagnan/naik pelan, bukan sudah naik tajam)

*Catatan: kalau data foreign flow tidak tersedia hari itu, sinyal Akumulasi tetap bisa muncul dari kriteria harga+volume saja, tapi skor kekuatannya dibatasi maksimal 70.*
"""
        )

    # ---------------------------------------------------------------
    # MARK UP
    # ---------------------------------------------------------------
    with st.expander("🔵 Mark Up"):
        st.markdown(
            f"""
**Apa itu:** Fase kenaikan harga yang sebenarnya — setelah proses akumulasi
selesai, harga mulai bergerak naik dengan cepat dan diikuti oleh minat beli
yang meluas (bukan cuma pemodal besar lagi).

**Kriteria yang dipakai sistem:**
- Volume transaksi minimal **{cfg.MARKUP_VOLUME_RATIO_MIN}x** rata-rata volume **{cfg.MARKUP_VOLUME_AVG_WINDOW} hari** terakhir
- Harga naik minimal **{cfg.MARKUP_PRICE_BREAKOUT:.0%}** dalam 1 hari, **atau** berhasil menembus (breakout) level tertinggi **{cfg.MARKUP_BREAKOUT_WINDOW} hari** terakhir
"""
        )

    # ---------------------------------------------------------------
    # DISTRIBUSI
    # ---------------------------------------------------------------
    with st.expander("🟠 Distribusi (Distribution)"):
        st.markdown(
            f"""
**Apa itu:** Kebalikan dari akumulasi — pemodal besar mulai melepas
(menjual) posisi mereka secara bertahap, biasanya setelah harga sudah naik
signifikan. Harga terlihat masih stabil atau bahkan sedikit naik karena
pembeli ritel yang justru dominan membeli, padahal pemain besar sedang keluar.

**Kriteria yang dipakai sistem:**
- Net **jual** asing minimal **{_rp_miliar(abs(cfg.DIST_NET_SELL_MIN))}** dalam **{cfg.DIST_WINDOW_DAYS} hari** terakhir
- Perubahan harga selama periode tersebut antara **{cfg.DIST_PRICE_CHANGE_MIN:.0%}** sampai **+{cfg.DIST_PRICE_CHANGE_MAX:.0%}** (harga stagnan atau mulai turun, belum jatuh tajam)

*Catatan: sama seperti Akumulasi, tanpa data foreign flow skor kekuatan dibatasi maksimal 70.*
"""
        )

    # ---------------------------------------------------------------
    # MARK DOWN
    # ---------------------------------------------------------------
    with st.expander("🔴 Mark Down"):
        st.markdown(
            f"""
**Apa itu:** Fase penurunan harga yang tajam — kebalikan dari Mark Up.
Terjadi setelah distribusi selesai, saat pemodal besar sudah keluar dan
tekanan jual mendominasi pasar.

**Kriteria yang dipakai sistem:**
- Harga turun minimal **{cfg.MARKDOWN_PRICE_DROP_MIN:.0%}** dalam **{cfg.MARKDOWN_PRICE_WINDOW} hari** terakhir
- Net jual asing minimal **{_rp_miliar(abs(cfg.MARKDOWN_NET_SELL_MIN))}** (konfirmasi tekanan jual masih berlanjut)
- Volume di atas **{cfg.MARKDOWN_VOLUME_RATIO_MIN}x** rata-rata (konfirmasi partisipasi pasar, bukan penurunan sepi volume)
"""
        )

    st.markdown("---")
    st.caption(
        "Semua threshold di atas diambil langsung dari config.py dan bisa disesuaikan "
        "di sana kapan saja — halaman ini akan otomatis mengikuti."
    )
