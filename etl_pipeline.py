# =============================================================================
# etl_pipeline.py — ETL Pipeline Stock Screening V2
#
# Menghubungkan screener v1 yang sudah ada ke database PostgreSQL (Neon).
# Jalankan manual:  python etl_pipeline.py
# Atau otomatis via scheduler (lihat scheduler.py)
#
# CATATAN: pipeline ini HANYA untuk jalur Wyckoff (jangka panjang).
# Sinyal swing (MA/MACD cross) ada di etl_swing.py — sengaja dipisah.
#
# Urutan proses:
#   1. Sync master saham  → tabel stocks
#   2. Fetch & simpan OHLCV harian → tabel daily_ohlcv
#   3. Jalankan screener ADMD → tabel screening_results
#   4. Deteksi & update fase → tabel phase_history
# =============================================================================

import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# ── Path setup (sesuaikan jika struktur folder berbeda) ──────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

# ── Logger ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(ROOT / "etl.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# =============================================================================
# KONEKSI DATABASE
# =============================================================================

def get_conn():
    """Buat koneksi baru ke Neon PostgreSQL."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL tidak ditemukan di .env")
    return psycopg2.connect(url)


# =============================================================================
# STEP 1 — SYNC MASTER SAHAM
# =============================================================================

def sync_stocks(conn, tickers: list[str]) -> None:
    """
    Insert ticker baru ke tabel stocks.
    Ticker yang sudah ada di-skip (ON CONFLICT DO NOTHING).
    """
    logger.info(f"[1/4] Sync master saham — {len(tickers)} ticker")
    rows = [(t.upper(), t.upper(), None, None, True) for t in tickers]

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO stocks (stock_code, stock_name, sector, subsector, is_active)
            VALUES %s
            ON CONFLICT (stock_code) DO NOTHING
        """, rows)
    conn.commit()
    logger.info(f"       Sync selesai.")


# =============================================================================
# STEP 2 — FETCH & SIMPAN OHLCV
# =============================================================================

def fetch_and_save_ohlcv(conn, tickers: list[str], trade_date: date) -> int:
    """
    Fetch OHLCV dari yfinance untuk trade_date, simpan ke daily_ohlcv.
    Return jumlah baris yang berhasil disimpan.
    """
    logger.info(f"[2/4] Fetch OHLCV — {trade_date}")

    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance belum terinstall: pip install yfinance")
        return 0

    # yfinance butuh range start..end+1 untuk data satu hari
    start = trade_date
    end   = trade_date + timedelta(days=1)

    tickers_yf = [f"{t}.JK" for t in tickers]
    logger.info(f"       Download {len(tickers_yf)} ticker dari yfinance...")

    try:
        raw = yf.download(
            tickers_yf,
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
    except Exception as e:
        logger.error(f"       yfinance error: {e}")
        return 0

    if raw.empty:
        logger.warning(f"       Tidak ada data OHLCV untuk {trade_date} (hari libur/weekend?)")
        return 0

    rows = []
    for ticker in tickers:
        ticker_yf = f"{ticker}.JK"
        try:
            if len(tickers) == 1:
                df_t = raw
            else:
                df_t = raw[ticker_yf] if ticker_yf in raw.columns.get_level_values(0) else pd.DataFrame()

            if df_t.empty:
                continue

            row = df_t.iloc[0]
            rows.append((
                ticker.upper(),
                trade_date,
                float(row.get("Open",   0) or 0),
                float(row.get("High",   0) or 0),
                float(row.get("Low",    0) or 0),
                float(row.get("Close",  0) or 0),
                int(row.get("Volume",   0) or 0),
                0,   # value — tidak tersedia di yfinance, isi 0
                0,   # frequency — tidak tersedia di yfinance, isi 0
            ))
        except Exception as e:
            logger.warning(f"       {ticker}: skip — {e}")

    if not rows:
        logger.warning("       Tidak ada baris OHLCV valid.")
        return 0

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO daily_ohlcv
                (stock_code, trade_date, open_price, high_price, low_price,
                 close_price, volume, value, frequency)
            VALUES %s
            ON CONFLICT (stock_code, trade_date) DO UPDATE SET
                open_price  = EXCLUDED.open_price,
                high_price  = EXCLUDED.high_price,
                low_price   = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume      = EXCLUDED.volume
        """, rows)
    conn.commit()
    logger.info(f"       OHLCV tersimpan: {len(rows)} saham")
    return len(rows)


# =============================================================================
# STEP 3 — JALANKAN SCREENER & SIMPAN HASIL
# =============================================================================

# Mapping sinyal v1 → phase di skema v2
SIGNAL_TO_PHASE = {
    "Akumulasi" : "accumulation",
    "Mark Up"   : "markup",
    "Distribusi": "distribution",
    "Mark Down" : "markdown",
}

def _wyckoff_only(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sisakan hanya sinyal Wyckoff (ADMD) dan maksimal SATU sinyal per saham
    (strength tertinggi). Tanpa ini, saham yang kena dua sinyal di hari yang sama
    bikin ON CONFLICT error di screening_results dan fase bolak-balik di phase_history.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    out = df[df["signal"].isin(SIGNAL_TO_PHASE.keys())].copy()
    if out.empty:
        return out
    out["_t"] = out["ticker"].astype(str).str.upper()
    return (
        out.sort_values("strength", ascending=False)
           .drop_duplicates("_t", keep="first")
           .drop(columns="_t")
           .reset_index(drop=True)
    )


def run_screener_and_save(conn, tickers: list[str], trade_date: date) -> pd.DataFrame:
    """
    Jalankan screener ADMD dari v1, simpan hasilnya ke screening_results.
    Return DataFrame hasil screening.
    """
    logger.info(f"[3/4] Jalankan screener ADMD — {trade_date}")

    try:
        from src.signals.screener import run_all
    except ImportError:
        logger.error("Tidak bisa import screener — pastikan path benar")
        return pd.DataFrame()

    df = run_all(tickers=tickers, use_cache=False, save_output=False, as_of_date=trade_date)
    df = _wyckoff_only(df)
    if df.empty:
        logger.warning("       Screener tidak menghasilkan sinyal.")
        return pd.DataFrame()

    logger.info(f"       Screener selesai: {len(df)} sinyal")

    # Fetch close price dari DB untuk saham yang tidak ada di hasil screener
    # (screener hanya return saham yang punya sinyal)
    rows = []
    for _, row in df.iterrows():
        ticker  = str(row["ticker"]).upper()
        signal  = str(row.get("signal", ""))
        phase   = SIGNAL_TO_PHASE.get(signal, "unknown")
        close   = float(row.get("close",    0) or 0)
        score   = float(row.get("strength", 0) or 0)
        note    = str(row.get("note", ""))

        rows.append((
            ticker,
            trade_date,
            close,
            None,   # volume_ratio — belum ada di v1, akan diisi nanti
            signal, # signal_type (nama asli dari v1)
            min(100, max(0, int(score * 10))),  # normalize 0–10 → 0–100
            phase,
        ))

    if not rows:
        return df

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO screening_results
                (stock_code, screen_date, close_price, volume_ratio,
                 signal_type, signal_score, phase)
            VALUES %s
            ON CONFLICT (stock_code, screen_date) DO UPDATE SET
                close_price  = EXCLUDED.close_price,
                signal_type  = EXCLUDED.signal_type,
                signal_score = EXCLUDED.signal_score,
                phase        = EXCLUDED.phase
        """, rows)
    conn.commit()
    logger.info(f"       Screening results tersimpan: {len(rows)} baris")
    return df


