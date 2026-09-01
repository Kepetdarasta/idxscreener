# =============================================================================
# src/dashboard/app.py — IDX Screener ADMD (V2 — baca dari Neon PostgreSQL)
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
from src.dashboard.components import render_ohlcv_chart, render_foreign_flow_chart

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

# =============================================================================
# LOAD DATA — sekali di awal, sudah di-cache oleh db.py (ttl 5 menit)
# =============================================================================

try:
    df_latest = db.get_latest_screening()
except Exception as e:
    st.error(
        "❌ Gagal konek ke database. Cek DATABASE_URL di file .env.\n\n"
        f"Detail error: {e}"
    )
    st.stop()

if df_latest.empty:
    st.warning(
        "⚠️ Belum ada data screening di database. "
        "Jalankan `python etl_pipeline.py` dulu untuk mengisi data."
    )
    st.stop()

latest_date = df_latest["screen_date"].iloc[0]

# =============================================================================
# SIDEBAR
# =============================================================================

with st.sidebar:
    st.title("⚙️ Kontrol")
    st.markdown("---")

    st.caption(f"📅 Data terbaru: **{latest_date}**")

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
        sorted(df_latest["sector"].dropna().unique().tolist()),
        default=[],
        help="Kosongkan untuk tampilkan semua sektor",
    )

    show_signals = st.multiselect(
        "Tampilkan sinyal",
        ["Akumulasi", "Distribusi", "Mark Up", "Mark Down"],
        default=["Akumulasi", "Distribusi", "Mark Up", "Mark Down"],
    )

    min_score = st.slider("Min. Signal Score", 0, 100, 0, 5)

    st.markdown("---")
    st.caption("📡 Sumber data: Neon PostgreSQL (hasil ETL harian)")


# Terapkan filter sidebar ke df_latest
filtered = df_latest.copy()
if sector_opt:
    filtered = filtered[filtered["sector"].isin(sector_opt)]
if show_signals:
    filtered = filtered[filtered["signal_type"].isin(show_signals)]
filtered = filtered[filtered["signal_score"] >= min_score]

# =============================================================================
# HEADER
# =============================================================================

st.title("📊 IDX Screener — ADMD")
st.caption(f"Akumulasi · Distribusi · Mark Up · Mark Down — data per {latest_date}")
st.markdown("---")

cols = st.columns(4)
for i, (sig, emoji) in enumerate(SIGNAL_EMOJI.items()):
    cols[i].metric(f"{emoji} {sig}", f"{len(df_latest[df_latest['signal_type'] == sig])} saham")

st.markdown("---")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📋 Screening Terbaru", "⏳ Fase Aktif", "🔍 Detail Saham", "📂 Export", "ℹ️ Keterangan"]
)

# =============================================================================
# TAB 1 — SCREENING TERBARU
# =============================================================================

with tab1:
    if filtered.empty:
        st.info("Tidak ada saham sesuai filter.")
    else:
        for signal in ["Akumulasi", "Distribusi", "Mark Up", "Mark Down"]:
            if signal not in show_signals:
                continue
            subset = filtered[filtered["signal_type"] == signal].copy()
            if subset.empty:
                continue

            st.markdown(
                f'<h3 style="color:{SIGNAL_COLOR[signal]};margin-top:1.5rem">'
                f'{SIGNAL_EMOJI[signal]} {signal} '
                f'<span style="font-size:14px;color:#94a3b8">({len(subset)} saham)</span>'
                f'</h3>', unsafe_allow_html=True,
            )

            show = subset[[
                "stock_code", "stock_name", "sector", "close_price",
                "signal_score", "ff_net_5d", "ff_net_20d",
            ]].rename(columns={
                "stock_code": "Ticker", "stock_name": "Nama", "sector": "Sektor",
                "close_price": "Harga", "signal_score": "Score",
                "ff_net_5d": "Net Asing 5h (lot)", "ff_net_20d": "Net Asing 20h (lot)",
            }).copy()
            show["Harga"] = show["Harga"].apply(lambda x: f"Rp {x:,.0f}")

            st.dataframe(show, use_container_width=True, hide_index=True)

# =============================================================================
# TAB 2 — FASE AKTIF
# =============================================================================

with tab2:
    try:
        df_phase = db.get_active_phases()
    except Exception as e:
        st.error(f"Gagal ambil data fase aktif: {e}")
        df_phase = pd.DataFrame()

    if df_phase.empty:
        st.info("Belum ada data fase aktif.")
    else:
        df_phase = df_phase.copy()
        df_phase["signal_name"] = df_phase["phase"].map(PHASE_TO_SIGNAL).fillna(df_phase["phase"])
        df_phase["price_change_pct"] = (
            (df_phase["current_price"] - df_phase["price_at_start"]) / df_phase["price_at_start"] * 100
        ).round(2)

        for phase_key, signal in PHASE_TO_SIGNAL.items():
            subset = df_phase[df_phase["phase"] == phase_key].sort_values("days_in_phase", ascending=False)
            if subset.empty:
                continue

            st.markdown(
                f'<h3 style="color:{SIGNAL_COLOR[signal]};margin-top:1.5rem">'
                f'{SIGNAL_EMOJI[signal]} {signal} '
                f'<span style="font-size:14px;color:#94a3b8">({len(subset)} saham)</span>'
                f'</h3>', unsafe_allow_html=True,
            )

            show = subset[[
                "stock_code", "stock_name", "days_in_phase",
                "price_at_start", "current_price", "price_change_pct",
            ]].rename(columns={
                "stock_code": "Ticker", "stock_name": "Nama",
                "days_in_phase": "Hari di Fase Ini",
                "price_at_start": "Harga Masuk", "current_price": "Harga Sekarang",
                "price_change_pct": "Δ (%)",
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
    all_tickers = sorted(df_latest["stock_code"].unique())
    selected = st.selectbox("Pilih saham", all_tickers, key="detail_ticker")

    row = df_latest[df_latest["stock_code"] == selected].iloc[0]
    signal = row["signal_type"]
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
    m1.metric("Harga", f"Rp {row['close_price']:,.0f}")
    m2.metric("Signal Score", f"{row['signal_score']}/100" if pd.notna(row["signal_score"]) else "—")
    if pd.notna(row.get("ff_net_5d")):
        m3.metric("Net Asing 5h", f"{row['ff_net_5d']:,.0f} lot")
    if pd.notna(row.get("ff_net_20d")):
        m4.metric("Net Asing 20h", f"{row['ff_net_20d']:,.0f} lot")

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

    st.markdown("#### Riwayat Fase")
    phase_hist = db.get_phase_history(selected)
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
    st.subheader("Export Hasil Screening")
    st.dataframe(df_latest, use_container_width=True)
    st.download_button(
        "⬇️ Download Hasil CSV",
        data=df_latest.to_csv(index=False).encode("utf-8"),
        file_name=f"idx_screener_{latest_date}.csv",
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
