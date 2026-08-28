# =============================================================================
# src/signals/accumulation.py — Stage 1: deteksi saham dalam fase akumulasi
#
# VERSI BARU (tanpa foreign flow). Kriteria:
#   1. Volatilitas menyempit  — BB width sekarang ada di persentil rendah
#      dibanding histori (khas konsolidasi sebelum breakout)
#   2. OBV naik               — slope positif selama window akumulasi,
#      proxy tekanan beli bersih (pengganti foreign flow)
#   3. Volume dry-up          — opsional, menambah skor strength
#
# Signature detect(ohlcv, foreign_flow) dipertahankan supaya kompatibel
# dengan screener.py (SIGNAL_FUNCS memanggil semua fn dengan argumen sama).
# foreign_flow tidak lagi dipakai di sini.
# =============================================================================

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg
from src.signals import indicators

logger = logging.getLogger(__name__)


def detect(ohlcv: dict, foreign_flow: pd.DataFrame = None) -> pd.DataFrame:
    """
    ohlcv: dict[ticker] -> DataFrame(index=tanggal, columns=[Open,High,Low,Close,Volume])
    Return DataFrame kolom: ticker, close, strength, note, signal ('Akumulasi')
    """
    rows = []
    window = cfg.ACCUM_WINDOW_DAYS_V2
    min_len = max(window, cfg.ACCUM_BB_PERIOD, cfg.ACCUM_BB_LOOKBACK_DAYS) + 5

    for ticker, df in ohlcv.items():
        if df is None or len(df) < min_len:
            continue

        width_series = indicators.bb_width(df, cfg.ACCUM_BB_PERIOD)
        width_now = width_series.iloc[-1]
        width_history = width_series.tail(cfg.ACCUM_BB_LOOKBACK_DAYS).dropna()

        if width_history.empty or pd.isna(width_now):
            continue

        # Persentil width sekarang dibanding histori — makin rendah, makin ketat kontraksinya
        percentile = (width_history < width_now).mean()
        is_contracting = percentile <= cfg.ACCUM_BB_PERCENTILE_MAX

        slope = indicators.obv_slope(df, window)
        is_obv_rising = slope > 0

        if not (is_contracting and is_obv_rising):
            continue

        vol_ratio_now = indicators.volume_ratio(df, cfg.ACCUM_BB_PERIOD).iloc[-1]
        is_volume_dryup = pd.notna(vol_ratio_now) and vol_ratio_now < 1.0

        # Strength 0-10: dasar 6 kalau lolos syarat utama, ditambah bonus
        strength = 6.0 + (1 - percentile) * 2.0
        if is_volume_dryup:
            strength += 1.5
        strength = round(min(10.0, strength), 1)

        close = float(df["Close"].iloc[-1])
        note = f"BB width persentil {percentile:.0%}, OBV slope naik"
        if is_volume_dryup:
            note += ", volume dry-up"

        rows.append({
            "ticker": ticker,
            "close": close,
            "strength": strength,
            "note": note,
            "signal": "Akumulasi",
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("strength", ascending=False).reset_index(drop=True)
    return result
