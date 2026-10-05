# =============================================================================
# src/signals/distribution.py — DISTRIBUSI (murni harga + volume)
# Kriteria: harga stagnan / turun tipis (5 hari) + volume masih ramai
#           (proxy: ritel masih aktif membeli sementara bandar keluar)
# =============================================================================

import logging
from pathlib import Path
from typing import Dict, Optional
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg

logger = logging.getLogger(__name__)


def detect(ohlcv_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    results = []
    for ticker, df in ohlcv_data.items():
        row = _check(ticker, df)
        if row:
            results.append(row)

    if not results:
        logger.info("Distribusi: tidak ada sinyal.")
        return pd.DataFrame()

    out = pd.DataFrame(results).sort_values("strength", ascending=False).reset_index(drop=True)
    logger.info(f"Distribusi: {len(out)} sinyal")
    return out


def _check(ticker, df) -> Optional[dict]:
    try:
        if len(df) < 6:
            return None
        last      = df.iloc[-1]
        change_5d = last.get("change_5d")
        vol_ratio = last.get("vol_ratio")

        if change_5d is None or pd.isna(change_5d):
            return None

        # Filter harga: stagnan atau sedikit turun
        if not (cfg.DIST_PRICE_CHANGE_MIN <= change_5d <= cfg.DIST_PRICE_CHANGE_MAX):
            return None

        # Volume harus masih ramai (>= rata-rata)
        vol_ok = vol_ratio is not None and not pd.isna(vol_ratio) and vol_ratio >= 1.0
        if not vol_ok:
            return None

        strength = _strength(change_5d, vol_ratio)
        notes = [f"Harga {change_5d*100:+.2f}% (5h)", f"Vol {vol_ratio:.2f}x avg"]

        return {
            "ticker"   : ticker,
            "signal"   : "Distribusi",
            "change_5d": round(change_5d * 100, 2),
            "close"    : round(last["Close"], 0),
            "volume"   : int(last["Volume"]),
            "vol_ratio": round(vol_ratio, 2),
            "strength" : strength,
            "note"     : " | ".join(notes),
        }
    except Exception as e:
        logger.debug(f"Distribusi {ticker}: {e}")
        return None


def _strength(change_5d, vol_ratio) -> float:
    """Skor skala 0-10 (sama dengan Akumulasi/Mark Up), maks 6.5."""
    s = 0.0
    if   -0.01 <= change_5d <= 0.02:                         s += 50
    elif cfg.DIST_PRICE_CHANGE_MIN <= change_5d < -0.01:     s += 35
    if   vol_ratio >= 1.5: s += 30
    elif vol_ratio >= 1.0: s += 15
    return round(min(s, 65) / 10, 1)
