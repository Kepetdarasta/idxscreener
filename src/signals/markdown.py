# =============================================================================
# src/signals/markdown.py — MARK DOWN (murni harga + volume)
# Kriteria: harga turun >= 5% dalam 3 hari + volume di atas rata-rata
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
        logger.info("Mark Down: tidak ada sinyal.")
        return pd.DataFrame()

    out = pd.DataFrame(results).sort_values("strength", ascending=False).reset_index(drop=True)
    logger.info(f"Mark Down: {len(out)} sinyal")
    return out


def _check(ticker, df) -> Optional[dict]:
    try:
        if len(df) < 5:
            return None
        last      = df.iloc[-1]
        change_3d = last.get("change_3d")
        change_5d = last.get("change_5d")
        vol_ratio = last.get("vol_ratio")
        return_1d = last.get("return_1d")

        if change_3d is None or pd.isna(change_3d):
            return None

        # Wajib turun >= 5% dalam 3 hari
        if change_3d > cfg.MARKDOWN_PRICE_DROP_MIN:
            return None

        # Wajib ada konfirmasi volume
        if vol_ratio is None or pd.isna(vol_ratio) or vol_ratio < cfg.MARKDOWN_VOLUME_RATIO_MIN:
            return None

        strength = _strength(change_3d, vol_ratio, return_1d)

        notes = [f"Harga {change_3d*100:+.2f}% (3h)", f"Vol {vol_ratio:.2f}x avg"]
        if return_1d is not None and not pd.isna(return_1d) and return_1d <= -0.02:
            notes.append(f"Hari ini {return_1d*100:+.2f}%")

        return {
            "ticker"   : ticker,
            "signal"   : "Mark Down",
            "change_3d": round(change_3d * 100, 2),
            "change_5d": round(change_5d * 100, 2) if change_5d is not None and not pd.isna(change_5d) else None,
            "return_1d": round(return_1d * 100, 2) if return_1d is not None and not pd.isna(return_1d) else None,
            "close"    : round(last["Close"], 0),
            "volume"   : int(last["Volume"]),
            "vol_ratio": round(vol_ratio, 2),
            "strength" : strength,
            "note"     : " | ".join(notes),
        }
    except Exception as e:
        logger.debug(f"Mark Down {ticker}: {e}")
        return None


def _strength(change_3d, vol_ratio, return_1d) -> float:
    """Skala 0-10: 60% penurunan harga, 30% volume, 10% momentum hari ini."""
    drop_ratio = abs(change_3d) / abs(cfg.MARKDOWN_PRICE_DROP_MIN)
    s = min(drop_ratio, 2.0) * 30
    if   vol_ratio >= 2.0: s += 30
    elif vol_ratio >= 1.2: s += 20
    if return_1d is not None and not pd.isna(return_1d) and return_1d <= -0.02:
        s += 10
    return round(min(s, 100) / 10, 1)
