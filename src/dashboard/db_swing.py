# =============================================================================
# src/dashboard/db_swing.py — Query khusus jalur SWING
# Berdiri sendiri (tidak mengubah db.py): koneksi dari DATABASE_URL, cache 5 menit.
# =============================================================================

import os

import pandas as pd
import psycopg2
import streamlit as st


def _connect():
    url = os.getenv("DATABASE_URL")
    if not url:
        try:
            url = st.secrets["DATABASE_URL"]
        except Exception:
            url = None
    if not url:
        raise EnvironmentError("DATABASE_URL tidak ditemukan (.env / st.secrets)")
    return psycopg2.connect(url)


@st.cache_data(ttl=300)
def get_swing_signals(days: int = 45) -> pd.DataFrame:
    """Sinyal swing `days` hari kalender terakhir, terbaru dulu."""
    sql = """
        SELECT ss.signal_date, ss.stock_code, s.stock_name, s.sector,
               ss.signal_type, ss.direction, ss.close_price, ss.strength, ss.note
        FROM swing_signals ss
        JOIN stocks s ON s.stock_code = ss.stock_code
        WHERE ss.signal_date >= CURRENT_DATE - %s
        ORDER BY ss.signal_date DESC, ss.strength DESC, ss.stock_code
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (int(days),))
            cols = [c.name for c in cur.description]
            rows = cur.fetchall()
    finally:
        conn.close()

    df = pd.DataFrame(rows, columns=cols)
    for c in ("close_price", "strength"):
        df[c] = pd.to_numeric(df[c])
    return df
