# =============================================================================
# src/signals/indicators.py — Indikator teknikal bersama
#
# Dipakai oleh accumulation.py (Stage 1), markup.py (Stage 2), dan
# risk_manager.py (Stage 3). Semua berbasis OHLCV murni — tidak ada yang
# butuh data foreign flow.
# =============================================================================

import pandas as pd


def obv(df: pd.DataFrame) -> pd.Series:
    """
    On-Balance Volume — volume dikumulatifkan dengan tanda sesuai arah harga.
    Proxy tekanan beli/jual bersih dari SEMUA pelaku pasar (bukan cuma asing),
    dipakai sebagai pengganti foreign flow.
    """
    direction = df["Close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * df["Volume"]).cumsum()


def obv_slope(df: pd.DataFrame, window: int) -> float:
    """
    Slope OBV (regresi linear sederhana) selama `window` hari terakhir.
    Positif = tekanan beli bersih meningkat (indikasi akumulasi diam-diam).
    """
    o = obv(df).tail(window)
    if len(o) < window:
        return 0.0

    x_vals = list(range(len(o)))
    x_mean = sum(x_vals) / len(x_vals)
    y_mean = o.mean()

    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, o))
    den = sum((x - x_mean) ** 2 for x in x_vals)

    return num / den if den else 0.0


def bb_width(df: pd.DataFrame, period: int = 20, num_std: float = 2.0) -> pd.Series:
    """
    Bollinger Band width = (upper - lower) / middle.
    Nilai kecil = volatilitas menyempit (khas fase akumulasi/konsolidasi).
    """
    mid = df["Close"].rolling(period).mean()
    std = df["Close"].rolling(period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return (upper - lower) / mid


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range — dipakai untuk buffer stop loss di Stage 3."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def volume_ratio(df: pd.DataFrame, window: int) -> pd.Series:
    """Volume hari ini dibagi rata-rata volume `window` hari — deteksi lonjakan/dry-up."""
    avg = df["Volume"].rolling(window).mean()
    return df["Volume"] / avg
