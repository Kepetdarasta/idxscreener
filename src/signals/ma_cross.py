# =============================================================================
# src/signals/ma_cross.py — Deteksi Golden Cross / Death Cross (MA5 x MA20)
#
# Mengikuti pola detect(ohlcv, foreign_flow) -> DataFrame seperti
# accumulation.py / markup.py, sehingga bisa langsung didaftarkan ke
# SIGNAL_FUNCS di src/signals/screener.py.
#
# ohlcv    : dict[ticker] -> DataFrame dengan kolom Open, High, Low, Close, Volume
#            (index atau kolom tanggal terurut naik)
# foreign_flow : tidak dipakai di sini, tapi tetap diterima agar signature
#                konsisten dengan sinyal ADMD lain (dipanggil seragam oleh screener).
# =============================================================================

import logging
from typing import Dict

import pandas as pd

try:
    import config as cfg
except ImportError:
    cfg = None

logger = logging.getLogger(__name__)

# --- Parameter (bisa dioverride lewat config.py: MA_CROSS_FAST, MA_CROSS_SLOW, dst.) ---
MA_FAST_WINDOW  = getattr(cfg, "MA_CROSS_FAST", 5)
MA_SLOW_WINDOW  = getattr(cfg, "MA_CROSS_SLOW", 20)
MIN_HISTORY_DAYS = getattr(cfg, "MA_CROSS_MIN_HISTORY", MA_SLOW_WINDOW + 5)

SIGNAL_GOLDEN = "MA_Golden_Cross"
SIGNAL_DEATH  = "MA_Death_Cross"


def _compute_ma(df: pd.DataFrame) -> pd.DataFrame:
    """Hitung MA cepat & lambat, sort by tanggal naik dulu."""
    out = df.sort_index().copy()
    out["ma_fast"] = out["Close"].rolling(MA_FAST_WINDOW).mean()
    out["ma_slow"] = out["Close"].rolling(MA_SLOW_WINDOW).mean()
    return out


def _score_strength(gap_pct: float) -> float:
    """
    Skor 0-10 berdasarkan seberapa besar jarak MA fast vs MA slow saat crossover.
    Crossover dengan gap lebih lebar dianggap lebih meyakinkan (bukan noise tipis).
    """
    strength = 5.0 + min(abs(gap_pct) * 100, 5.0)  # base 5, tambah maks 5
    return round(min(10.0, max(0.0, strength)), 1)


def detect(ohlcv: Dict[str, pd.DataFrame], foreign_flow: pd.DataFrame = None) -> pd.DataFrame:
    """
    Deteksi Golden Cross (MA fast memotong ke atas MA slow) dan
    Death Cross (MA fast memotong ke bawah MA slow) pada hari terakhir data.

    Return DataFrame kolom: ticker, signal, close, strength, note
    """
    rows = []

    for ticker, df in (ohlcv or {}).items():
        if df is None or df.empty:
            continue
        if len(df) < MIN_HISTORY_DAYS:
            logger.debug(f"  {ticker}: skip MA cross — histori kurang ({len(df)} < {MIN_HISTORY_DAYS} hari)")
            continue
        if "Close" not in df.columns:
            continue

        try:
            d = _compute_ma(df)
            if d[["ma_fast", "ma_slow"]].iloc[-2:].isna().any().any():
                # MA belum terbentuk penuh di 2 hari terakhir (histori terlalu pendek)
                continue

            fast_today, slow_today = d["ma_fast"].iloc[-1], d["ma_slow"].iloc[-1]
            fast_prev,  slow_prev  = d["ma_fast"].iloc[-2], d["ma_slow"].iloc[-2]
            close_today = float(d["Close"].iloc[-1])

            golden = (fast_prev <= slow_prev) and (fast_today > slow_today)
            death  = (fast_prev >= slow_prev) and (fast_today < slow_today)

            if not golden and not death:
                continue

            gap_pct = (fast_today - slow_today) / slow_today if slow_today else 0.0
            signal = SIGNAL_GOLDEN if golden else SIGNAL_DEATH
            note = (
                f"MA{MA_FAST_WINDOW} {'memotong ke atas' if golden else 'memotong ke bawah'} "
                f"MA{MA_SLOW_WINDOW} (gap {gap_pct*100:.2f}%)"
            )

            rows.append({
                "ticker":   ticker.upper(),
                "signal":   signal,
                "close":    close_today,
                "strength": _score_strength(gap_pct),
                "note":     note,
            })

        except Exception as e:
            logger.warning(f"  {ticker}: error hitung MA cross — {e}")
            continue

    result = pd.DataFrame(rows, columns=["ticker", "signal", "close", "strength", "note"])
    logger.info(f"MA Cross: {len(result)} sinyal ditemukan "
                f"({(result['signal'] == SIGNAL_GOLDEN).sum()} golden, "
                f"{(result['signal'] == SIGNAL_DEATH).sum()} death)")
    return result
