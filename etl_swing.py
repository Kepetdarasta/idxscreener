# =============================================================================
# etl_swing.py — ETL jalur SWING (MA cross & MACD cross, data harian)
#
# TERPISAH dari etl_pipeline.py (Wyckoff). Menulis hanya ke tabel swing_signals;
# tidak menyentuh screening_results / phase_history.
#
# Jalankan:
#   python etl_swing.py                    # hari ini
#   python etl_swing.py --date 2026-10-02  # tanggal tertentu
#   python etl_swing.py --backfill 10      # 10 hari kalender ke belakang
# =============================================================================

import logging
import sys
from datetime import date, datetime, timedelta

import pandas as pd
from psycopg2.extras import execute_values

from etl_pipeline import get_conn, log_etl_run, sync_stocks

logger = logging.getLogger(__name__)
PROCESS_NAME = "swing_signals"


def save_swing_signals(conn, df: pd.DataFrame, trade_date: date) -> int:
    """Ganti seluruh sinyal swing pada trade_date (idempotent: re-run tidak menyisakan sinyal usang)."""
    rows = [
        (
            str(r["ticker"]).upper(), trade_date, r["signal"], r["direction"],
            float(r["close"]), float(r["strength"]), str(r.get("note", "")),
        )
        for _, r in df.iterrows()
    ]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM swing_signals WHERE signal_date = %s", (trade_date,))
        if rows:
            execute_values(cur, """
                INSERT INTO swing_signals
                    (stock_code, signal_date, signal_type, direction, close_price, strength, note)
                VALUES %s
            """, rows)
    conn.commit()
    return len(rows)


def run_swing_pipeline(trade_date: date = None, tickers: list = None) -> bool:
    from src.swing.swing_screener import load_history, run_swing

    trade_date = trade_date or date.today()
    started_at = datetime.now()

    if trade_date.weekday() >= 5:
        logger.info(f"Skip {trade_date} — weekend")
        return True

    if tickers is None:
        import config as cfg
        tickers = cfg.DEFAULT_UNIVERSE

    logger.info("=" * 60)
    logger.info(f"ETL SWING START — {trade_date} ({len(tickers)} ticker)")
    logger.info("=" * 60)

    conn = None
    try:
        conn = get_conn()
        sync_stocks(conn, tickers)   # jaga FK stock_code kalau swing dijalankan lebih dulu

        ohlcv = load_history(tickers, as_of_date=trade_date)
        if not ohlcv:
            logger.warning(f"Tidak ada bar {trade_date} (libur bursa atau yfinance gagal) — skip")
            log_etl_run(conn, trade_date, PROCESS_NAME, "partial", total=len(tickers),
                        error="Tidak ada bar pada tanggal ini (libur bursa / yfinance gagal)",
                        started_at=started_at)
            return True

        df = run_swing(tickers, as_of_date=trade_date, ohlcv=ohlcv)
        n = save_swing_signals(conn, df, trade_date)

        log_etl_run(conn, trade_date, PROCESS_NAME, "success",
                    total=len(ohlcv), success=n, started_at=started_at)
        logger.info(f"ETL SWING SELESAI — {trade_date}: {n} sinyal dari {len(ohlcv)} saham")
        return True

    except Exception as e:
        logger.error(f"ETL SWING ERROR: {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
                log_etl_run(conn, trade_date, PROCESS_NAME, "failed",
                            error=str(e)[:500], started_at=started_at)
            except Exception:
                pass
        return False
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ETL Swing (MA & MACD cross)")
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD. Default: hari ini")
    parser.add_argument("--backfill", type=int, default=0, help="Proses N hari kalender ke belakang")
    args = parser.parse_args()

    if args.backfill > 0:
        today = date.today()
        ok = True
        for i in range(args.backfill, -1, -1):
            d = today - timedelta(days=i)
            if d.weekday() < 5:
                ok = run_swing_pipeline(trade_date=d) and ok
        sys.exit(0 if ok else 1)
    else:
        target = date.fromisoformat(args.date) if args.date else date.today()
        sys.exit(0 if run_swing_pipeline(trade_date=target) else 1)
