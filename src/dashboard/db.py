# =============================================================================
# src/dashboard/db.py — Koneksi & query ke Neon PostgreSQL untuk dashboard
# Semua fungsi di sini READ-ONLY (SELECT saja), aman dipanggil berulang dari UI.
#
# PERUBAHAN dari versi sebelumnya:
#   - Pakai SQLAlchemy Engine (connection pool) via st.cache_resource, bukan
#     psycopg2.connect() baru untuk SETIAP query. Engine SQLAlchemy aman
#     di-cache & dipakai bersama banyak sesi (thread-safe), beda dengan
#     objek koneksi psycopg2 mentah.
#   - connect_timeout eksplisit -> kalau Neon lambat "bangun"/tidak
#     merespons, query akan GAGAL dengan error jelas dalam beberapa detik,
#     BUKAN menggantung tanpa batas waktu (yang selama ini terlihat
#     sebagai halaman blank/kosong).
#   - pool_pre_ping + pool_recycle -> otomatis buang & ganti koneksi yang
#     basi karena Neon auto-suspend, sebelum dipakai query berikutnya.
#
# Nama & signature semua fungsi public (get_latest_screening, get_ohlcv,
# dst) TIDAK berubah, jadi app.py tidak perlu diedit sama sekali.
# =============================================================================

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def _get_database_url() -> str:
    # Streamlit Cloud: disimpan di Settings -> Secrets
    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass  # st.secrets bisa error kalau belum ada secrets.toml sama sekali (lokal)

    # Lokal: fallback ke .env
    url = os.getenv("DATABASE_URL")
    if not url:
        raise EnvironmentError(
            "DATABASE_URL tidak ditemukan. Pastikan file .env ada dan berisi "
            "DATABASE_URL=postgresql://... (lihat .env.example), atau sudah "
            "diisi di Streamlit Cloud -> Settings -> Secrets."
        )
    return url


@st.cache_resource(show_spinner=False)
def _get_engine():
    """
    Satu engine SQLAlchemy dipakai bersama semua sesi — ini AMAN (beda
    dengan psycopg2.connect() mentah) karena SQLAlchemy mengelola
    connection pool sendiri secara thread-safe di baliknya.
    """
    return create_engine(
        _get_database_url(),
        pool_pre_ping=True,          # cek & buang koneksi basi sebelum dipakai
        pool_recycle=280,            # paksa buat koneksi baru sebelum 5 menit
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 10},  # gagal cepat, bukan menggantung
    )


def _run_query(sql: str, params: dict = None) -> pd.DataFrame:
    engine = _get_engine()
    return pd.read_sql(text(sql), engine, params=params or {})


# =============================================================================
# SCREENING TERBARU (view v_screening_latest)
# =============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_latest_screening() -> pd.DataFrame:
    """
    Hasil screening pada screen_date TERBARU yang ada di database.
    Kolom: screen_date, stock_code, stock_name, sector, close_price,
           volume_ratio, ff_net_3d, ff_net_5d, ff_net_20d,
           signal_type, signal_score, phase, ff_net_today, ff_value_today
    """
    return _run_query("SELECT * FROM v_screening_latest ORDER BY signal_score DESC")


@st.cache_data(ttl=300, show_spinner=False)
def get_available_dates(limit: int = 60) -> list:
    """Daftar tanggal screening yang tersedia, terbaru dulu."""
    df = _run_query(
        "SELECT DISTINCT screen_date FROM screening_results "
        "ORDER BY screen_date DESC LIMIT :limit",
        {"limit": limit},
    )
    return df["screen_date"].tolist()


