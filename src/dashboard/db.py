# =============================================================================
# src/dashboard/db.py — Koneksi & query ke Neon PostgreSQL untuk dashboard
# Semua fungsi di sini READ-ONLY (SELECT saja), aman dipanggil berulang dari UI.
# =============================================================================

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import psycopg2
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _get_conn():
    """Buat koneksi baru ke Neon. Dipanggil per query, bukan disimpan lama-lama."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise EnvironmentError(
            "DATABASE_URL tidak ditemukan. Pastikan file .env ada dan berisi "
            "DATABASE_URL=postgresql://... (lihat .env.example)."
        )
    return psycopg2.connect(url)


def _run_query(sql: str, params: tuple = None) -> pd.DataFrame:
    conn = _get_conn()
    try:
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


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
        "ORDER BY screen_date DESC LIMIT %s",
        (limit,),
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
        WHERE sr.screen_date = %s
        ORDER BY sr.signal_score DESC
    """
    return _run_query(sql, (screen_date,))


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
        WHERE stock_code = %s
        ORDER BY phase_start ASC
    """
    return _run_query(sql, (ticker,))


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
        WHERE stock_code = %s
        ORDER BY trade_date DESC
        LIMIT %s
    """
    df = _run_query(sql, (ticker, days))
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
    # Vol MA20 opsional — dipakai render_ohlcv_chart kalau ada
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
        WHERE stock_code = %s
        ORDER BY trade_date DESC
        LIMIT %s
    """
    df = _run_query(sql, (ticker, days))
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
