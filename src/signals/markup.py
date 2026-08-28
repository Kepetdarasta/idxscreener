# =============================================================================
# src/signals/markup.py — Stage 2: deteksi trigger breakout ("mulai bergerak")
#
# VERSI BARU (tanpa foreign flow). Breakout hanya dianggap valid kalau saham
# tsb SUDAH lolos Stage 1 (accumulation.detect) — supaya breakout yang
# dihitung memang keluar dari fase akumulasi, bukan breakout acak dari
# saham yang sedang trending liar tanpa fase konsolidasi.
#
# Kriteria trigger:
#   1. Breakout   — close hari ini > resistance (high tertinggi N hari sebelumnya)
#   2. Volume     — volume ratio >= MARKUP_VOLUME_RATIO_MIN (konfirmasi tenaga beli nyata)
#   3. OBV        — OBV hari ini bikin high baru (konfirmasi bukan fakeout)
#
# Parameter MARKUP_* diambil dari config.py yang sudah ada (tidak ada
# parameter baru yang perlu ditambahkan untuk Stage 2 ini).
# =============================================================================

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg
from src.signals import indicators, accumulation

logger = logging.getLogger(__name__)


def detect(ohlcv: dict, foreign_flow: pd.DataFrame = None) -> pd.DataFrame:
    """
    ohlcv: dict[ticker] -> DataFrame(index=tanggal, columns=[Open,High,Low,Close,Volume])
    Return DataFrame kolom: ticker, close, strength, note, signal ('Mark Up')
    """
    accumulated = accumulation.detect(ohlcv, foreign_flow)
    if accumulated.empty:
        return pd.DataFrame()

    accumulated_tickers = set(accumulated["ticker"])
    rows = []
    min_len = cfg.MARKUP_BREAKOUT_WINDOW + cfg.MARKUP_VOLUME_AVG_WINDOW + 1

    for ticker in accumulated_tickers:
        df = ohlcv.get(ticker)
        if df is None or len(df) < min_len:
            continue

        # Resistance = high tertinggi N hari SEBELUM hari ini (exclude hari ini sendiri)
        resistance = df["High"].iloc[-(cfg.MARKUP_BREAKOUT_WINDOW + 1):-1].max()
        close_today = float(df["Close"].iloc[-1])
        is_breakout = close_today > resistance

        vol_ratio = indicators.volume_ratio(df, cfg.MARKUP_VOLUME_AVG_WINDOW).iloc[-1]
        is_volume_confirmed = pd.notna(vol_ratio) and vol_ratio >= cfg.MARKUP_VOLUME_RATIO_MIN

        obv_series = indicators.obv(df)
        obv_now = obv_series.iloc[-1]
        obv_recent_max = obv_series.iloc[-(cfg.MARKUP_BREAKOUT_WINDOW + 1):-1].max()
        is_obv_confirmed = obv_now >= obv_recent_max

        if not (is_breakout and is_volume_confirmed and is_obv_confirmed):
            continue

        strength = 7.0 + min(2.0, vol_ratio - cfg.MARKUP_VOLUME_RATIO_MIN)
        strength = round(min(10.0, strength), 1)

        note = f"Breakout resistance {resistance:.0f}, volume {vol_ratio:.1f}x, OBV konfirmasi"

        rows.append({
            "ticker": ticker,
            "close": close_today,
            "strength": strength,
            "note": note,
            "signal": "Mark Up",
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("strength", ascending=False).reset_index(drop=True)
    return result
