# =============================================================================
# src/dashboard/app.py — IDX Screener ADMD
# Fix: hasil tidak hilang saat apapun berubah di sidebar
# =============================================================================

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import date
import pandas as pd
import streamlit as st

import config as cfg
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

SIGNAL_COLOR = {"Akumulasi":"#22c55e","Distribusi":"#f97316","Mark Up":"#3b82f6","Mark Down":"#ef4444"}
SIGNAL_EMOJI = {"Akumulasi":"🟢","Distribusi":"🟠","Mark Up":"🔵","Mark Down":"🔴"}

# =============================================================================
# SESSION STATE — inisialisasi SEMUA key di sini, SEKALI
# =============================================================================

for k, v in {
    "results_df"      : pd.DataFrame(),
    "ohlcv_cache"     : {},
    "foreign_df"      : pd.DataFrame(),
    "has_foreign"     : False,
    "screening_done"  : False,
    "selected_ticker" : None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =============================================================================
# SIDEBAR
# =============================================================================

with st.sidebar:
    st.title("⚙️ Kontrol")
    st.markdown("---")

    # Universe — simpan ke session state, TIDAK trigger re-screening otomatis
    universe_opt = st.selectbox(
        "Universe Saham",
        ["LQ45","IDX High Dividend 20","Custom"],
        key="universe_select",
    )
    if universe_opt == "LQ45":
        tickers = cfg.LQ45
    elif universe_opt == "IDX High Dividend 20":
        tickers = cfg.IDXHIDIV20
    else:
        raw = st.text_area("Ticker (pisah koma)", "BBCA,BBRI,TLKM,ASII,BMRI", height=80)
        tickers = [t.strip().upper() for t in raw.replace("\n",",").split(",") if t.strip()]
    st.caption(f"📋 {len(tickers)} saham")

    st.markdown("---")

    # Data asing
    st.subheader("📂 Data Asing (Opsional)")
    uploaded_file = st.file_uploader("Upload CSV foreign flow", type=["csv"])
    if uploaded_file is not None:
        try:
            p = cfg.DATA_RAW_DIR / f"foreign_flow_{date.today().strftime('%Y%m%d')}.csv"
            p.write_bytes(uploaded_file.getvalue())
            from src.data_fetcher.idx_foreign_parser import load_foreign_flow
            ff = load_foreign_flow(tickers, days=5)
            if not ff.empty:
                st.session_state.foreign_df  = ff
                st.session_state.has_foreign = True
                st.success(f"✅ {ff['ticker'].nunique()} saham dimuat")
            else:
                st.warning("⚠ Tidak terbaca — cek format")
        except Exception as e:
            st.error(f"Error: {e}")

    if not st.session_state.has_foreign:
        from src.data_fetcher.idx_foreign_parser import _get_sorted_files, load_foreign_flow
        if _get_sorted_files():
            try:
                ff = load_foreign_flow(tickers, days=5)
                if not ff.empty:
                    st.session_state.foreign_df  = ff
                    st.session_state.has_foreign = True
            except Exception:
                pass

    st.info("✅ Foreign flow aktif" if st.session_state.has_foreign else "❌ Mode harga & volume")

    st.markdown("---")

    # Filter
    show_signals = st.multiselect(
        "Tampilkan sinyal",
        ["Akumulasi","Distribusi","Mark Up","Mark Down"],
        default=["Akumulasi","Distribusi","Mark Up","Mark Down"],
        key="show_signals",
    )
    min_strength = st.slider("Min. Strength", 0, 100, 0, 5, key="min_strength")

    st.markdown("---")
    use_cache  = st.toggle("Gunakan cache OHLCV", value=True, key="use_cache")

    # Tombol screening — SATU-SATUNYA trigger yang menjalankan ulang screening
    run_button = st.button("🔍 Jalankan Screening",
                           use_container_width=True, type="primary", key="run_btn")
    st.markdown("---")
    st.caption("📡 Harga: Yahoo Finance")


# =============================================================================
# JALANKAN SCREENING — hanya saat tombol diklik
# Semua hasil disimpan ke session state dan TIDAK berubah sampai tombol diklik lagi
# =============================================================================

if run_button:
    with st.spinner("⏳ Mengambil data & mendeteksi sinyal..."):
        try:
            from src.data_fetcher.yfinance_fetcher import fetch_ohlcv
            from src.signals import accumulation, distribution, markup, markdown

            ohlcv = fetch_ohlcv(list(tickers), use_cache=use_cache)
            ff    = st.session_state.foreign_df

            FN_MAP = {
                "Akumulasi" : accumulation.detect,
                "Distribusi": distribution.detect,
                "Mark Up"   : markup.detect,
                "Mark Down" : markdown.detect,
            }

            parts = []
            for name, fn in FN_MAP.items():
                r = fn(ohlcv, ff)
                if not r.empty:
                    parts.append(r)

            combined = pd.concat(parts, ignore_index=True) \
                         .sort_values(["signal","strength"], ascending=[True,False]) \
                         .reset_index(drop=True) if parts else pd.DataFrame()

            # Simpan ke session state
            st.session_state.ohlcv_cache    = ohlcv
            st.session_state.results_df     = combined
            st.session_state.screening_done = True

            n    = len(combined)
            mode = "lengkap" if st.session_state.has_foreign else "harga+volume"
            st.success(f"✅ Selesai — **{n} sinyal** dari {len(ohlcv)} saham (mode: {mode}).")

        except Exception as e:
            st.error(f"❌ Error: {e}")
            st.exception(e)


# =============================================================================
# MAIN CONTENT
# Selalu render berdasarkan session state — TIDAK peduli apa yang berubah di sidebar
# =============================================================================

st.title("📊 IDX Screener — ADMD")
st.caption("Akumulasi · Distribusi · Mark Up · Mark Down")

if st.session_state.has_foreign:
    st.success("✅ **Mode lengkap** — harga, volume & foreign flow.")
else:
    st.warning("⚠️ **Mode harga & volume** — upload CSV asing di sidebar untuk hasil lebih akurat.")

st.markdown("---")

# ── Belum pernah screening ────────────────────────────────────────────────────
if not st.session_state.screening_done:
    st.info("👈 Pilih universe & klik **Jalankan Screening** di sidebar untuk memulai.")
    with st.expander("ℹ️ Cara kerja 4 sinyal ADMD", expanded=True):
        c1, c2 = st.columns(2)
        c1.markdown("""
**🟢 Akumulasi** — bandar kumpulkan diam-diam
- Net buy asing ≥ Rp 200M (5h) *(jika ada data asing)*
- Harga naik pelan –1% s/d +5%
- Volume tidak meledak

**🔵 Mark Up** — fase pompa
- Volume ≥ 1.5× rata-rata 20 hari
- Harga +3% dalam 1 hari ATAU breakout high 5h
""")
        c2.markdown("""
**🟠 Distribusi** — bandar buang ke ritel
- Net sell asing ≥ Rp 150M (5h) *(jika ada data asing)*
- Harga stagnan –10% s/d +2%
- Volume masih tinggi (ritel aktif beli)

**🔴 Mark Down** — fase dump, hindari
- Harga turun ≥ 5% dalam 3 hari
- Volume tinggi = konfirmasi tekanan jual
""")

# ── Sudah ada hasil — tampilkan SELALU dari session state ─────────────────────
else:
    df          = st.session_state.results_df
    ohlcv_cache = st.session_state.ohlcv_cache

    if df.empty:
        st.info("Tidak ada sinyal ditemukan. Coba ubah filter atau jalankan ulang.")

    else:
        # Metrik
        cols = st.columns(4)
        for i, (sig, emoji) in enumerate(SIGNAL_EMOJI.items()):
            cols[i].metric(f"{emoji} {sig}", f"{len(df[df['signal']==sig])} saham")

        st.markdown("---")

        tab1, tab2, tab3 = st.tabs(["📋 Tabel Sinyal","🔍 Detail Saham","📂 Export Data"])

        # ── TAB 1: TABEL ─────────────────────────────────────────────────────
        with tab1:
            # Filter show_signals dari sidebar
            filtered = df[df["signal"].isin(show_signals)].copy() if show_signals else df.copy()
            if min_strength > 0:
                filtered = filtered[filtered["strength"] >= min_strength]

            if filtered.empty:
                st.info("Tidak ada sinyal sesuai filter.")
            else:
                no_foreign = "data_asing" in filtered.columns and not filtered["data_asing"].any()
                if no_foreign:
                    st.info("⚠️ Mode harga & volume — strength maks 70 untuk Akumulasi/Distribusi.")

                for signal in ["Akumulasi","Distribusi","Mark Up","Mark Down"]:
                    if signal not in show_signals:
                        continue
                    subset = filtered[filtered["signal"] == signal].copy()
                    if subset.empty:
                        continue

                    st.markdown(
                        f'<h3 style="color:{SIGNAL_COLOR[signal]};margin-top:1.5rem">'
                        f'{SIGNAL_EMOJI[signal]} {signal} '
                        f'<span style="font-size:14px;color:#94a3b8">({len(subset)} saham)</span>'
                        f'</h3>', unsafe_allow_html=True,
                    )

                    col_map = {
                        "ticker":"Ticker","close":"Harga","strength":"Str",
                        "change_5d":"Δ5h (%)","vol_ratio":"Vol Ratio","note":"Catatan",
                    }
                    if st.session_state.has_foreign: col_map["net_5d"]    = "Net Asing 5h"
                    if signal == "Mark Up":          col_map["return_1d"] = "Return 1h (%)"
                    if signal == "Mark Down":        col_map["change_3d"] = "Δ3h (%)"

                    avail = {k:v for k,v in col_map.items() if k in subset.columns}
                    show  = subset[list(avail)].rename(columns=avail).copy()

                    if "Harga"        in show: show["Harga"]        = show["Harga"].apply(lambda x: f"Rp {x:,.0f}")
                    if "Net Asing 5h" in show: show["Net Asing 5h"] = show["Net Asing 5h"].apply(lambda x: f"Rp {x/1e9:+.1f}M" if pd.notna(x) else "—")
                    if "Str"          in show: show["Str"]          = show["Str"].apply(lambda x: f"{x:.1f}")

                    st.dataframe(show, use_container_width=True, hide_index=True)

        # ── TAB 2: DETAIL ────────────────────────────────────────────────────
        with tab2:
            all_tickers = sorted(df["ticker"].unique())

            # Jaga pilihan saham agar tidak reset
            if st.session_state.selected_ticker not in all_tickers:
                st.session_state.selected_ticker = all_tickers[0]

            selected = st.selectbox(
                "Pilih saham",
                all_tickers,
                index=all_tickers.index(st.session_state.selected_ticker),
                key="ticker_select",
            )
            st.session_state.selected_ticker = selected

            row   = df[df["ticker"] == selected].iloc[0]
            color = SIGNAL_COLOR.get(row["signal"], "#64748b")
            emoji = SIGNAL_EMOJI.get(row["signal"], "⚪")

            st.markdown(
                f'<h2>{selected}&nbsp;'
                f'<span style="background:{color};color:white;'
                f'padding:3px 16px;border-radius:14px;font-size:16px">'
                f'{emoji} {row["signal"]}</span></h2>',
                unsafe_allow_html=True,
            )

            if "data_asing" in row and not row["data_asing"] \
                    and row["signal"] in ["Akumulasi","Distribusi"]:
                st.warning("⚠️ Tanpa konfirmasi data asing — cek RTI/Stockbit sebelum keputusan.")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Harga",    f"Rp {row['close']:,.0f}")
            m2.metric("Strength", f"{row['strength']:.1f}/100")
            if pd.notna(row.get("change_5d")): m3.metric("Δ 5 Hari",     f"{row['change_5d']:+.2f}%")
            if pd.notna(row.get("net_5d")):    m4.metric("Net Asing 5h", f"Rp {row['net_5d']/1e9:+.1f}M")

            st.progress(int(row["strength"]), text=f"Strength: {row['strength']:.1f}/100")
            if row.get("note"):
                st.info(f"📌 {row['note']}")

            if selected in ohlcv_cache:
                st.markdown("#### Chart Harga & Volume")
                render_ohlcv_chart(selected, ohlcv_cache[selected])
            else:
                st.info("Chart tidak tersedia — jalankan screening ulang.")

            foreign = st.session_state.foreign_df
            if not foreign.empty and selected in foreign["ticker"].values:
                st.markdown("#### Net Buy/Sell Asing Harian")
                render_foreign_flow_chart(selected, foreign)

        # ── TAB 3: EXPORT ────────────────────────────────────────────────────
        with tab3:
            st.subheader("Export Hasil Screening")
            st.dataframe(df, use_container_width=True)

            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "⬇️ Download Hasil CSV",
                    data=df.to_csv(index=False).encode("utf-8"),
                    file_name="idx_screener_hasil.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with c2:
                if not st.session_state.foreign_df.empty:
                    st.download_button(
                        "⬇️ Download Foreign Flow CSV",
                        data=st.session_state.foreign_df.to_csv(index=False).encode("utf-8"),
                        file_name="foreign_flow_data.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

            with st.expander("📋 Format CSV data asing"):
                st.markdown("""
| StockCode | ForeignBuy | ForeignSell | NetBuySell |
|-----------|-----------|------------|-----------|
| BBCA | 350000000000 | 100000000000 | 250000000000 |

Nilai dalam **Rupiah**. Nama kolom fleksibel.
""")
