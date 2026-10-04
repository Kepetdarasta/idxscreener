# =============================================================================
# src/dashboard/swing_view.py — Mode SWING (MA cross & MACD cross, data harian)
# Terpisah total dari tampilan Wyckoff. Dipanggil dari app.py saat mode = Swing.
# =============================================================================

from datetime import timedelta

import pandas as pd
import streamlit as st

import config as cfg
from src.dashboard import db_swing

SIGNAL_LABEL = {
    "MA_Golden_Cross"   : "MA Golden Cross",
    "MA_Death_Cross"    : "MA Death Cross",
    "MACD_Bullish_Cross": "MACD Bullish Cross",
    "MACD_Bearish_Cross": "MACD Bearish Cross",
}
SIGNAL_COLOR = {
    "MA_Golden_Cross": "#22c55e", "MACD_Bullish_Cross": "#22c55e",
    "MA_Death_Cross" : "#ef4444", "MACD_Bearish_Cross": "#ef4444",
}
SIGNAL_EMOJI = {
    "MA_Golden_Cross": "🟢", "MACD_Bullish_Cross": "🟢",
    "MA_Death_Cross" : "🔴", "MACD_Bearish_Cross": "🔴",
}


def render_swing() -> None:
    # ---- Data ---------------------------------------------------------------
    try:
        df_all = db_swing.get_swing_signals(days=45)
    except Exception as e:
        st.error(
            "❌ Gagal membaca tabel `swing_signals`. Pastikan `schema_v3_swing.sql` "
            f"sudah dijalankan di Neon dan DATABASE_URL benar.\n\nDetail: {e}"
        )
        st.stop()

    if df_all.empty:
        st.warning(
            "⚠️ Belum ada sinyal swing di database. Jalankan `python etl_swing.py` "
            "(atau `--backfill 10`) untuk mengisi data."
        )
        st.stop()

    latest = df_all["signal_date"].max()

    # ---- Sidebar ------------------------------------------------------------
    with st.sidebar:
        st.title("⚙️ Kontrol Swing")
        st.markdown("---")
        st.caption(f"📅 Sinyal terbaru: **{latest}**")

        lookback = st.selectbox(
            "Rentang sinyal",
            [1, 3, 7, 14],
            index=1,
            format_func=lambda d: "Hanya tanggal terbaru" if d == 1 else f"{d} hari kalender terakhir",
            help="Dihitung mundur dari tanggal sinyal terbaru.",
        )
        sector_opt = st.multiselect(
            "Sektor", sorted(df_all["sector"].dropna().unique().tolist()), default=[],
            help="Kosongkan untuk semua sektor", key="swing_sector",
        )
        type_opt = st.multiselect(
            "Jenis sinyal", list(SIGNAL_LABEL), default=list(SIGNAL_LABEL),
            format_func=lambda s: SIGNAL_LABEL[s],
        )
        min_strength = st.slider("Min. Strength (0–10)", 0.0, 10.0, 0.0, 0.5)
        st.markdown("---")
        st.caption("📡 Sumber: tabel swing_signals (ETL harian terpisah dari Wyckoff)")

    view = df_all[df_all["signal_date"] >= latest - timedelta(days=lookback - 1)].copy()
    if sector_opt:
        view = view[view["sector"].isin(sector_opt)]
    if type_opt:
        view = view[view["signal_type"].isin(type_opt)]
    view = view[view["strength"].fillna(0) >= min_strength]

    # ---- Header -------------------------------------------------------------
    st.title("📈 IDX Screener — Swing")
    st.caption("MA Cross · MACD Cross — data harian, terpisah dari metode Wyckoff")
    st.markdown("---")

    cols = st.columns(4)
    for i, sig in enumerate(SIGNAL_LABEL):
        n = len(view[view["signal_type"] == sig])
        cols[i].metric(f"{SIGNAL_EMOJI[sig]} {SIGNAL_LABEL[sig]}", f"{n} saham")
    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["📋 Sinyal", "🎯 Konfluensi MA + MACD", "ℹ️ Keterangan"])

    # ---- Tab Sinyal ---------------------------------------------------------
    with tab1:
        if view.empty:
            st.info("Tidak ada sinyal sesuai filter.")
        for sig in SIGNAL_LABEL:
            sub = view[view["signal_type"] == sig]
            if sub.empty:
                continue
            st.markdown(
                f'<h3 style="color:{SIGNAL_COLOR[sig]};margin-top:1.5rem">'
                f'{SIGNAL_EMOJI[sig]} {SIGNAL_LABEL[sig]} '
                f'<span style="font-size:14px;color:#94a3b8">({len(sub)} saham)</span></h3>',
                unsafe_allow_html=True,
            )
            show = sub[["signal_date", "stock_code", "stock_name", "sector",
                        "close_price", "strength", "note"]].rename(columns={
                "signal_date": "Tanggal", "stock_code": "Ticker", "stock_name": "Nama",
                "sector": "Sektor", "close_price": "Harga", "strength": "Strength", "note": "Catatan",
            }).copy()
            show["Harga"] = show["Harga"].apply(lambda x: f"Rp {x:,.0f}")
            st.dataframe(show, use_container_width=True, hide_index=True)

    # ---- Tab Konfluensi -----------------------------------------------------
    with tab2:
        st.caption(
            "Saham yang kena sinyal **MA cross dan MACD cross searah** dalam rentang terpilih. "
            "Konfirmasi dua indikator mengurangi sinyal palsu, tapi tidak menghilangkannya."
        )
        found = False
        for direction, title, color in (("bullish", "🟢 Bullish", "#22c55e"),
                                        ("bearish", "🔴 Bearish", "#ef4444")):
            sub = view[view["direction"] == direction]
            ma = sub[sub["signal_type"].str.startswith("MA_")].groupby("stock_code")["signal_date"].max()
            mc = sub[sub["signal_type"].str.startswith("MACD_")].groupby("stock_code")["signal_date"].max()
            both = ma.index.intersection(mc.index)
            if len(both) == 0:
                continue
            found = True
            last = sub.sort_values("signal_date").groupby("stock_code").last()
            out = pd.DataFrame({
                "Ticker": both,
                "Nama": last.loc[both, "stock_name"].values,
                "Tgl MA Cross": ma.loc[both].values,
                "Tgl MACD Cross": mc.loc[both].values,
                "Harga": last.loc[both, "close_price"].apply(lambda x: f"Rp {x:,.0f}").values,
            })
            st.markdown(
                f'<h3 style="color:{color};margin-top:1rem">{title} '
                f'<span style="font-size:14px;color:#94a3b8">({len(out)} saham)</span></h3>',
                unsafe_allow_html=True,
            )
            st.dataframe(out, use_container_width=True, hide_index=True)
        if not found:
            st.info("Belum ada saham dengan konfluensi MA + MACD pada rentang ini. Coba lebarkan rentang sinyal.")

    # ---- Tab Keterangan -----------------------------------------------------
    with tab3:
        fast = getattr(cfg, "MA_CROSS_FAST", 5)
        slow = getattr(cfg, "MA_CROSS_SLOW", 20)
        mf, ms, msig = (getattr(cfg, "MACD_FAST", 12), getattr(cfg, "MACD_SLOW", 26),
                        getattr(cfg, "MACD_SIGNAL", 9))
        st.subheader("Mode Swing")
        st.markdown(f"""
Mode ini **terpisah dari Wyckoff**: tidak ada konsep "fase", hanya **kejadian crossover**
pada bar harian terakhir. Wyckoff untuk gambaran jangka panjang; swing untuk entri/exit
jangka pendek-menengah (hari sampai beberapa minggu).

**MA Cross (MA{fast} × MA{slow})**
- 🟢 *Golden Cross*: MA{fast} memotong ke atas MA{slow}
- 🔴 *Death Cross*: MA{fast} memotong ke bawah MA{slow}

**MACD Cross ({mf}, {ms}, {msig})**
- 🟢 *Bullish*: garis MACD memotong ke atas signal line
- 🔴 *Bearish*: garis MACD memotong ke bawah signal line

**Strength (0–10)** adalah skor heuristik dari lebar gap/histogram saat cross — bukan probabilitas
keberhasilan. Sinyal hanya tercatat pada hari crossover terjadi; sinyal lama tidak diulang.

⚠️ Cross adalah indikator yang tertinggal (lagging) dan sering palsu di pasar sideways.
Gunakan bersama level support/resistance dan manajemen risiko (stop loss).
""")
        st.caption("Parameter diambil dari config.py (bagian PARAMETER SWING).")
