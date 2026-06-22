# =============================================================================
# src/dashboard/app.py — Streamlit Dashboard IDX Screener
# Berjalan dengan atau tanpa data foreign flow
# Jalankan: streamlit run src/dashboard/app.py
# =============================================================================

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import date
import pandas as pd
import streamlit as st

import config as cfg
from src.dashboard.components import render_ohlcv_chart, render_foreign_flow_chart

# =============================================================================
# PAGE CONFIG
# =============================================================================

st.set_page_config(
    page_title=cfg.DASHBOARD_TITLE,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
div[data-testid="stMetric"] {
    background: #f8fafc;
    border-radius: 8px;
    padding: 12px;
    border: 1px solid #e2e8f0;
}
</style>
""", unsafe_allow_html=True)

SIGNAL_COLOR = {
    "Akumulasi" : "#22c55e",
    "Distribusi": "#f97316",
    "Mark Up"   : "#3b82f6",
    "Mark Down" : "#ef4444",
}
SIGNAL_EMOJI = {
    "Akumulasi" : "🟢",
    "Distribusi": "🟠",
    "Mark Up"   : "🔵",
    "Mark Down" : "🔴",
}

# =============================================================================
# SESSION STATE — inisialisasi semua key di awal
# =============================================================================

DEFAULTS = {
    "results_df"      : pd.DataFrame(),
    "ohlcv_cache"     : {},
    "foreign_df"      : pd.DataFrame(),
    "has_foreign"     : False,
    "screening_done"  : False,   # ← key baru: flag apakah screening sudah pernah dijalankan
    "last_tickers"    : [],
}
for key, default in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default

# =============================================================================
# SIDEBAR
# =============================================================================

with st.sidebar:
    st.title("⚙️ Kontrol")
    st.markdown("---")

    # ── Universe ──────────────────────────────────────────────────────────────
    universe_opt = st.selectbox(
        "Universe Saham",
        ["LQ45", "IDX High Dividend 20", "Custom"],
    )
    if universe_opt == "LQ45":
        tickers = cfg.LQ45
    elif universe_opt == "IDX High Dividend 20":
        tickers = cfg.IDXHIDIV20
    else:
        raw = st.text_area(
            "Ticker (pisah koma atau enter)",
            value="BBCA, BBRI, TLKM, ASII, BMRI",
            height=100,
        )
        tickers = [t.strip().upper() for t in raw.replace("\n", ",").split(",") if t.strip()]
    st.caption(f"📋 {len(tickers)} saham dalam universe")

    st.markdown("---")

    # ── Data Asing (Opsional) ─────────────────────────────────────────────────
    st.subheader("📂 Data Asing (Opsional)")
    st.caption(
        "Upload CSV net buy/sell asing dari RTI / Stockbit / IDX. "
        "Jika tidak diupload, screener tetap berjalan dengan kriteria harga & volume."
    )

    uploaded_file = st.file_uploader(
        "Upload CSV foreign flow",
        type=["csv"],
        help=(
            "Format kolom yang diterima:\n"
            "StockCode / Ticker, ForeignBuy, ForeignSell, NetBuySell\n\n"
            "Nama file bebas."
        ),
    )

    # Proses upload — hanya jika ada file baru
    if uploaded_file is not None:
        try:
            dated_path = cfg.DATA_RAW_DIR / f"foreign_flow_{date.today().strftime('%Y%m%d')}.csv"
            dated_path.write_bytes(uploaded_file.getvalue())

            from src.data_fetcher.idx_foreign_parser import load_foreign_flow
            foreign_df = load_foreign_flow(tickers, days=5)

            if not foreign_df.empty:
                st.session_state.foreign_df  = foreign_df
                st.session_state.has_foreign = True
                st.success(f"✅ {foreign_df['ticker'].nunique()} saham dimuat")
            else:
                st.warning("⚠ File diupload tapi tidak terbaca — cek format")
        except Exception as e:
            st.error(f"Error upload: {e}")

    # Coba load dari disk jika belum ada di session
    if not st.session_state.has_foreign:
        from src.data_fetcher.idx_foreign_parser import _get_sorted_files, load_foreign_flow
        existing = _get_sorted_files()
        if existing:
            try:
                foreign_df = load_foreign_flow(tickers, days=5)
                if not foreign_df.empty:
                    st.session_state.foreign_df  = foreign_df
                    st.session_state.has_foreign = True
                    st.info(f"📁 File di disk: {existing[-1].name}")
            except Exception:
                pass

    if not st.session_state.has_foreign:
        st.info("❌ Tidak ada — mode harga & volume")

    st.markdown("---")

    # ── Filter ────────────────────────────────────────────────────────────────
    st.subheader("🔧 Filter")
    show_signals = st.multiselect(
        "Tampilkan sinyal",
        ["Akumulasi", "Distribusi", "Mark Up", "Mark Down"],
        default=["Akumulasi", "Distribusi", "Mark Up", "Mark Down"],
    )
    min_strength = st.slider("Min. Strength", 0, 100, 0, 5)

    st.markdown("---")
    use_cache  = st.toggle("Gunakan cache OHLCV", value=True)
    run_button = st.button(
        "🔍 Jalankan Screening",
        use_container_width=True,
        type="primary",
    )
    st.markdown("---")
    st.caption("📡 Harga: Yahoo Finance")
    st.caption("📋 Data asing: Upload manual")


# =============================================================================
# JALANKAN SCREENING — hanya saat tombol diklik
# =============================================================================

if run_button:
    with st.spinner("⏳ Mengambil data & mendeteksi sinyal..."):
        try:
            from src.data_fetcher.yfinance_fetcher import fetch_ohlcv
            from src.signals import accumulation, distribution, markup, markdown

            ohlcv = fetch_ohlcv(tickers, use_cache=use_cache)
            st.session_state.ohlcv_cache  = ohlcv
            st.session_state.last_tickers = tickers

            ff = st.session_state.foreign_df

            FN_MAP = {
                "Akumulasi" : accumulation.detect,
                "Distribusi": distribution.detect,
                "Mark Up"   : markup.detect,
                "Mark Down" : markdown.detect,
            }
            parts = []
            for name in show_signals:
                r = FN_MAP[name](ohlcv, ff)
                if not r.empty:
                    parts.append(r)

            if parts:
                combined = pd.concat(parts, ignore_index=True)
                if min_strength > 0:
                    combined = combined[combined["strength"] >= min_strength]
                st.session_state.results_df = combined.reset_index(drop=True)
            else:
                st.session_state.results_df = pd.DataFrame()

            # ← Set flag bahwa screening sudah pernah dijalankan
            st.session_state.screening_done = True

            n    = len(st.session_state.results_df)
            mode = "lengkap" if st.session_state.has_foreign else "harga+volume"
            st.success(f"✅ Selesai — **{n} sinyal** dari {len(ohlcv)} saham (mode: {mode}).")

        except Exception as e:
            st.error(f"❌ Error: {e}")
            st.exception(e)


# =============================================================================
# HEADER
# =============================================================================

st.title("📊 IDX Screener — ADMD")
st.caption("Akumulasi · Distribusi · Mark Up · Mark Down")

if st.session_state.has_foreign:
    st.success("✅ **Mode lengkap** — data harga, volume, dan foreign flow tersedia.")
else:
    st.warning(
        "⚠️ **Mode harga & volume** — data asing tidak tersedia. "
        "Sinyal Akumulasi & Distribusi berjalan dengan kriteria harga+volume saja "
        "(strength dikap 70). Upload CSV asing di sidebar untuk hasil lebih akurat."
    )

st.markdown("---")


# =============================================================================
# KONTEN — tampilkan panduan jika belum pernah screening
# =============================================================================

# ← Pakai flag screening_done, BUKAN df.empty
# Ini yang mencegah konten hilang saat user ganti selectbox
if not st.session_state.screening_done:
    st.info("👈 Klik **Jalankan Screening** di sidebar untuk memulai.")
    with st.expander("ℹ️ Cara kerja 4 sinyal ADMD", expanded=True):
        c1, c2 = st.columns(2)
        c1.markdown("""
**🟢 Akumulasi** — bandar kumpulkan diam-diam
- Net buy asing ≥ Rp 200M dalam 5 hari *(jika ada data asing)*
- Harga naik pelan –1% s/d +5%
- Volume tidak meledak

**🔵 Mark Up** — fase pompa (berjalan penuh)
- Volume ≥ 1.5× rata-rata 20 hari
- Harga +3% dalam 1 hari, ATAU
- Breakout dari High 5 hari sebelumnya
""")
        c2.markdown("""
**🟠 Distribusi** — bandar buang ke ritel
- Net sell asing ≥ Rp 150M dalam 5 hari *(jika ada data asing)*
- Harga stagnan –10% s/d +2%
- Volume masih tinggi (ritel aktif beli)

**🔴 Mark Down** — fase dump, hindari
- Harga turun ≥ 5% dalam 3 hari
- Net sell asing berlanjut *(jika ada data asing)*
- Volume tinggi = konfirmasi tekanan jual
""")
    st.stop()

# Ambil hasil dari session state — tidak hilang saat re-run
df = st.session_state.results_df

if df.empty and st.session_state.screening_done:
    st.info("Tidak ada sinyal ditemukan dengan filter saat ini. Coba ubah filter atau jalankan ulang.")
    st.stop()


# =============================================================================
# METRIK RINGKASAN
# =============================================================================

cols = st.columns(4)
for i, (sig, emoji) in enumerate(SIGNAL_EMOJI.items()):
    count = len(df[df["signal"] == sig])
    cols[i].metric(f"{emoji} {sig}", f"{count} saham")

st.markdown("---")


# =============================================================================
# TABS
# =============================================================================

tab1, tab2, tab3 = st.tabs(["📋 Tabel Sinyal", "🔍 Detail Saham", "📂 Export Data"])


# ── TAB 1: TABEL ─────────────────────────────────────────────────────────────
with tab1:
    no_foreign_mode = "data_asing" in df.columns and not df["data_asing"].any()
    if no_foreign_mode:
        st.info(
            "⚠️ **Mode harga & volume** — sinyal Akumulasi dan Distribusi berjalan "
            "tanpa konfirmasi data asing. Strength maksimal 70 untuk kedua sinyal ini."
        )

    for signal in ["Akumulasi", "Distribusi", "Mark Up", "Mark Down"]:
        if signal not in show_signals:
            continue
        subset = df[df["signal"] == signal].copy()
        if subset.empty:
            continue

        color = SIGNAL_COLOR[signal]
        emoji = SIGNAL_EMOJI[signal]
        st.markdown(
            f'<h3 style="color:{color};margin-top:1.5rem">'
            f'{emoji} {signal} '
            f'<span style="font-size:14px;color:#94a3b8">({len(subset)} saham)</span>'
            f'</h3>',
            unsafe_allow_html=True,
        )

        col_map = {
            "ticker"   : "Ticker",
            "close"    : "Harga",
            "strength" : "Str",
            "change_5d": "Δ5h (%)",
            "vol_ratio": "Vol Ratio",
            "note"     : "Catatan",
        }
        if st.session_state.has_foreign:
            col_map["net_5d"] = "Net Asing 5h"
        if signal == "Mark Up":
            col_map["return_1d"] = "Return 1h (%)"
        if signal == "Mark Down":
            col_map["change_3d"] = "Δ3h (%)"

        avail = {k: v for k, v in col_map.items() if k in subset.columns}
        show  = subset[list(avail)].rename(columns=avail).copy()

        if "Harga"        in show: show["Harga"]        = show["Harga"].apply(lambda x: f"Rp {x:,.0f}")
        if "Net Asing 5h" in show: show["Net Asing 5h"] = show["Net Asing 5h"].apply(lambda x: f"Rp {x/1e9:+.1f}M" if pd.notna(x) else "—")
        if "Str"          in show: show["Str"]          = show["Str"].apply(lambda x: f"{x:.1f}")

        st.dataframe(show, use_container_width=True, hide_index=True)


# ── TAB 2: DETAIL SAHAM ──────────────────────────────────────────────────────
with tab2:
    all_tickers = sorted(df["ticker"].unique())

    # ← key="ticker_select" mencegah selectbox reset saat re-run
    selected = st.selectbox("Pilih saham", all_tickers, key="ticker_select")

    if selected and selected in df["ticker"].values:
        row   = df[df["ticker"] == selected].iloc[0]
        color = SIGNAL_COLOR.get(row["signal"], "#64748b")
        emoji = SIGNAL_EMOJI.get(row["signal"], "⚪")

        st.markdown(
            f'<h2>{selected} &nbsp;'
            f'<span style="background:{color};color:white;'
            f'padding:3px 16px;border-radius:14px;font-size:16px">'
            f'{emoji} {row["signal"]}</span></h2>',
            unsafe_allow_html=True,
        )

        if "data_asing" in row and not row["data_asing"] and row["signal"] in ["Akumulasi", "Distribusi"]:
            st.warning(
                "⚠️ Sinyal ini berjalan tanpa data asing — "
                "konfirmasi dengan cek foreign flow di RTI / Stockbit sebelum keputusan."
            )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Harga",    f"Rp {row['close']:,.0f}")
        m2.metric("Strength", f"{row['strength']:.1f} / 100")
        if pd.notna(row.get("change_5d")): m3.metric("Δ 5 Hari", f"{row['change_5d']:+.2f}%")
        if pd.notna(row.get("net_5d")):    m4.metric("Net Asing 5h", f"Rp {row['net_5d']/1e9:+.1f}M")

        st.progress(int(row["strength"]), text=f"Strength: {row['strength']:.1f}/100")

        if row.get("note"):
            st.info(f"📌 {row['note']}")

        # ← Ambil dari session state — tidak hilang saat ganti selectbox
        ohlcv = st.session_state.ohlcv_cache
        if selected in ohlcv:
            st.markdown("#### Chart Harga & Volume")
            render_ohlcv_chart(selected, ohlcv[selected])
        else:
            st.info("Chart tidak tersedia — jalankan screening ulang.")

        foreign = st.session_state.foreign_df
        if not foreign.empty and selected in foreign["ticker"].values:
            st.markdown("#### Net Buy/Sell Asing Harian")
            render_foreign_flow_chart(selected, foreign)


# ── TAB 3: EXPORT ─────────────────────────────────────────────────────────────
with tab3:
    st.subheader("Export Hasil Screening")

    if st.session_state.has_foreign:
        st.success("✅ Data lengkap (harga + volume + foreign flow)")
    else:
        st.warning("⚠️ Data harga & volume saja (tanpa foreign flow)")

    st.dataframe(df, use_container_width=True)

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            "⬇️ Download Hasil CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="idx_screener_hasil.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_dl2:
        if not st.session_state.foreign_df.empty:
            st.download_button(
                "⬇️ Download Foreign Flow CSV",
                data=st.session_state.foreign_df.to_csv(index=False).encode("utf-8"),
                file_name="foreign_flow_data.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with st.expander("📋 Format CSV data asing yang diterima"):
        st.markdown("""
**Kolom minimal yang dibutuhkan:**

| StockCode | ForeignBuy | ForeignSell | NetBuySell |
|-----------|-----------|------------|-----------|
| BBCA | 350000000000 | 100000000000 | 250000000000 |
| TLKM | 80000000000 | 200000000000 | -120000000000 |

**Variasi nama kolom yang dikenali otomatis:**
- Ticker: `StockCode`, `Ticker`, `KodeSaham`, `Kode`, `Emiten`
- Net: `NetBuySell`, `Net`, `NetBeli`, `Net_Buy_Sell`
- Nilai dalam **Rupiah** (bukan lot)
""")
