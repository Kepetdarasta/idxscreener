# =============================================================================
# src/signals/distribution.py
# Sinyal DISTRIBUSI: Net sell asing >= Rp 150M, harga stagnan, ritel dominan
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
    Deteksi sinyal Distribusi.

    Kriteria:
    1. Net sell asing <= -Rp 150 miliar dalam 5 hari  [cfg.DIST_NET_SELL_MIN]
    2. Harga stagnan atau sedikit turun: -10% s/d +2% [asing jual, ritel masih beli]
    3. Volume >= rata-rata (ritel masih aktif)         [vol_ratio >= 1.0]

    Sinyal distribusi adalah PERINGATAN bahaya — bandar/asing
    sedang melepas saham ke ritel yang tidak tahu.
    """
    net_lookup = _build_net_lookup(foreign_flow)
    results    = []

    for ticker, df in ohlcv_data.items():
        row = _check(ticker, df, net_lookup)
        if row:
            results.append(row)

    if not results:
        logger.info("Distribusi: tidak ada sinyal.")
        return pd.DataFrame()

    out = (
        pd.DataFrame(results)
        .sort_values("strength", ascending=False)
        .reset_index(drop=True)
    )
    logger.info(f"Distribusi: {len(out)} sinyal — top: {list(out['ticker'][:3])}")
    return out


# -----------------------------------------------------------------------------
def _check(ticker: str, df: pd.DataFrame, net_lookup: dict) -> Optional[dict]:
    try:
        if len(df) < 6:
            return None

        last      = df.iloc[-1]
        change_5d = last.get("change_5d")
        vol_ratio = last.get("vol_ratio")
        net_5d    = net_lookup.get(ticker)

        if pd.isna(change_5d):
            return None

        # --- FILTER HARGA: stagnan atau sedikit turun ---
        if not (cfg.DIST_PRICE_CHANGE_MIN <= change_5d <= cfg.DIST_PRICE_CHANGE_MAX):
            return None

        # --- FILTER NET SELL ---
        if net_5d is not None and net_5d > cfg.DIST_NET_SELL_MIN:
            return None

        # --- FILTER VOLUME: ritel masih aktif beli ---
        vol_ok = vol_ratio is not None and not pd.isna(vol_ratio) and vol_ratio >= 1.0

        strength = _strength(net_5d, change_5d, vol_ratio, vol_ok)

        notes = []
        if net_5d is not None:
            notes.append(f"Net sell asing Rp {net_5d/1e9:.1f}M")
        notes.append(f"Harga {change_5d*100:+.2f}% (5h)")
        if vol_ratio is not None and not pd.isna(vol_ratio):
            label = "⚠ ritel beli" if vol_ok else ""
            notes.append(f"Vol {vol_ratio:.2f}x avg {label}".strip())

        return {
            "ticker"   : ticker,
            "signal"   : "Distribusi",
            "net_5d"   : net_5d,
            "change_5d": round(change_5d * 100, 2),
            "close"    : round(last["Close"], 0),
            "volume"   : int(last["Volume"]),
            "vol_ratio": round(vol_ratio, 2) if vol_ratio and not pd.isna(vol_ratio) else None,
            "strength" : strength,
            "note"     : " | ".join(notes),
        }
    except Exception as e:
        logger.debug(f"Distribusi {ticker}: {e}")
        return None


def _strength(net_5d, change_5d, vol_ratio, vol_ok) -> float:
    """
    Skor 0–100. Semakin tinggi = semakin kuat sinyal bahaya distribusi.
      50% → besarnya net sell asing
      30% → harga stagnan (lebih bahaya dari sudah turun)
      20% → volume tinggi (ritel masih aktif masuk)
    """
    s = 0.0

    # Net sell (50%)
    if net_5d is not None and net_5d < 0:
        s += min(abs(net_5d) / abs(cfg.DIST_NET_SELL_MIN), 2.0) * 25

    # Stagnansi harga (30%) — stagnan lebih bahaya, harga belum drop tapi asing sudah kabur
    if  -0.01 <= change_5d <= 0.02: s += 30   # stagnan sempurna
    elif 0.02 <  change_5d <= cfg.DIST_PRICE_CHANGE_MAX: s += 15  # masih naik tipis
    elif cfg.DIST_PRICE_CHANGE_MIN <= change_5d < -0.01: s += 20  # sudah mulai turun

    # Volume (20%)
    if vol_ratio is not None and not pd.isna(vol_ratio):
        if   vol_ratio >= 1.5: s += 20
        elif vol_ratio >= 1.0: s += 12

    return round(min(s, 100), 1)


def _build_net_lookup(foreign_flow: pd.DataFrame) -> dict:
    if foreign_flow.empty or "net_5d" not in foreign_flow.columns:
        return {}
    return foreign_flow.groupby("ticker")["net_5d"].last().to_dict()
