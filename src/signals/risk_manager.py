# =============================================================================
# src/signals/risk_manager.py — Stage 3: Trade Setup (Risk Management)
#
# Dipanggil setelah Stage 2 (breakout/"Mark Up") terdeteksi di screener.
# Menghitung entry, stop loss, target, dan risk:reward ratio berbasis
# tinggi range akumulasi + ATR — tanpa perlu data foreign flow.
#
# ASUMSI STRUKTUR DATA:
#   ohlcv adalah dict: { "BBCA": DataFrame(index=tanggal, columns=[Open,High,Low,Close,Volume]), ... }
#   Ini mengikuti struktur yang dipakai src/data_fetcher/yfinance_fetcher.py.
#   Kalau struktur aktual berbeda (misal MultiIndex atau nama kolom lower-case),
#   sesuaikan get_ohlcv_for_ticker() di bawah — sisanya tidak perlu diubah.
# =============================================================================

import logging
from typing import Dict, Optional

import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER — akses OHLCV per ticker (sesuaikan jika struktur data berbeda)
# =============================================================================

def get_ohlcv_for_ticker(ohlcv: Dict[str, pd.DataFrame], ticker: str) -> Optional[pd.DataFrame]:
    df = ohlcv.get(ticker)
    if df is None or df.empty:
        return None
    return df


# =============================================================================
# RANGE & ATR
# =============================================================================

def compute_range(df: pd.DataFrame, lookback_days: int) -> tuple[float, float]:
    """
    Ambil high tertinggi & low terendah selama `lookback_days` terakhir
    (window sebelum breakout) — merepresentasikan tinggi range akumulasi.
    """
    window = df.tail(lookback_days)
    range_high = float(window["High"].max())
    range_low = float(window["Low"].min())
    return range_high, range_low


def compute_atr(df: pd.DataFrame, period: int) -> float:
    """
    Average True Range — dipakai sebagai buffer stop loss di bawah support,
    supaya stop tidak kena 'shake out' normal dari volatilitas harian.
    """
    high = df["High"]
    low = df["Low"]
    prev_close = df["Close"].shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr_series = tr.rolling(window=period).mean()
    atr = atr_series.iloc[-1]
    return float(atr) if pd.notna(atr) else 0.0


# =============================================================================
# TRADE SETUP UNTUK SATU SAHAM
# =============================================================================

def calculate_trade_setup(ticker: str, entry_price: float, df: pd.DataFrame) -> Optional[dict]:
    """
    Hitung range, ATR, stop loss, target, dan RR untuk satu saham yang
    baru saja trigger breakout (Stage 2). Return None kalau data tidak cukup
    atau RR di bawah threshold minimum (config.STAGE3_MIN_RISK_REWARD).
    """
    if df is None or len(df) < max(cfg.STAGE3_RANGE_LOOKBACK_DAYS, cfg.STAGE3_ATR_PERIOD) + 1:
        logger.debug(f"       {ticker}: data OHLCV kurang untuk hitung trade setup, skip")
        return None

    range_high, range_low = compute_range(df, cfg.STAGE3_RANGE_LOOKBACK_DAYS)
    atr = compute_atr(df, cfg.STAGE3_ATR_PERIOD)

    if range_high <= range_low or atr <= 0:
        return None

    stop_loss = range_low - (atr * cfg.STAGE3_ATR_STOP_MULTIPLIER)
    target_price = entry_price + (range_high - range_low)

    risk = entry_price - stop_loss
    reward = target_price - entry_price

    if risk <= 0:
        logger.debug(f"       {ticker}: risk <= 0 (entry di bawah stop?), skip")
        return None

    rr = round(reward / risk, 2)

    if rr < cfg.STAGE3_MIN_RISK_REWARD:
        logger.debug(f"       {ticker}: RR {rr} < minimum {cfg.STAGE3_MIN_RISK_REWARD}, sinyal dibuang")
        return None

    return {
        "range_high": round(range_high, 2),
        "range_low": round(range_low, 2),
        "entry_price": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "target_price": round(target_price, 2),
        "risk_reward_ratio": rr,
    }


# =============================================================================
# TRADE SETUP UNTUK SEMUA SINYAL BREAKOUT DI SATU HASIL SCREENING
# =============================================================================

def attach_trade_setup(df_signals: pd.DataFrame, ohlcv: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Tambahkan kolom range_high, range_low, entry_price, stop_loss,
    target_price, risk_reward_ratio ke df_signals — hanya untuk baris
    dengan signal == 'Mark Up' (breakout, Stage 2 trigger).

    Sinyal Mark Up yang tidak lolos filter RR minimum akan DIBUANG dari
    hasil (bukan cuma dikosongkan kolomnya) — supaya screener hanya
    mengeluarkan sinyal entry yang benar-benar actionable.
    """
    if df_signals.empty:
        return df_signals

    setup_cols = ["range_high", "range_low", "entry_price", "stop_loss",
                  "target_price", "risk_reward_ratio"]

    rows_to_keep = []
    n_filtered = 0

    for _, row in df_signals.iterrows():
        signal = str(row.get("signal", ""))

        if signal != "Mark Up":
            # Sinyal selain breakout (Akumulasi/Distribusi/Mark Down) lewat apa adanya,
            # tanpa trade setup — kolom setup diisi None.
            new_row = row.to_dict()
            for c in setup_cols:
                new_row[c] = None
            rows_to_keep.append(new_row)
            continue

        ticker = str(row["ticker"]).upper()
        entry_price = float(row.get("close", 0) or 0)
        df_t = get_ohlcv_for_ticker(ohlcv, ticker)

        setup = calculate_trade_setup(ticker, entry_price, df_t)
        if setup is None:
            n_filtered += 1
            continue

        new_row = row.to_dict()
        new_row.update(setup)
        rows_to_keep.append(new_row)

    if n_filtered:
        logger.info(f"       Stage 3: {n_filtered} sinyal Mark Up dibuang (RR < {cfg.STAGE3_MIN_RISK_REWARD} atau data kurang)")

    result = pd.DataFrame(rows_to_keep)
    logger.info(f"       Stage 3: trade setup dihitung untuk sinyal breakout")
    return result
