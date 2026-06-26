# =============================================================================
# src/signals/markdown.py
# Sinyal MARK DOWN: Harga turun tajam + net sell asing berlanjut
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
    Deteksi sinyal Mark Down.

    Kriteria:
    1. Harga turun >= 5% dalam 3 hari   [cfg.MARKDOWN_PRICE_DROP_MIN]
    2. Net sell asing <= -Rp 50 miliar  [cfg.MARKDOWN_NET_SELL_MIN]
    3. Volume >= 1.2x rata-rata         [konfirmasi tekanan jual]

    Mark Down adalah fase paling berbahaya — asing sudah keluar,
    harga mulai free fall, ritel menjadi pihak yang menanggung kerugian.
    """
    net_lookup = _build_net_lookup(foreign_flow)
    results    = []

    for ticker, df in ohlcv_data.items():
        row = _check(ticker, df, net_lookup)
        if row:
            results.append(row)

    if not results:
        logger.info("Mark Down: tidak ada sinyal.")
        return pd.DataFrame()

    out = (
        pd.DataFrame(results)
        .sort_values("strength", ascending=False)
        .reset_index(drop=True)
    )
    logger.info(f"Mark Down: {len(out)} sinyal — top: {list(out['ticker'][:3])}")
    return out


# -----------------------------------------------------------------------------
def _check(ticker: str, df: pd.DataFrame, net_lookup: dict) -> Optional[dict]:
    try:
        if len(df) < 5:
            return None

        last      = df.iloc[-1]
        change_3d = last.get("change_3d")
        change_5d = last.get("change_5d")
        vol_ratio = last.get("vol_ratio")
        return_1d = last.get("return_1d")
        net_5d    = net_lookup.get(ticker)

        if change_3d is None or pd.isna(change_3d):
            return None

        # --- FILTER HARGA: turun >= 5% dalam 3 hari ---
        if change_3d > cfg.MARKDOWN_PRICE_DROP_MIN:
            return None

        # --- FILTER NET SELL ---
        if net_5d is not None and net_5d > cfg.MARKDOWN_NET_SELL_MIN:
            return None

        # --- FILTER VOLUME: konfirmasi tekanan jual ---
        vol_confirm = (
            vol_ratio is not None
            and not pd.isna(vol_ratio)
            and vol_ratio >= cfg.MARKDOWN_VOLUME_RATIO_MIN
        )

        strength = _strength(change_3d, net_5d, vol_ratio, return_1d)

        notes = [f"Harga {change_3d*100:+.2f}% (3h)"]
        if net_5d is not None:
            notes.append(f"Net sell asing Rp {net_5d/1e9:.1f}M")
        if vol_ratio is not None and not pd.isna(vol_ratio):
            notes.append(f"Vol {vol_ratio:.2f}x avg")
        if return_1d is not None and not pd.isna(return_1d) and return_1d <= -0.02:
            notes.append(f"Hari ini {return_1d*100:+.2f}%")

        return {
            "ticker"    : ticker,
            "signal"    : "Mark Down",
            "net_5d"    : net_5d,
            "change_3d" : round(change_3d * 100, 2),
            "change_5d" : round(change_5d * 100, 2) if change_5d and not pd.isna(change_5d) else None,
            "return_1d" : round(return_1d * 100, 2) if return_1d and not pd.isna(return_1d) else None,
            "close"     : round(last["Close"], 0),
            "volume"    : int(last["Volume"]),
            "vol_ratio" : round(vol_ratio, 2) if vol_ratio and not pd.isna(vol_ratio) else None,
            "vol_confirm": vol_confirm,
            "strength"  : strength,
            "note"      : " | ".join(notes),
        }
    except Exception as e:
        logger.debug(f"Mark Down {ticker}: {e}")
        return None


def _strength(change_3d, net_5d, vol_ratio, return_1d) -> float:
    """
    Skor 0–100. Semakin tinggi = semakin kuat tekanan jual.
      40% → magnitude penurunan harga
      35% → besarnya net sell asing
      15% → volume konfirmasi
      10% → momentum hari ini masih negatif
    """
    s = 0.0

    # Penurunan harga (40%)
    drop_ratio = abs(change_3d) / abs(cfg.MARKDOWN_PRICE_DROP_MIN)
    s += min(drop_ratio, 2.0) * 20

    # Net sell (35%)
    if net_5d is not None and net_5d < 0:
        sell_ratio = abs(net_5d) / abs(cfg.MARKDOWN_NET_SELL_MIN)
        s += min(sell_ratio, 2.0) * 17.5

    # Volume (15%)
    if vol_ratio is not None and not pd.isna(vol_ratio):
        if   vol_ratio >= 2.0: s += 15
        elif vol_ratio >= 1.2: s += 10

    # Momentum hari ini (10%)
    if return_1d is not None and not pd.isna(return_1d) and return_1d <= -0.02:
        s += 10

    return round(min(s, 100), 1)


def _build_net_lookup(foreign_flow: pd.DataFrame) -> dict:
    if foreign_flow.empty or "net_5d" not in foreign_flow.columns:
        return {}
    return foreign_flow.groupby("ticker")["net_5d"].last().to_dict()
