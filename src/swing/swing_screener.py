# =============================================================================
# src/swing/swing_screener.py — Orchestrator jalur SWING (data harian)
#
# MA Cross + MACD Cross. TERPISAH dari Wyckoff (src/signals/screener.py):
#   - tidak menulis ke screening_results / phase_history
#   - tidak mengenal "fase"; hanya event crossover pada hari bursa
#   - histori diambil sendiri (SWING_HISTORY_PERIOD) karena MACD butuh >= 45 hari bursa
# =============================================================================

import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg
from src.swing import ma_cross, macd_cross
from src.utils.asof import truncate_ohlcv

logger = logging.getLogger(__name__)

SWING_FUNCS = {
    "MA Cross"  : ma_cross.detect,
    "MACD Cross": macd_cross.detect,
}

DIRECTION = {
    ma_cross.SIGNAL_GOLDEN   : "bullish",
    ma_cross.SIGNAL_DEATH    : "bearish",
    macd_cross.SIGNAL_BULLISH: "bullish",
    macd_cross.SIGNAL_BEARISH: "bearish",
}

COLUMNS = ["ticker", "signal", "close", "strength", "note", "direction"]


@lru_cache(maxsize=2)
def _fetch_history(tickers: tuple, period: str) -> Dict[str, pd.DataFrame]:
    """Download OHLCV harian (cache di memori supaya backfill tidak download berulang)."""
    import yfinance as yf

    out: Dict[str, pd.DataFrame] = {}
    size = getattr(cfg, "YFINANCE_BATCH_SIZE", 20)

    for i in range(0, len(tickers), size):
        batch = tickers[i:i + size]
        yf_tickers = [f"{t}{cfg.YFINANCE_SUFFIX}" for t in batch]
        try:
            raw = yf.download(
                yf_tickers, period=period, interval="1d",
                auto_adjust=True, group_by="ticker", progress=False, threads=True,
            )
        except Exception as e:
            logger.error(f"yfinance error (batch {i // size + 1}): {e}")
            continue
        if raw is None or raw.empty:
            continue

        for t, yt in zip(batch, yf_tickers):
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    if yt not in raw.columns.get_level_values(0):
                        continue
                    d = raw[yt]
                else:
                    d = raw
                d = d[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"]).sort_index()
                if not d.empty:
                    out[t] = d
            except Exception as e:
                logger.warning(f"  {t}: skip — {e}")
    return out


def load_history(tickers: List[str], as_of_date=None) -> Dict[str, pd.DataFrame]:
    """
    Histori OHLCV untuk swing, dipotong sampai as_of_date.
    Jika as_of_date diberikan, hanya saham yang BAR TERAKHIR-nya tepat as_of_date yang
    dipakai (menghindari sinyal data lama berlabel tanggal baru saat bursa libur).
    """
    key = tuple(sorted({t.upper() for t in tickers}))
    raw = _fetch_history(key, getattr(cfg, "SWING_HISTORY_PERIOD", "9mo"))
    ohlcv = truncate_ohlcv(raw, as_of_date)

    if as_of_date is not None:
        cutoff = pd.Timestamp(as_of_date).normalize()
        ohlcv = {
            t: d for t, d in ohlcv.items()
            if pd.Timestamp(d.index[-1]).tz_localize(None).normalize() == cutoff
        }
    return ohlcv


def run_swing(
    tickers: List[str] = None,
    as_of_date=None,
    ohlcv: Optional[Dict[str, pd.DataFrame]] = None,
) -> pd.DataFrame:
    """
    Jalankan MA cross + MACD cross.
    Return DataFrame: ticker, signal, close, strength (0-10), note, direction.
    """
    tickers = tickers or cfg.DEFAULT_UNIVERSE
    if ohlcv is None:
        ohlcv = load_history(tickers, as_of_date)
    if not ohlcv:
        logger.warning("Swing: tidak ada data OHLCV.")
        return pd.DataFrame(columns=COLUMNS)

    results = []
    for name, fn in SWING_FUNCS.items():
        try:
            r = fn(ohlcv, None)
            if not r.empty:
                results.append(r)
        except Exception as e:
            logger.error(f"  ✗ {name}: {e}")

    if not results:
        return pd.DataFrame(columns=COLUMNS)

    df = pd.concat(results, ignore_index=True)
    df["direction"] = df["signal"].map(DIRECTION)
    return (
        df.sort_values(["signal", "strength"], ascending=[True, False])
          .reset_index(drop=True)[COLUMNS]
    )
