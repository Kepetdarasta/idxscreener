# =============================================================================
# src/signals/accumulation.py
# Sinyal AKUMULASI: Net buy asing >= Rp 200M dalam 5 hari, harga naik pelan
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
    Deteksi sinyal Akumulasi untuk semua ticker.

    Kriteria (semua harus terpenuhi):
    1. Net buy asing >= Rp 200 miliar dalam 5 hari  [cfg.ACCUM_NET_BUY_MIN]
    2. Perubahan harga 5 hari: -1% s/d +5%          [naik pelan, bukan melonjak]
    3. Volume tidak spike berlebihan (vol_ratio < 2) [akumulasi senyap]

    Catatan: jika data foreign flow tidak tersedia,
    kriteria #1 dilewati dan strength dikurangi 40 poin.

    Returns
    -------
    DataFrame kolom: ticker, signal, net_5d, change_5d, close,
                     volume, vol_ratio, strength, note
    Diurutkan: strength tertinggi dulu.
    """
    net_lookup = _build_net_lookup(foreign_flow)
    results    = []

    for ticker, df in ohlcv_data.items():
        row = _check(ticker, df, net_lookup)
        if row:
            results.append(row)

    if not results:
        logger.info("Akumulasi: tidak ada sinyal.")
        return pd.DataFrame()

    out = (
        pd.DataFrame(results)
        .sort_values("strength", ascending=False)
        .reset_index(drop=True)
    )
    logger.info(f"Akumulasi: {len(out)} sinyal — top: {list(out['ticker'][:3])}")
    return out


# -----------------------------------------------------------------------------
def _check(ticker: str, df: pd.DataFrame, net_lookup: dict) -> Optional[dict]:
    try:
        if len(df) < 6:
            return None

        last      = df.iloc[-1]
        change_5d = last.get("change_5d")
        vol_ratio = last.get("vol_ratio")
        net_5d    = net_lookup.get(ticker)   # None jika tidak ada data asing

        if pd.isna(change_5d):
            return None

        # --- FILTER HARGA: naik pelan -1% s/d +5% ---
        if not (cfg.ACCUM_PRICE_CHANGE_MIN <= change_5d <= cfg.ACCUM_PRICE_CHANGE_MAX):
            return None

        # --- FILTER NET BUY: wajib jika data tersedia ---
        if net_5d is not None and net_5d < cfg.ACCUM_NET_BUY_MIN:
            return None

        # --- FILTER VOLUME: tidak meledak (akumulasi sejati senyap) ---
        if vol_ratio is not None and not pd.isna(vol_ratio) and vol_ratio > 2.0:
            return None

        strength = _strength(net_5d, change_5d, vol_ratio)

        notes = []
        if net_5d is not None:
            notes.append(f"Net buy asing Rp {net_5d/1e9:+.1f}M")
        notes.append(f"Harga {change_5d*100:+.2f}% (5h)")
        if vol_ratio is not None and not pd.isna(vol_ratio):
            notes.append(f"Vol {vol_ratio:.2f}x avg")

        return {
            "ticker"   : ticker,
            "signal"   : "Akumulasi",
            "net_5d"   : net_5d,
            "change_5d": round(change_5d * 100, 2),
            "close"    : round(last["Close"], 0),
            "volume"   : int(last["Volume"]),
            "vol_ratio": round(vol_ratio, 2) if vol_ratio and not pd.isna(vol_ratio) else None,
            "strength" : strength,
            "note"     : " | ".join(notes),
        }
    except Exception as e:
        logger.debug(f"Akumulasi {ticker}: {e}")
        return None


def _strength(net_5d, change_5d, vol_ratio) -> float:
    """
    Skor 0–100. Komponen:
      50% → besarnya net buy asing
      30% → kualitas kenaikan harga (pelan & steady = lebih baik)
      20% → volume normal (akumulasi senyap = lebih baik)
    """
    s = 0.0

    # Net buy (50%)
    if net_5d is not None:
        s += min(net_5d / cfg.ACCUM_NET_BUY_MIN, 2.0) * 25   # max 50
    # else: data tidak ada, tidak dapat poin ini

    # Kualitas harga (30%) — ideal 1% s/d 3%, bukan 0% atau 5%
    if   0.01 <= change_5d <= 0.03: s += 30
    elif 0.00 <= change_5d <  0.01: s += 15
    elif 0.03 <  change_5d <= cfg.ACCUM_PRICE_CHANGE_MAX: s += 20
    elif cfg.ACCUM_PRICE_CHANGE_MIN <= change_5d < 0.00:  s += 10

    # Volume (20%) — vol normal 0.8x–1.3x = akumulasi senyap = ideal
    if vol_ratio is not None and not pd.isna(vol_ratio):
        if   0.8  <= vol_ratio <= 1.3: s += 20
        elif 1.3  <  vol_ratio <= 1.8: s += 12
        elif vol_ratio < 0.8:          s += 8

    return round(min(s, 100), 1)


def _build_net_lookup(foreign_flow: pd.DataFrame) -> dict:
    if foreign_flow.empty or "net_5d" not in foreign_flow.columns:
        return {}
    return foreign_flow.groupby("ticker")["net_5d"].last().to_dict()
