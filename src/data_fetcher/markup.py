# =============================================================================
# src/signals/markup.py
# Sinyal MARK UP: Volume melonjak + harga breakout
# =============================================================================

import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg

logger = logging.getLogger(__name__)


def detect(
    ohlcv_data: Dict[str, pd.DataFrame],
    foreign_flow: pd.DataFrame,
) -> pd.DataFrame:
    """
    Deteksi sinyal Mark Up.

    Kriteria (semua harus terpenuhi):
    1. Volume >= 1.5x rata-rata 20 hari  [vol_ratio >= cfg.MARKUP_VOLUME_RATIO_MIN]
    2. Salah satu breakout:
       a. Return harian >= +3%           [cfg.MARKUP_PRICE_BREAKOUT]
       b. Close > High tertinggi 5 hari sebelumnya

    Net buy asing bukan filter wajib, tapi menaikkan strength jika ada.
    """
    net_lookup = _build_net_lookup(foreign_flow)
    results    = []

    for ticker, df in ohlcv_data.items():
        row = _check(ticker, df, net_lookup)
        if row:
            results.append(row)

    if not results:
        logger.info("Mark Up: tidak ada sinyal.")
        return pd.DataFrame()

    out = (
        pd.DataFrame(results)
        .sort_values("strength", ascending=False)
        .reset_index(drop=True)
    )
    logger.info(f"Mark Up: {len(out)} sinyal — top: {list(out['ticker'][:3])}")
    return out


# -----------------------------------------------------------------------------
def _check(ticker: str, df: pd.DataFrame, net_lookup: dict) -> Optional[dict]:
    try:
        if len(df) < cfg.MARKUP_VOLUME_AVG_WINDOW + 2:
            return None

        last      = df.iloc[-1]
        prev      = df.iloc[-2]
        vol_ratio = last.get("vol_ratio")
        return_1d = last.get("return_1d")
        high_5d   = prev.get("high_5d")   # high 5h sebelum hari ini (sudah shift di fetcher)
        net_5d    = net_lookup.get(ticker)

        if vol_ratio is None or pd.isna(vol_ratio): return None
        if return_1d is None or pd.isna(return_1d): return None

        # --- FILTER VOLUME: wajib spike ---
        if vol_ratio < cfg.MARKUP_VOLUME_RATIO_MIN:
            return None

        # --- FILTER BREAKOUT: salah satu ---
        price_jump = return_1d >= cfg.MARKUP_PRICE_BREAKOUT
        breakout   = (
            high_5d is not None
            and not pd.isna(high_5d)
            and last["Close"] > high_5d
        )
        if not (price_jump or breakout):
            return None

        strength = _strength(vol_ratio, return_1d, price_jump, breakout, net_5d)

        notes = [f"Vol {vol_ratio:.2f}x avg"]
        if price_jump:
            notes.append(f"Harga {return_1d*100:+.2f}% hari ini")
        if breakout:
            notes.append(f"Breakout high {cfg.MARKUP_BREAKOUT_WINDOW}h")
        if net_5d is not None and net_5d > 0:
            notes.append(f"Net buy asing Rp {net_5d/1e9:.1f}M")

        return {
            "ticker"    : ticker,
            "signal"    : "Mark Up",
            "net_5d"    : net_5d,
            "return_1d" : round(return_1d * 100, 2),
            "change_5d" : round(last.get("change_5d", 0) * 100, 2),
            "close"     : round(last["Close"], 0),
            "volume"    : int(last["Volume"]),
            "vol_ratio" : round(vol_ratio, 2),
            "breakout"  : breakout,
            "price_jump": price_jump,
            "strength"  : strength,
            "note"      : " | ".join(notes),
        }
    except Exception as e:
        logger.debug(f"Mark Up {ticker}: {e}")
        return None


def _strength(vol_ratio, return_1d, price_jump, breakout, net_5d) -> float:
    """
    Skor 0–100:
      40% → besarnya volume spike
      30% → kualitas breakout (double confirm lebih tinggi)
      20% → magnitude kenaikan harga
      10% → konfirmasi net buy asing
    """
    s = 0.0

    # Volume (40%)
    s += min(vol_ratio / cfg.MARKUP_VOLUME_RATIO_MIN, 3.0) * (40 / 3)

    # Breakout (30%)
    if price_jump and breakout: s += 30
    elif price_jump:            s += 20
    elif breakout:              s += 15

    # Magnitude harga (20%)
    if   return_1d >= 0.07: s += 20
    elif return_1d >= 0.05: s += 15
    elif return_1d >= 0.03: s += 10

    # Net buy asing konfirmasi (10%)
    if net_5d is not None and net_5d > 0:
        s += 10

    return round(min(s, 100), 1)


def _build_net_lookup(foreign_flow: pd.DataFrame) -> dict:
    if foreign_flow.empty or "net_5d" not in foreign_flow.columns:
        return {}
    return foreign_flow.groupby("ticker")["net_5d"].last().to_dict()
