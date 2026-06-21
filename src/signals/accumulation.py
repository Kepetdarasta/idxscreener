# =============================================================================
# src/signals/accumulation.py — AKUMULASI
# Mode 1 (ada data asing): net buy >= Rp200M + harga naik pelan
# Mode 2 (tanpa data asing): harga naik pelan + volume normal (senyap)
# =============================================================================

import logging
from pathlib import Path
from typing import Dict, Optional
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg

logger = logging.getLogger(__name__)


def detect(ohlcv_data: Dict[str, pd.DataFrame], foreign_flow: pd.DataFrame) -> pd.DataFrame:
    net_lookup = _build_net_lookup(foreign_flow)
    has_foreign = bool(net_lookup)
    results = []

    for ticker, df in ohlcv_data.items():
        row = _check(ticker, df, net_lookup, has_foreign)
        if row:
            results.append(row)

    if not results:
        logger.info("Akumulasi: tidak ada sinyal.")
        return pd.DataFrame()

    out = pd.DataFrame(results).sort_values("strength", ascending=False).reset_index(drop=True)
    logger.info(f"Akumulasi: {len(out)} sinyal (mode: {'dengan' if has_foreign else 'tanpa'} data asing)")
    return out


def _check(ticker, df, net_lookup, has_foreign) -> Optional[dict]:
    try:
        if len(df) < 6:
            return None
        last      = df.iloc[-1]
        change_5d = last.get("change_5d")
        vol_ratio = last.get("vol_ratio")
        net_5d    = net_lookup.get(ticker)

        if pd.isna(change_5d):
            return None

        # Filter harga: naik pelan -1% s/d +5%
        if not (cfg.ACCUM_PRICE_CHANGE_MIN <= change_5d <= cfg.ACCUM_PRICE_CHANGE_MAX):
            return None

        # Filter net buy (hanya jika data asing tersedia)
        if has_foreign and net_5d is not None and net_5d < cfg.ACCUM_NET_BUY_MIN:
            return None

        # Filter volume: tidak meledak (akumulasi sejati senyap)
        if vol_ratio is not None and not pd.isna(vol_ratio) and vol_ratio > 2.0:
            return None

        strength = _strength(net_5d, change_5d, vol_ratio, has_foreign)

        notes = []
        if net_5d is not None:
            notes.append(f"Net buy asing Rp {net_5d/1e9:+.1f}M")
        elif not has_foreign:
            notes.append("⚠ Tanpa data asing")
        notes.append(f"Harga {change_5d*100:+.2f}% (5h)")
        if vol_ratio and not pd.isna(vol_ratio):
            notes.append(f"Vol {vol_ratio:.2f}x avg")

        return {
            "ticker"      : ticker,
            "signal"      : "Akumulasi",
            "data_asing"  : has_foreign,
            "net_5d"      : net_5d,
            "change_5d"   : round(change_5d * 100, 2),
            "close"       : round(last["Close"], 0),
            "volume"      : int(last["Volume"]),
            "vol_ratio"   : round(vol_ratio, 2) if vol_ratio and not pd.isna(vol_ratio) else None,
            "strength"    : strength,
            "note"        : " | ".join(notes),
        }
    except Exception as e:
        logger.debug(f"Akumulasi {ticker}: {e}")
        return None


def _strength(net_5d, change_5d, vol_ratio, has_foreign) -> float:
    s = 0.0
    if has_foreign:
        # Mode lengkap: 50% net buy, 30% harga, 20% volume
        if net_5d is not None:
            s += min(net_5d / cfg.ACCUM_NET_BUY_MIN, 2.0) * 25
        if   0.01 <= change_5d <= 0.03: s += 30
        elif 0.00 <= change_5d <  0.01: s += 15
        elif 0.03 <  change_5d <= cfg.ACCUM_PRICE_CHANGE_MAX: s += 20
        elif cfg.ACCUM_PRICE_CHANGE_MIN <= change_5d < 0: s += 10
        if vol_ratio and not pd.isna(vol_ratio):
            if   0.8 <= vol_ratio <= 1.3: s += 20
            elif 1.3 <  vol_ratio <= 1.8: s += 12
            elif vol_ratio < 0.8:         s += 8
    else:
        # Mode tanpa asing: 60% harga, 40% volume — skor dikap 70 (sinyal lebih lemah)
        if   0.01 <= change_5d <= 0.03: s += 36
        elif 0.00 <= change_5d <  0.01: s += 18
        elif 0.03 <  change_5d <= cfg.ACCUM_PRICE_CHANGE_MAX: s += 24
        elif cfg.ACCUM_PRICE_CHANGE_MIN <= change_5d < 0: s += 12
        if vol_ratio and not pd.isna(vol_ratio):
            if   0.8 <= vol_ratio <= 1.3: s += 40
            elif 1.3 <  vol_ratio <= 1.8: s += 24
            elif vol_ratio < 0.8:         s += 16
        s = min(s, 70)   # cap 70 tanpa konfirmasi asing

    return round(min(s, 100), 1)


def _build_net_lookup(foreign_flow):
    if foreign_flow.empty or "net_5d" not in foreign_flow.columns:
        return {}
    return foreign_flow.groupby("ticker")["net_5d"].last().to_dict()
