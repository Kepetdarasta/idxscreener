# =============================================================================
# app.py — Dashboard Streamlit: IDX Screener ADMD
#
# Taruh file ini di ROOT project (sejajar dengan etl_pipeline.py), supaya
# gampang di-deploy ke Streamlit Community Cloud (main file = app.py).
#
# Koneksi database baca dari st.secrets["DATABASE_URL"] kalau di-deploy di
# Streamlit Cloud, atau fallback ke .env (DATABASE_URL) kalau dijalankan
# lokal — jadi satu file ini jalan di dua tempat tanpa ubah kode.
# =============================================================================

import os
from datetime import date

import pandas as pd
import psycopg2
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text
import config as cfg

# =============================================================================
# KONEKSI DATABASE
# =============================================================================

def get_database_url() -> str:
    if "DATABASE_URL" in st.secrets:
        return st.secrets["DATABASE_URL"]
    from dotenv import load_dotenv
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        st.error("DATABASE_URL tidak ditemukan — cek .env (lokal) atau Secrets (Streamlit Cloud).")
        st.stop()
    return url

@st.cache_resource
def get_engine():
    """
    Engine SQLAlchemy AMAN untuk di-cache & dipakai bersama banyak sesi,
    karena SQLAlchemy mengelola connection pool sendiri di baliknya —
    beda dengan objek psycopg2.connect() mentah yang tidak thread-safe.

    pool_pre_ping=True -> otomatis cek & buang koneksi basi/mati sebelum
    dipakai (mengatasi Neon yang suka auto-suspend koneksi idle).
    pool_recycle=280    -> paksa buat koneksi baru sebelum 5 menit
    (sedikit di bawah threshold suspend Neon), supaya tidak sempat basi.
    """
    return create_engine(
        get_database_url(),
        pool_pre_ping=True,
        pool_recycle=280,
    )


@st.cache_data(ttl=300)
def query(sql: str, params: dict = None) -> pd.DataFrame:
    engine = get_engine()
    # SQLAlchemy 2.x butuh text() untuk raw SQL string + named params
    return pd.read_sql(text(sql), engine, params=params or {})


#def get_connection():
#    return psycopg2.connect(get_database_url())


#@st.cache_data(ttl=300)  # cache 5 menit — cukup untuk data EOD, tidak query berulang tiap interaksi
#def query(sql: str, params: tuple = None) -> pd.DataFrame:
#    conn = get_connection()
#    try:
#        return pd.read_sql(sql, conn, params=params)
#    except Exception:
#        # Koneksi mungkin putus (Neon serverless suka auto-sleep) — reconnect sekali
#        st.cache_resource.clear()
#        conn = get_connection()
#        return pd.read_sql(sql, conn, params=params)

# =============================================================================
# PAGE CONFIG
# =============================================================================

st.set_page_config(page_title="IDX Screener — ADMD", page_icon="📈", layout="wide")
st.title("📈 IDX Screener — ADMD")

tab_screening, tab_phase, tab_info = st.tabs(
    ["🔍 Screening", "📊 Histori Fase", "ℹ️ Keterangan"]
)

# =============================================================================
# TAB 1 — SCREENING HARI INI (dengan filter)
# =============================================================================