# =============================================================================
# STEP 4 — DETEKSI & UPDATE FASE
# =============================================================================

def update_phase_history(conn, df_screening: pd.DataFrame, trade_date: date) -> None:
    """
    Update phase_history. Aturan (Wyckoff = jangka panjang):
      - Fase berubah HANYA jika screener mendeteksi fase LAIN untuk saham itu.
      - Saham tanpa sinyal hari ini -> fase aktif dibiarkan berjalan (phase_end tetap NULL).
      - Fase lama ditutup di tanggal fase baru dimulai, dengan price_at_end = harga hari itu
        (tanggal & harga konsisten).
      - Idempotent: menjalankan ulang tanggal yang sama tidak menggandakan baris.
    """
    logger.info(f"[4/4] Update phase history — {trade_date}")

    df = _wyckoff_only(df_screening)
    if df.empty:
        logger.info("       Tidak ada sinyal Wyckoff hari ini, fase aktif dibiarkan berjalan.")
        return

    n_new = n_switch = 0
    with conn.cursor() as cur:
        for _, row in df.iterrows():
            ticker = str(row["ticker"]).upper()
            phase  = SIGNAL_TO_PHASE[row["signal"]]
            close  = float(row.get("close", 0) or 0)
            if close <= 0:
                continue

            cur.execute("""
                SELECT id, phase, phase_start
                FROM phase_history
                WHERE stock_code = %s AND phase_end IS NULL
                ORDER BY phase_start DESC LIMIT 1
            """, (ticker,))
            active = cur.fetchone()

            if active is None:
                cur.execute("""
                    INSERT INTO phase_history (stock_code, phase, phase_start, price_at_start)
                    VALUES (%s, %s, %s, %s)
                """, (ticker, phase, trade_date, close))
                n_new += 1
                continue

            active_id, active_phase, active_start = active

            if active_phase == phase:
                continue  # fase sama -> tetap berjalan

            if active_start > trade_date:
                logger.warning(f"       {ticker}: fase aktif dimulai {active_start} > {trade_date}, skip (backfill tidak berurutan?)")
                continue

            if active_start == trade_date:
                # re-run di hari yang sama dengan hasil berbeda -> koreksi in-place
                cur.execute("""
                    UPDATE phase_history
                    SET phase = %s, price_at_start = %s, updated_at = NOW()
                    WHERE id = %s
                """, (phase, close, active_id))
            else:
                cur.execute("""
                    UPDATE phase_history
                    SET phase_end = %s, price_at_end = %s, updated_at = NOW()
                    WHERE id = %s
                """, (trade_date, close, active_id))
                cur.execute("""
                    INSERT INTO phase_history (stock_code, phase, phase_start, price_at_start)
                    VALUES (%s, %s, %s, %s)
                """, (ticker, phase, trade_date, close))

            n_switch += 1
            logger.info(f"       {ticker}: {active_phase} → {phase}")

    conn.commit()
    logger.info(f"       Phase history updated: {n_new} fase baru, {n_switch} transisi.")


