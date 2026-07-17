# =============================================================================
# app.py — Dashboard Streamlit IDX Screener V2
#
# Cara jalankan:
#   streamlit run app.py
#
# Butuh:
#   - DATABASE_URL di file .env (sama seperti yang dipakai etl_pipeline.py)
#   - pip install streamlit psycopg2-binary pandas python-dotenv plotly
# =============================================================================

import os
from datetime import date

import pandas as pd
import psycopg2
import streamlit as st
import plotly.express as px
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="IDX Screener — ADMD",
    page_icon="📊",
    layout="wide",
)

SIGNAL_COLORS = {
    "accumulation": "#22c55e",
    "markup": "#3b82f6",
    "distribution": "#f97316",
    "markdown": "#ef4444",
    "unknown": "#94a3b8",
}
PHASE_LABEL = {
    "accumulation": "🟢 Akumulasi",
    "markup": "🔵 Mark Up",
    "distribution": "🟠 Distribusi",
    "markdown": "🔴 Mark Down",
    "unknown": "⚪ Unknown",
}


# -----------------------------------------------------------------------------
# KONEKSI DATABASE
# -----------------------------------------------------------------------------
@st.cache_resource
def get_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        st.error(
            "DATABASE_URL tidak ditemukan. Pastikan file .env berisi "
            "DATABASE_URL dan berada di folder yang sama dengan app.py."
        )
        st.stop()
    return psycopg2.connect(url)


@st.cache_data(ttl=300)
def load_screening_latest() -> pd.DataFrame:
    conn = get_conn()
    try:
        return pd.read_sql("SELECT * FROM v_screening_latest", conn)
    except Exception as e:
        st.error(f"Gagal load v_screening_latest: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_active_phases() -> pd.DataFrame:
    conn = get_conn()
    try:
        return pd.read_sql("SELECT * FROM v_active_phases", conn)
    except Exception as e:
        st.error(f"Gagal load v_active_phases: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_phase_history(stock_code: str) -> pd.DataFrame:
    conn = get_conn()
    try:
        return pd.read_sql(
            """
            SELECT phase, phase_start, phase_end, price_at_start,
                   price_at_end, price_change_pct, duration_days,
                   ff_net_cumulative
            FROM phase_history
            WHERE stock_code = %(code)s
            ORDER BY phase_start ASC
            """,
            conn,
            params={"code": stock_code},
        )
    except Exception as e:
        st.error(f"Gagal load phase_history: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_all_stock_codes() -> list[str]:
    conn = get_conn()
    try:
        df = pd.read_sql(
            "SELECT DISTINCT stock_code FROM screening_results ORDER BY stock_code",
            conn,
        )
        return df["stock_code"].tolist()
    except Exception:
        return []


# -----------------------------------------------------------------------------
# HEADER
# -----------------------------------------------------------------------------
st.title("📊 IDX Screener — Sinyal ADMD")
st.caption(
    "Akumulasi · Mark Up · Distribusi · Mark Down — berdasarkan harga, "
    "volume, dan foreign flow"
)

df_latest = load_screening_latest()

if df_latest.empty:
    st.warning(
        "Belum ada data di tabel `screening_results`. Jalankan "
        "`python etl_pipeline.py` dulu untuk mengisi data, lalu refresh halaman ini."
    )
    st.stop()

screen_date = df_latest["screen_date"].max()
st.info(f"Data screening terbaru: **{screen_date}**")

# -----------------------------------------------------------------------------
# SIDEBAR — FILTER
# -----------------------------------------------------------------------------
st.sidebar.header("🔍 Filter")

phase_options = sorted(df_latest["phase"].dropna().unique().tolist())
selected_phases = st.sidebar.multiselect(
    "Fase",
    options=phase_options,
    default=phase_options,
    format_func=lambda p: PHASE_LABEL.get(p, p),
)

sector_options = sorted(df_latest["sector"].dropna().unique().tolist())
selected_sectors = st.sidebar.multiselect(
    "Sektor",
    options=sector_options,
    default=sector_options,
)

min_score = st.sidebar.slider("Minimal Signal Score", 0, 100, 0)

search_ticker = st.sidebar.text_input("Cari kode saham (misal BBCA)").upper().strip()

# Terapkan filter
df_filtered = df_latest[
    df_latest["phase"].isin(selected_phases)
    & df_latest["sector"].isin(selected_sectors)
    & (df_latest["signal_score"].fillna(0) >= min_score)
]
if search_ticker:
    df_filtered = df_filtered[df_filtered["stock_code"].str.contains(search_ticker)]

# -----------------------------------------------------------------------------
# RINGKASAN / METRIC
# -----------------------------------------------------------------------------
st.subheader("Ringkasan Hari Ini")
cols = st.columns(4)
for col, phase in zip(cols, ["accumulation", "markup", "distribution", "markdown"]):
    count = int((df_latest["phase"] == phase).sum())
    col.metric(PHASE_LABEL[phase], count)

st.divider()

# -----------------------------------------------------------------------------
# TABEL HASIL SCREENING
# -----------------------------------------------------------------------------
st.subheader(f"Hasil Screening ({len(df_filtered)} saham)")

if df_filtered.empty:
    st.warning("Tidak ada saham yang cocok dengan filter di atas.")
else:
    show_cols = [
        "stock_code", "stock_name", "sector", "phase", "signal_type",
        "signal_score", "close_price", "volume_ratio",
        "ff_net_3d", "ff_net_5d", "ff_net_20d",
        "ff_net_today", "ff_value_today",
    ]
    show_cols = [c for c in show_cols if c in df_filtered.columns]
    df_display = df_filtered[show_cols].sort_values("signal_score", ascending=False)
    df_display["phase"] = df_display["phase"].map(lambda p: PHASE_LABEL.get(p, p))

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "signal_score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d"
            ),
        },
    )

    # Distribusi sinyal
    fig_pie = px.pie(
        df_latest,
        names="phase",
        title="Distribusi Fase — Seluruh Universe",
        color="phase",
        color_discrete_map=SIGNAL_COLORS,
    )
    st.plotly_chart(fig_pie, use_container_width=True)