with tab_screening:
    available_dates = query("""
        SELECT DISTINCT screen_date FROM screening_results
        ORDER BY screen_date DESC LIMIT 60
    """)

    if available_dates.empty:
        st.warning("Belum ada data screening. Jalankan etl_pipeline.py dulu.")
        st.stop()

    col1, col2, col3, col4 = st.columns([1.2, 1.5, 1.5, 1])

    with col1:
        selected_date = st.selectbox(
            "Tanggal screening",
            available_dates["screen_date"],
            format_func=lambda d: d.strftime("%d %b %Y"),
        )

    df = query("""
        SELECT sr.stock_code, s.stock_name, s.sector, sr.close_price, sr.phase,
               sr.signal_type, sr.signal_score, sr.range_high, sr.range_low,
               sr.entry_price, sr.stop_loss, sr.target_price, sr.risk_reward_ratio
        FROM screening_results sr
        JOIN stocks s ON s.stock_code = sr.stock_code
        WHERE sr.screen_date = %(d)s
        ORDER BY sr.signal_score DESC
    """, params={"d": selected_date})

    with col2:
        phase_options = sorted(df["phase"].dropna().unique().tolist())
        selected_phases = st.multiselect("Filter fase", phase_options, default=phase_options)

    with col3:
        signal_options = sorted(df["signal_type"].dropna().unique().tolist())
        selected_signals = st.multiselect("Filter sinyal", signal_options, default=signal_options)

    with col4:
        min_rr = st.number_input("Min RR (kosongkan 0 = semua)", min_value=0.0, value=0.0, step=0.5)

    filtered = df[df["phase"].isin(selected_phases) & df["signal_type"].isin(selected_signals)]
    if min_rr > 0:
        # RR cuma ada untuk sinyal Mark Up — filter ini otomatis exclude sinyal lain saat RR diisi
        filtered = filtered[filtered["risk_reward_ratio"] >= min_rr]

    st.caption(f"{len(filtered)} dari {len(df)} sinyal ditampilkan")

    display_cols = {
        "stock_code": "Ticker", "stock_name": "Nama", "sector": "Sektor",
        "close_price": "Close", "phase": "Fase", "signal_type": "Sinyal",
        "signal_score": "Skor", "entry_price": "Entry", "stop_loss": "Stop Loss",
        "target_price": "Target", "risk_reward_ratio": "RR",
    }
    st.dataframe(
        filtered[list(display_cols.keys())].rename(columns=display_cols),
        use_container_width=True,
        hide_index=True,
    )

    # Ringkasan cepat per fase
    st.subheader("Ringkasan per fase")
    summary = df.groupby("phase").size().reset_index(name="jumlah")
    st.bar_chart(summary.set_index("phase"))

# =============================================================================
# TAB 2 — HISTORI FASE PER SAHAM
# =============================================================================

with tab_phase:
    all_tickers = query("SELECT stock_code FROM stocks ORDER BY stock_code")["stock_code"].tolist()
    ticker = st.selectbox("Pilih saham", all_tickers)

    phase_df = query("""
        SELECT phase, phase_start, phase_end, price_at_start, price_at_end,
               price_change_pct, duration_days
        FROM phase_history
        WHERE stock_code = %(t)s
        ORDER BY phase_start
    """, params={"t": ticker})

    if phase_df.empty:
        st.info(f"Belum ada histori fase untuk {ticker}.")
    else:
        # Fase yang masih berjalan (phase_end NULL) digambar sampai hari ini
        phase_df["phase_end_display"] = phase_df["phase_end"].fillna(pd.Timestamp(date.today()))

        fig = px.timeline(
            phase_df,
            x_start="phase_start",
            x_end="phase_end_display",
            y="phase",
            color="phase",
            color_discrete_map={
                "accumulation": "#22c55e",
                "markup": "#3b82f6",
                "distribution": "#f97316",
                "markdown": "#ef4444",
            },
            hover_data=["price_at_start", "price_at_end", "price_change_pct", "duration_days"],
            title=f"Timeline fase — {ticker}",
        )
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            phase_df.drop(columns=["phase_end_display"]),
            use_container_width=True,
            hide_index=True,
        )

# =============================================================================
# TAB 3 — INFORMASI
# =============================================================================

def _rp_miliar(nominal: int) -> str:
    """Format angka rupiah besar jadi 'Rp XXX miliar' biar gampang dibaca."""
    return f"Rp {nominal / 1_000_000_000:,.0f} miliar".replace(",", ".")


with tab_info:
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

    st.divider()

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

    st.divider()
    st.caption(
        "Semua threshold di atas diambil langsung dari config.py dan bisa disesuaikan "
        "di sana kapan saja — halaman ini akan otomatis mengikuti."
    )