# =============================================================================
# LOGGING ETL RUN
# =============================================================================

def log_etl_run(conn, run_date: date, process: str, status: str,
                total: int = 0, success: int = 0, failed: int = 0,
                error: str = None, started_at: datetime = None) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO etl_log
                (run_date, process_name, status, stocks_total, stocks_success,
                 stocks_failed, error_message, started_at, finished_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (run_date, process, status, total, success, failed, error, started_at))
    conn.commit()


# =============================================================================
# MAIN — PIPELINE UTAMA
# =============================================================================

def run_pipeline(trade_date: date = None, tickers: list[str] = None) -> bool:
    """
    Jalankan full ETL pipeline untuk satu tanggal.

    Parameters
    ----------
    trade_date : date yang diproses, default = hari ini
    tickers    : list ticker, default = dari config DEFAULT_UNIVERSE

    Returns
    -------
    True jika berhasil, False jika ada error kritis
    """
    trade_date = trade_date or date.today()
    started_at = datetime.now()

    # Skip weekend
    if trade_date.weekday() >= 5:
        logger.info(f"Skip {trade_date} — hari libur (weekend)")
        return True

    # Load tickers dari config jika tidak diisi
    if tickers is None:
        try:
            import config as cfg
            tickers = cfg.DEFAULT_UNIVERSE
        except ImportError:
            logger.error("Tidak bisa import config.py — pastikan file ada")
            return False

    logger.info("=" * 60)
    logger.info(f"ETL PIPELINE START — {trade_date} ({len(tickers)} ticker)")
    logger.info("=" * 60)

    conn = None
    try:
        conn = get_conn()

        # Step 1 — Master saham
        sync_stocks(conn, tickers)

        # Step 2 — OHLCV
        n_ohlcv = fetch_and_save_ohlcv(conn, tickers, trade_date)
        if n_ohlcv == 0:
            # Libur bursa (atau yfinance gagal): jangan lanjut, kalau tidak sinyal data lama
            # akan tersimpan dengan label tanggal ini.
            logger.warning(f"OHLCV kosong untuk {trade_date} — step 3-4 di-skip")
            log_etl_run(
                conn, trade_date, "full_pipeline", "partial", total=len(tickers),
                error="OHLCV kosong (libur bursa atau yfinance gagal) — step 3-4 di-skip",
                started_at=started_at,
            )
            return True

        # Step 3 — Screener
        df_result = run_screener_and_save(conn, tickers, trade_date)

        # Step 4 — Phase history
        update_phase_history(conn, df_result, trade_date)

        # Log sukses
        log_etl_run(
            conn, trade_date, "full_pipeline", "success",
            total=len(tickers), success=len(df_result),
            started_at=started_at
        )

        logger.info("=" * 60)
        logger.info(f"ETL PIPELINE SELESAI — {trade_date}")
        logger.info(f"  OHLCV   : {n_ohlcv} saham")
        logger.info(f"  Sinyal  : {len(df_result)} saham")
        logger.info("=" * 60)
        return True

    except Exception as e:
        logger.error(f"ETL PIPELINE ERROR: {e}", exc_info=True)
        if conn:
            try:
                log_etl_run(
                    conn, trade_date, "full_pipeline", "failed",
                    error=str(e)[:500], started_at=started_at
                )
            except Exception:
                pass
        return False

    finally:
        if conn:
            conn.close()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ETL Pipeline Stock Screening V2")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Tanggal proses (YYYY-MM-DD). Default: hari ini"
    )
    parser.add_argument(
        "--backfill",
        type=int,
        default=0,
        help="Proses N hari ke belakang. Contoh: --backfill 5"
    )
    args = parser.parse_args()

    if args.backfill > 0:
        # Mode backfill: proses beberapa hari sekaligus
        today = date.today()
        for i in range(args.backfill, -1, -1):
            d = today - timedelta(days=i)
            if d.weekday() < 5:  # skip weekend
                run_pipeline(trade_date=d)
    else:
        # Mode normal: proses satu hari
        target = date.fromisoformat(args.date) if args.date else date.today()
        success = run_pipeline(trade_date=target)
        sys.exit(0 if success else 1)
