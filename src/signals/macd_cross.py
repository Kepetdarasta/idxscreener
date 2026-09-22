# =============================================================================
# src/signals/macd_cross.py — Deteksi MACD Bullish/Bearish Crossover
#
# Mengikuti pola detect(ohlcv, foreign_flow) -> DataFrame seperti
# accumulation.py / markup.py, sehingga bisa langsung didaftarkan ke
# SIGNAL_FUNCS di src/signals/screener.py.
#
# MACD standar (12, 26, 9):
#   macd_line   = EMA(12) - EMA(26)
#   signal_line = EMA(9) dari macd_line
#   Bullish cross : macd_line memotong ke atas signal_line
#   Bearish cross : macd_line memotong ke bawah signal_line
#
# ohlcv : dict[ticker] -> DataFrame dengan kolom Open, High, Low, Close, Volume
# =============================================================================

import logging
from typing import Dict

import pandas as pd

try:
    import config as cfg
except ImportError:
    cfg = None

logger = logging.getLogger(__name__)

# --- Parameter (override lewat config.py: MACD_FAST, MACD_SLOW, MACD_SIGNAL) ---
MACD_FAST   = getattr(cfg, "MACD_FAST", 12)
MACD_SLOW   = getattr(cfg, "MACD_SLOW", 26)
MACD_SIGNAL = getattr(cfg, "MACD_SIGNAL", 9)

# EMA26 + EMA9 signal line butuh histori lebih panjang biar tidak bias oleh
# efek "pemanasan" EMA di awal deret data. Aturan umum: minimal slow + signal + buffer.
MIN_HISTORY_DAYS = getattr(cfg, "MACD_MIN_HISTORY", MACD_SLOW + MACD_SIGNAL + 10)

SIGNAL_BULLISH = "MACD_Bullish_Cross"
SIGNAL_BEARISH = "MACD_Bearish_Cross"


def _compute_macd(df: pd.DataFrame) -> pd.DataFrame:
    """Hitung MACD line, signal line, dan histogram. Sort by tanggal naik dulu."""
    out = df.sort_index().copy()
    ema_fast = out["Close"].ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = out["Close"].ewm(span=MACD_SLOW, adjust=False).mean()
    out["macd_line"]   = ema_fast - ema_slow
    out["signal_line"] = out["macd_line"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    out["histogram"]   = out["macd_line"] - out["signal_line"]
    return out


def _score_strength(hist_today: float, close: float) -> float:
    """
    Skor 0-10 berdasarkan besar histogram (macd_line - signal_line) relatif
    terhadap harga saham, dinormalisasi kasar sebagai proxy momentum crossover.
    """
    if not close:
        return 5.0
    rel = abs(hist_today) / close
    strength = 5.0 + min(rel * 500, 5.0)  # base 5, tambah maks 5
    return round(min(10.0, max(0.0, strength)), 1)


def detect(ohlcv: Dict[str, pd.DataFrame], foreign_flow: pd.DataFrame = None) -> pd.DataFrame:
    """
    Deteksi MACD Bullish Cross (macd_line memotong ke atas signal_line) dan
    Bearish Cross (macd_line memotong ke bawah signal_line) pada hari terakhir.

    Return DataFrame kolom: ticker, signal, close, strength, note
    """
    rows = []

    for ticker, df in (ohlcv or {}).items():
        if df is None or df.empty:
            continue
        if len(df) < MIN_HISTORY_DAYS:
            logger.debug(f"  {ticker}: skip MACD cross — histori kurang ({len(df)} < {MIN_HISTORY_DAYS} hari)")
            continue
        if "Close" not in df.columns:
            continue

        try:
            d = _compute_macd(df)
            if d[["macd_line", "signal_line"]].iloc[-2:].isna().any().any():
                continue

            macd_today, sig_today = d["macd_line"].iloc[-1], d["signal_line"].iloc[-1]
            macd_prev,  sig_prev  = d["macd_line"].iloc[-2], d["signal_line"].iloc[-2]
            hist_today  = d["histogram"].iloc[-1]
            close_today = float(d["Close"].iloc[-1])

            bullish = (macd_prev <= sig_prev) and (macd_today > sig_today)
            bearish = (macd_prev >= sig_prev) and (macd_today < sig_today)

            if not bullish and not bearish:
                continue

            signal = SIGNAL_BULLISH if bullish else SIGNAL_BEARISH
            note = (
                f"MACD({MACD_FAST},{MACD_SLOW},{MACD_SIGNAL}) "
                f"{'memotong ke atas' if bullish else 'memotong ke bawah'} signal line "
                f"(hist {hist_today:.2f})"
            )

            rows.append({
                "ticker":   ticker.upper(),
                "signal":   signal,
                "close":    close_today,
                "strength": _score_strength(hist_today, close_today),
                "note":     note,
            })

        except Exception as e:
            logger.warning(f"  {ticker}: error hitung MACD cross — {e}")
            continue

    result = pd.DataFrame(rows, columns=["ticker", "signal", "close", "strength", "note"])
    logger.info(f"MACD Cross: {len(result)} sinyal ditemukan "
                f"({(result['signal'] == SIGNAL_BULLISH).sum()} bullish, "
                f"{(result['signal'] == SIGNAL_BEARISH).sum()} bearish)")
    return result
