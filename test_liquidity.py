# test_liquidity.py — sementara, hapus setelah selesai testing
from etl_pipeline import get_conn
from src.data_fetcher.liquidity import get_liquid_tickers

conn = get_conn()
tickers = get_liquid_tickers(conn, top_n=45, window_days=20, min_days_required=10)
print(f"{len(tickers)} saham likuid:")
print(tickers)
conn.close()