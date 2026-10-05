# =============================================================================
# src/swing/swing_setup.py — Setup swing gabungan (MA cross + MACD cross)
#
# JALUR SWING — terpisah dari Wyckoff. Didaftarkan di swing_screener.py.
#
# Berbeda dengan ma_cross.py / macd_cross.py (event crossover HARI INI saja),
# modul ini melihat cross dalam jendela SWING_CROSS_WINDOW hari terakhir
# (cross masih berlaku hari ini), menggabungkan keduanya, memberi filter,
# serta menghitung stop loss & target berbasis ATR.
#
# Sinyal:
#   Swing_Confirmed_Bullish : MA5 x MA20 ke atas DAN MACD x signal ke atas (dalam jendela)
#   Swing_Early_Bullish     : baru salah satu cross yang terjadi
#   Swing_Exit_Warning      : MA death cross atau MACD bearish cross dalam jendela
#
# Filter wajib (bullish): close > MA50, dan (jika MA cross terlibat) gap MA5-MA20 >= SWING_MIN_GAP_PCT.
# Bullish ditolak jika indikator lain justru sedang cross turun (sinyal bertentangan).
# Skor 0-10: tiap konfirmasi menambah poin. Stop = close - 2xATR14, target = 2R.
# =============================================================================

import logging
from typing import Dict, Optional

import pandas as pd

try:
    import config as cfg
except ImportError:
    cfg = None

from src.signals import indicators

logger = logging.getLogger(__name__)

CROSS_WINDOW     = getattr(cfg, "SWING_CROSS_WINDOW", 3)
MA_FAST          = getattr(cfg, "MA_CROSS_FAST", 5)
MA_SLOW          = getattr(cfg, "MA_CROSS_SLOW", 20)
TREND_MA         = getattr(cfg, "SWING_TREND_MA", 50)
MIN_GAP_PCT      = getattr(cfg, "SWING_MIN_GAP_PCT", 0.002)
VOLUME_RATIO_MIN = getattr(cfg, "SWING_VOLUME_RATIO_MIN", 1.2)
ATR_PERIOD       = getattr(cfg, "SWING_ATR_PERIOD", 14)
STOP_ATR_MULT    = getattr(cfg, "SWING_STOP_ATR_MULT", 2.0)
TARGET_R         = getattr(cfg, "SWING_TARGET_R", 2.0)
MACD_FAST        = getattr(cfg, "MACD_FAST", 12)
MACD_SLOW        = getattr(cfg, "MACD_SLOW", 26)
MACD_SIGNAL      = getattr(cfg, "MACD_SIGNAL", 9)

MIN_HISTORY_DAYS = max(TREND_MA, MACD_SLOW + MACD_SIGNAL + 10) + CROSS_WINDOW + 5

SIGNAL_CONFIRMED = "Swing_Confirmed_Bullish"
SIGNAL_EARLY     = "Swing_Early_Bullish"
SIGNAL_EXIT      = "Swing_Exit_Warning"

COLUMNS = ["ticker", "signal", "close", "strength", "note", "stop_price", "target_price"]


def _cross_age(a: pd.Series, b: pd.Series, window: int, up: bool) -> Optional[int]:
    """
    Umur cross dalam bar (1 = terjadi hari ini), None jika tidak ada.
    up=True : a memotong ke atas b, dan hari ini a masih di atas b.
    up=False: a memotong ke bawah b, dan hari ini a masih di bawah b.
    """
    if len(a) < window + 2:
        return None
    hi, lo = (a, b) if up else (b, a)
    if not hi.iloc[-1] > lo.iloc[-1]:
        return None
    for k in range(1, window + 1):
        if hi.iloc[-k - 1] <= lo.iloc[-k - 1] and hi.iloc[-k] > lo.iloc[-k]:
            return k
    return None