@st.cache_data(ttl=300, show_spinner=False)
def get_screening_by_date(screen_date) -> pd.DataFrame:
    """Hasil screening untuk tanggal tertentu (untuk lihat histori, bukan cuma hari ini)."""
    sql = """
        SELECT sr.screen_date, sr.stock_code, s.stock_name, s.sector,
               sr.close_price, sr.volume_ratio,
               sr.ff_net_3d, sr.ff_net_5d, sr.ff_net_20d,
               sr.signal_type, sr.signal_score, sr.phase
        FROM screening_results sr
        JOIN stocks s ON s.stock_code = sr.stock_code
        WHERE sr.screen_date = :d
        ORDER BY sr.signal_score DESC
    """
    return _run_query(sql, {"d": screen_date})


# =============================================================================
# FASE AKTIF (view v_active_phases)
# =============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_active_phases() -> pd.DataFrame:
    """
    Saham yang sedang berada di suatu fase (phase_end IS NULL).
    Kolom: stock_code, stock_name, sector, phase, phase_start,
           days_in_phase, price_at_start, current_price, ff_net_cumulative
    """
    return _run_query("SELECT * FROM v_active_phases")


@st.cache_data(ttl=300, show_spinner=False)
def get_phase_history(ticker: str) -> pd.DataFrame:
    """Riwayat lengkap transisi fase untuk satu saham (termasuk yang sudah selesai)."""
    sql = """
        SELECT phase, phase_start, phase_end, duration_days,
               price_at_start, price_at_end, price_change_pct, ff_net_cumulative
        FROM phase_history
        WHERE stock_code = :t
        ORDER BY phase_start ASC
    """
    return _run_query(sql, {"t": ticker})


# =============================================================================
# OHLCV — dibentuk ulang kolomnya supaya cocok dengan components.render_ohlcv_chart
# =============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_ohlcv(ticker: str, days: int = 90) -> pd.DataFrame:
    """
    OHLCV historis untuk satu saham, kolom & index disesuaikan
    supaya langsung cocok dipakai oleh render_ohlcv_chart():
    index = trade_date (datetime), kolom Open/High/Low/Close/Volume.
    """
    sql = """
        SELECT trade_date, open_price, high_price, low_price, close_price, volume
        FROM daily_ohlcv
        WHERE stock_code = :t
        ORDER BY trade_date DESC
        LIMIT :days
    """
    df = _run_query(sql, {"t": ticker, "days": days})
    if df.empty:
        return df

    df = df.sort_values("trade_date")
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date").rename(columns={
        "open_price": "Open",
        "high_price": "High",
        "low_price": "Low",
        "close_price": "Close",
        "volume": "Volume",
    })
    df["vol_avg20"] = df["Volume"].rolling(20, min_periods=1).mean()
    return df


# =============================================================================
# FOREIGN FLOW — dibentuk ulang supaya cocok dengan render_foreign_flow_chart
# =============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_foreign_flow(ticker: str, days: int = 30) -> pd.DataFrame:
    """
    Foreign flow historis untuk satu saham, kolom disesuaikan
    supaya cocok dipakai render_foreign_flow_chart():
    kolom ticker, date, net_buy_sell (dalam rupiah).
    """
    sql = """
        SELECT stock_code, trade_date, foreign_net_value
        FROM foreign_flow
        WHERE stock_code = :t
        ORDER BY trade_date DESC
        LIMIT :days
    """
    df = _run_query(sql, {"t": ticker, "days": days})
    if df.empty:
        return df

    df = df.rename(columns={
        "stock_code": "ticker",
        "trade_date": "date",
        "foreign_net_value": "net_buy_sell",
    })
    df["net_buy_sell"] = df["net_buy_sell"].astype(float)
    return df.sort_values("date")


# =============================================================================
# ETL STATUS — buat kasih tahu user kapan data terakhir di-update
# =============================================================================

@st.cache_data(ttl=300, show_spinner=False)
def get_last_etl_run() -> pd.DataFrame:
    sql = """
        SELECT run_date, process_name, status, stocks_success, stocks_failed, finished_at
        FROM etl_log
        ORDER BY finished_at DESC NULLS LAST
        LIMIT 1
    """
    return _run_query(sql)
