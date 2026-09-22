# =============================================================================
# src/analysis/trend_indicators.py
#
# Modul INDEPENDEN dari pipeline screening ADMD (src/signals/). Tujuannya
# murni untuk analisis & perbandingan: menghitung garis MA5/MA20/MACD penuh
# sepanjang histori harga, dan mendeteksi SEMUA crossover historis — bukan
# cuma sinyal hari terakhir seperti src/signals/ma_cross.py & macd_cross.py.
#
# Dipakai oleh dashboard.py di tab "Perbandingan Metode" untuk:
#   1. Overlay chart harga + MA/MACD dengan timeline fase Wyckoff
#   2. Validasi hipotesis: apakah golden/death cross & MACD cross muncul
#      SEBELUM transisi fase Wyckoff tercatat (leading indicator check)
# =============================================================================

from typing import Dict, Optional

import pandas as pd

MA_FAST_WINDOW   = 5
MA_SLOW_WINDOW   = 20
MACD_FAST        = 12
MACD_SLOW        = 26
MACD_SIGNAL      = 9

EVENT_MA_GOLDEN  = "MA_Golden_Cross"
EVENT_MA_DEATH   = "MA_Death_Cross"
EVENT_MACD_BULL  = "MACD_Bullish_Cross"
EVENT_MACD_BEAR  = "MACD_Bearish_Cross"

# Sinyal trend mana yang relevan sebagai "leading indicator" untuk tiap arah
# fase Wyckoff — dipakai di validate_leading_indicator().
RELEVANT_SIGNALS_FOR_PHASE = {
    "accumulation": [EVENT_MA_GOLDEN, EVENT_MACD_BULL],
    "markup"      : [EVENT_MA_GOLDEN, EVENT_MACD_BULL],
    "distribution": [EVENT_MA_DEATH, EVENT_MACD_BEAR],
    "markdown"    : [EVENT_MA_DEATH, EVENT_MACD_BEAR],
}


def compute_indicators(close: pd.Series) -> pd.DataFrame:
    """
    Hitung MA5, MA20, MACD line, signal line, histogram untuk SELURUH histori.

    Parameters
    ----------
    close : pd.Series, index = tanggal (DatetimeIndex) terurut naik, value = close price

    Returns
    -------
    DataFrame dengan kolom: close, ma_fast, ma_slow, macd_line, signal_line, histogram
    """
    close = close.sort_index()
    out = pd.DataFrame(index=close.index)
    out["close"] = close
    out["ma_fast"] = close.rolling(MA_FAST_WINDOW).mean()
    out["ma_slow"] = close.rolling(MA_SLOW_WINDOW).mean()

    ema_fast = close.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=MACD_SLOW, adjust=False).mean()
    out["macd_line"] = ema_fast - ema_slow
    out["signal_line"] = out["macd_line"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    out["histogram"] = out["macd_line"] - out["signal_line"]
    return out


def find_crossovers(ind: pd.DataFrame) -> pd.DataFrame:
    """
    Deteksi SEMUA crossover historis (bukan cuma yang terakhir) dari hasil
    compute_indicators().

    Returns
    -------
    DataFrame kolom: date, type — terurut naik berdasarkan tanggal
    """
    ma_fast, ma_slow = ind["ma_fast"], ind["ma_slow"]
    macd, sig = ind["macd_line"], ind["signal_line"]

    golden  = (ma_fast > ma_slow) & (ma_fast.shift(1) <= ma_slow.shift(1))
    death   = (ma_fast < ma_slow) & (ma_fast.shift(1) >= ma_slow.shift(1))
    bullish = (macd > sig) & (macd.shift(1) <= sig.shift(1))
    bearish = (macd < sig) & (macd.shift(1) >= sig.shift(1))

    events = []
    for mask, label in [
        (golden, EVENT_MA_GOLDEN),
        (death, EVENT_MA_DEATH),
        (bullish, EVENT_MACD_BULL),
        (bearish, EVENT_MACD_BEAR),
    ]:
        for dt in ind.index[mask.fillna(False)]:
            events.append({"date": dt, "type": label})

    if not events:
        return pd.DataFrame(columns=["date", "type"])

    return pd.DataFrame(events).sort_values("date").reset_index(drop=True)


def validate_leading_indicator(
    phase_history: pd.DataFrame,
    ohlcv_by_ticker: Dict[str, pd.Series],
    lookback_days: int = 5,
) -> pd.DataFrame:
    """
    Untuk setiap baris di phase_history (= satu transisi ke fase tertentu),
    cek apakah ada sinyal trend (golden/death cross, MACD cross) yang relevan
    dengan arah fase itu, dalam `lookback_days` hari SEBELUM phase_start.

    Parameters
    ----------
    phase_history   : DataFrame dari tabel phase_history — wajib ada kolom
                       stock_code, phase, phase_start (datetime)
    ohlcv_by_ticker : dict[ticker] -> pd.Series close price, index tanggal
    lookback_days   : lebar jendela pengecekan "sebelum transisi" (hari)

    Returns
    -------
    DataFrame kolom: stock_code, phase, phase_start, leading_signal_found,
                      signal_type, days_before
    """
    rows = []

    for stock_code, sub in phase_history.groupby("stock_code"):
        close = ohlcv_by_ticker.get(stock_code)
        if close is None or close.empty:
            continue

        ind = compute_indicators(close)
        events = find_crossovers(ind)
        if events.empty:
            events = pd.DataFrame(columns=["date", "type"])

        for _, r in sub.sort_values("phase_start").iterrows():
            phase = r["phase"]
            phase_start = pd.Timestamp(r["phase_start"])
            window_start = phase_start - pd.Timedelta(days=lookback_days)

            relevant_types = RELEVANT_SIGNALS_FOR_PHASE.get(phase, [])
            window_events = events[
                (events["date"] >= window_start)
                & (events["date"] < phase_start)
                & (events["type"].isin(relevant_types))
            ]

            found = not window_events.empty
            last_event = window_events.iloc[-1] if found else None

            rows.append({
                "stock_code": stock_code,
                "phase": phase,
                "phase_start": phase_start,
                "leading_signal_found": found,
                "signal_type": last_event["type"] if found else None,
                "days_before": (phase_start - last_event["date"]).days if found else None,
            })

    return pd.DataFrame(rows, columns=[
        "stock_code", "phase", "phase_start",
        "leading_signal_found", "signal_type", "days_before",
    ])