def _analyze(ticker: str, df: pd.DataFrame) -> Optional[dict]:
    d = df.sort_index()
    close = d["Close"]
    c = float(close.iloc[-1])

    ma_f = close.rolling(MA_FAST).mean()
    ma_s = close.rolling(MA_SLOW).mean()
    ma_t = close.rolling(TREND_MA).mean()
    macd = close.ewm(span=MACD_FAST, adjust=False).mean() - close.ewm(span=MACD_SLOW, adjust=False).mean()
    sig  = macd.ewm(span=MACD_SIGNAL, adjust=False).mean()

    if pd.isna(ma_t.iloc[-1]) or pd.isna(ma_s.iloc[-1]):
        return None

    ma_up    = _cross_age(ma_f, ma_s, CROSS_WINDOW, up=True)
    macd_up  = _cross_age(macd, sig, CROSS_WINDOW, up=True)
    ma_dn    = _cross_age(ma_f, ma_s, CROSS_WINDOW, up=False)
    macd_dn  = _cross_age(macd, sig, CROSS_WINDOW, up=False)

    vol_peak = indicators.volume_ratio(d, 20).iloc[-CROSS_WINDOW:].max()
    vol_ok   = pd.notna(vol_peak) and vol_peak >= VOLUME_RATIO_MIN

    # ---- Exit warning (bearish) ----
    if ma_dn is not None or macd_dn is not None:
        both  = ma_dn is not None and macd_dn is not None
        score = 7.0 if both else 5.0
        if c < ma_t.iloc[-1]: score += 1.0
        if vol_ok:            score += 1.0
        parts = []
        if ma_dn is not None:   parts.append(f"MA{MA_FAST}x{MA_SLOW} turun ({ma_dn}h lalu)")
        if macd_dn is not None: parts.append(f"MACD turun ({macd_dn}h lalu)")
        return {"ticker": ticker, "signal": SIGNAL_EXIT, "close": c,
                "strength": round(min(10.0, score), 1), "note": " + ".join(parts),
                "stop_price": None, "target_price": None}

    # ---- Bullish ----
    if ma_up is None and macd_up is None:
        return None
    if c <= ma_t.iloc[-1]:                       # filter tren
        return None
    gap = (ma_f.iloc[-1] - ma_s.iloc[-1]) / ma_s.iloc[-1]
    if ma_up is not None and gap < MIN_GAP_PCT:  # filter anti-sideways
        return None

    atr = indicators.atr(d, ATR_PERIOD).iloc[-1]
    if pd.isna(atr) or atr <= 0:
        return None
    stop = c - STOP_ATR_MULT * atr
    if stop <= 0:
        return None
    target = c + TARGET_R * (c - stop)

    both  = ma_up is not None and macd_up is not None
    score = 6.0 if both else 4.0
    if macd.iloc[-1] > 0:                  score += 1.0
    if vol_ok:                             score += 1.0
    if ma_t.iloc[-1] > ma_t.iloc[-6]:      score += 1.0
    if ma_up is not None and gap >= 0.01:  score += 1.0

    parts = []
    if ma_up is not None:   parts.append(f"MA{MA_FAST}x{MA_SLOW} naik ({ma_up}h lalu, gap {gap*100:.1f}%)")
    if macd_up is not None: parts.append(f"MACD naik ({macd_up}h lalu)")
    parts.append(f"stop {stop:,.0f} / target {target:,.0f}")

    return {"ticker": ticker, "signal": SIGNAL_CONFIRMED if both else SIGNAL_EARLY,
            "close": c, "strength": round(min(10.0, score), 1), "note": " | ".join(parts),
            "stop_price": round(stop, 2), "target_price": round(target, 2)}


def detect(ohlcv: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for ticker, df in (ohlcv or {}).items():
        if df is None or df.empty or "Close" not in df.columns or len(df) < MIN_HISTORY_DAYS:
            continue
        try:
            r = _analyze(ticker.upper(), df)
            if r:
                rows.append(r)
        except Exception as e:
            logger.warning(f"  {ticker}: error swing setup — {e}")

    out = pd.DataFrame(rows, columns=COLUMNS)
    logger.info(
        f"Swing Setup: {len(out)} sinyal "
        f"({(out['signal'] == SIGNAL_CONFIRMED).sum()} confirmed, "
        f"{(out['signal'] == SIGNAL_EARLY).sum()} early, "
        f"{(out['signal'] == SIGNAL_EXIT).sum()} exit warning)"
    )
    return out
