# =============================================================================
# src/signals/distribution.py — DISTRIBUSI
# Mode 1 (ada asing): net sell >= Rp150M + harga stagnan + vol tinggi
# Mode 2 (tanpa asing): harga stagnan + volume spike (ritel masih aktif beli)
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
    net_lookup  = _build_net_lookup(foreign_flow)
    has_foreign = bool(net_lookup)
    results     = []

    for ticker, df in ohlcv_data.items():
        row = _check(ticker, df, net_lookup, has_foreign)
        if row:
            results.append(row)

    if not results:
        logger.info("Distribusi: tidak ada sinyal.")
        return pd.DataFrame()

    out = pd.DataFrame(results).sort_values("strength", ascending=False).reset_index(drop=True)
    logger.info(f"Distribusi: {len(out)} sinyal (mode: {'dengan' if has_foreign else 'tanpa'} data asing)")
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

        # Filter harga: stagnan atau sedikit turun
        if not (cfg.DIST_PRICE_CHANGE_MIN <= change_5d <= cfg.DIST_PRICE_CHANGE_MAX):
            return None

        # Filter net sell (hanya jika data asing tersedia)
        if has_foreign and net_5d is not None and net_5d > cfg.DIST_NET_SELL_MIN:
            return None

        # Tanpa data asing: butuh volume spike sebagai proxy "ritel masih beli"
        vol_ok = vol_ratio is not None and not pd.isna(vol_ratio) and vol_ratio >= 1.0
        if not has_foreign and not vol_ok:
            return None

        strength = _strength(net_5d, change_5d, vol_ratio, has_foreign)

        notes = []
        if net_5d is not None:
            notes.append(f"Net sell asing Rp {net_5d/1e9:.1f}M")
        elif not has_foreign:
            notes.append("⚠ Tanpa data asing")
        notes.append(f"Harga {change_5d*100:+.2f}% (5h)")
        if vol_ratio and not pd.isna(vol_ratio):
            notes.append(f"Vol {vol_ratio:.2f}x avg" + (" ⚠ ritel beli" if vol_ok else ""))

        return {
            "ticker"    : ticker,
            "signal"    : "Distribusi",
            "data_asing": has_foreign,
            "net_5d"    : net_5d,
            "change_5d" : round(change_5d * 100, 2),
            "close"     : round(last["Close"], 0),
            "volume"    : int(last["Volume"]),
            "vol_ratio" : round(vol_ratio, 2) if vol_ratio and not pd.isna(vol_ratio) else None,
            "strength"  : strength,
            "note"      : " | ".join(notes),
        }
    except Exception as e:
        logger.debug(f"Distribusi {ticker}: {e}")
        return None


def _strength(net_5d, change_5d, vol_ratio, has_foreign) -> float:
    s = 0.0
    if has_foreign:
        if net_5d is not None and net_5d < 0:
            s += min(abs(net_5d) / abs(cfg.DIST_NET_SELL_MIN), 2.0) * 25
        if  -0.01 <= change_5d <= 0.02: s += 30
        elif 0.02 < change_5d <= cfg.DIST_PRICE_CHANGE_MAX: s += 15
        elif cfg.DIST_PRICE_CHANGE_MIN <= change_5d < -0.01: s += 20
        if vol_ratio and not pd.isna(vol_ratio):
            if   vol_ratio >= 1.5: s += 20
            elif vol_ratio >= 1.0: s += 12
    else:
        # Tanpa asing: 50% harga stagnan, 50% volume — cap 65
        if  -0.01 <= change_5d <= 0.02: s += 50
        elif cfg.DIST_PRICE_CHANGE_MIN <= change_5d < -0.01: s += 35
        if vol_ratio and not pd.isna(vol_ratio):
            if   vol_ratio >= 1.5: s += 30
            elif vol_ratio >= 1.0: s += 15
        s = min(s, 65)

    return round(min(s, 100), 1)


def _build_net_lookup(foreign_flow):
    if foreign_flow.empty or "net_5d" not in foreign_flow.columns:
        return {}
    return foreign_flow.groupby("ticker")["net_5d"].last().to_dict()