st.divider()

# -----------------------------------------------------------------------------
# FASE AKTIF (BERAPA LAMA SUDAH DI FASE INI)
# -----------------------------------------------------------------------------
st.subheader("📅 Saham dalam Fase Aktif")
df_active = load_active_phases()

if df_active.empty:
    st.caption("Belum ada data fase aktif.")
else:
    df_active_display = df_active.copy()
    df_active_display["phase"] = df_active_display["phase"].map(
        lambda p: PHASE_LABEL.get(p, p)
    )
    st.dataframe(
        df_active_display,
        use_container_width=True,
        hide_index=True,
    )

st.divider()

# -----------------------------------------------------------------------------
# DETAIL PER SAHAM — TIMELINE PERGERAKAN FASE
# -----------------------------------------------------------------------------
st.subheader("📈 Riwayat Pergerakan Fase per Saham")

all_codes = load_all_stock_codes()
if not all_codes:
    all_codes = sorted(df_latest["stock_code"].unique().tolist())

selected_stock = st.selectbox("Pilih saham", options=all_codes)

if selected_stock:
    df_hist = load_phase_history(selected_stock)
    if df_hist.empty:
        st.caption(f"Belum ada riwayat fase untuk {selected_stock}.")
    else:
        df_hist = df_hist.copy()
        df_hist["phase_end_display"] = df_hist["phase_end"].fillna(pd.Timestamp(date.today()))
        df_hist["phase_label"] = df_hist["phase"].map(lambda p: PHASE_LABEL.get(p, p))

        fig_timeline = px.timeline(
            df_hist,
            x_start="phase_start",
            x_end="phase_end_display",
            y="phase_label",
            color="phase",
            color_discrete_map=SIGNAL_COLORS,
            title=f"Timeline Fase — {selected_stock}",
            hover_data=["price_at_start", "price_at_end", "price_change_pct", "duration_days"],
        )
        fig_timeline.update_yaxes(title="")
        st.plotly_chart(fig_timeline, use_container_width=True)

        st.dataframe(
            df_hist[
                ["phase", "phase_start", "phase_end", "duration_days",
                 "price_at_start", "price_at_end", "price_change_pct",
                 "ff_net_cumulative"]
            ],
            use_container_width=True,
            hide_index=True,
        )

st.divider()
st.caption(
    "Data foreign flow dalam satuan rupiah. "
    "`phase_end = NULL` artinya saham masih berada di fase tersebut."
)
