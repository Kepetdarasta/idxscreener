# =============================================================================
# src/signals/screener.py — Orchestrator semua sinyal ADMD
# =============================================================================

import logging
from pathlib import Path
from typing import List, Optional

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg

from src.signals import accumulation, distribution, markup, markdown

logger = logging.getLogger(__name__)

SIGNAL_FUNCS = {
    "Akumulasi" : accumulation.detect,
    "Distribusi": distribution.detect,
    "Mark Up"   : markup.detect,
    "Mark Down" : markdown.detect,
}

SIGNAL_EMOJI = {
    "Akumulasi" : "🟢",
    "Distribusi": "🟠",
    "Mark Up"   : "🔵",
    "Mark Down" : "🔴",
}


def run_all(
    tickers: List[str] = None,
    use_cache: bool = True,
    save_output: bool = True,
) -> pd.DataFrame:
    from src.data_fetcher.yfinance_fetcher import fetch_ohlcv
    from src.data_fetcher.idx_foreign_parser import load_foreign_flow

    tickers = tickers or cfg.DEFAULT_UNIVERSE
    logger.info(f"Screening {len(tickers)} ticker — 4 sinyal ADMD")

    logger.info("Step 1/3: Download OHLCV...")
    ohlcv = fetch_ohlcv(tickers, use_cache=use_cache)
    if not ohlcv:
        logger.error("Tidak ada data OHLCV.")
        return pd.DataFrame()

    logger.info("Step 2/3: Baca foreign flow...")
    foreign = load_foreign_flow(tickers, days=5)
    if foreign.empty:
        logger.warning("Data foreign flow tidak tersedia — sinyal net asing dilewati.")

    logger.info("Step 3/3: Deteksi sinyal ADMD...")
    all_results = []
    for name, fn in SIGNAL_FUNCS.items():
        try:
            result = fn(ohlcv, foreign)
            if not result.empty:
                all_results.append(result)
                logger.info(f"  {SIGNAL_EMOJI[name]} {name}: {len(result)} sinyal")
            else:
                logger.info(f"  — {name}: tidak ada sinyal")
        except Exception as e:
            logger.error(f"  ✗ {name}: {e}")

    if not all_results:
        logger.warning("Tidak ada sinyal sama sekali.")
        return pd.DataFrame()

    combined = pd.concat(all_results, ignore_index=True)
    combined = combined.sort_values(
        ["signal", "strength"], ascending=[True, False]
    ).reset_index(drop=True)

    if save_output:
        cfg.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        combined.to_csv(cfg.SIGNALS_OUTPUT_PATH, index=False)
        logger.info(f"Hasil disimpan → {cfg.SIGNALS_OUTPUT_PATH}")

    logger.info(f"Selesai — {len(combined)} sinyal dari {len(tickers)} ticker.")
    return combined


def run_single(signal_name: str, tickers: List[str] = None, use_cache: bool = True) -> pd.DataFrame:
    from src.data_fetcher.yfinance_fetcher import fetch_ohlcv
    from src.data_fetcher.idx_foreign_parser import load_foreign_flow

    if signal_name not in SIGNAL_FUNCS:
        raise ValueError(f"Signal tidak dikenal: '{signal_name}'. Pilih: {list(SIGNAL_FUNCS)}")

    tickers = tickers or cfg.DEFAULT_UNIVERSE
    ohlcv   = fetch_ohlcv(tickers, use_cache=use_cache)
    foreign = load_foreign_flow(tickers, days=5)
    return SIGNAL_FUNCS[signal_name](ohlcv, foreign)


def print_summary(df: pd.DataFrame) -> None:
    if df.empty:
        print("\n  Tidak ada sinyal ditemukan.\n")
        return

    print(f"\n{'='*65}")
    print(f"  IDX SCREENER — ADMD  ({len(df)} sinyal total)")
    print(f"{'='*65}")

    for signal, emoji in SIGNAL_EMOJI.items():
        subset = df[df["signal"] == signal]
        if subset.empty:
            continue
        print(f"\n{emoji} {signal.upper()} ({len(subset)} saham)")
        print(f"  {'Ticker':<7} {'Close':>9}  {'Str':>5}  Catatan")
        print(f"  {'-'*56}")
        for _, row in subset.iterrows():
            print(
                f"  {row['ticker']:<7} "
                f"Rp{row['close']:>8,.0f}  "
                f"{row['strength']:>5.1f}  "
                f"{row.get('note', '')}"
            )

    print(f"\n{'='*65}\n")
