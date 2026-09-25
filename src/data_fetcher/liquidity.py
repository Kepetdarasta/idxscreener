# =============================================================================
# src/data_fetcher/liquidity.py
# Hitung tier likuiditas saham dari data trading kita sendiri (bukan index resmi)
# =============================================================================

import logging

logger = logging.getLogger(__name__)


def get_liquid_tickers(conn, top_n: int = 45, window_days: int = 20,
                        min_days_required: int = 10) -> list[str]:
    """
    Ambil top_n saham paling likuid berdasarkan rata-rata nilai transaksi
    (value, rupiah) dalam window_days terakhir.
    """
    query = """
        SELECT stock_code, AVG(value) AS avg_value, COUNT(*) AS n_days
        FROM daily_ohlcv
        WHERE trade_date >= (CURRENT_DATE - %s::INT)
          AND value > 0
        GROUP BY stock_code
        HAVING COUNT(*) >= %s
        ORDER BY avg_value DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (window_days, min_days_required, top_n))
        rows = cur.fetchall()

    tickers = [r[0] for r in rows]

    if len(tickers) < top_n:
        logger.warning(
            f"get_liquid_tickers: hanya {len(tickers)}/{top_n} saham punya "
            f"histori >= {min_days_required} hari."
        )

    return tickers