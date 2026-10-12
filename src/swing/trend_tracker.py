# =============================================================================
# src/swing/trend_tracker.py — Pelacak posisi swing (MA cross + konfirmasi MACD)
#
# Aturan (dapat diubah lewat config.py):
#   BELI  : MA5 menembus MA20 ke atas DAN MACD golden cross (MACD > signal),
#           keduanya terjadi dalam jendela SWING_CONFIRM_WINDOW hari bursa.
#           Harga acuan = penutupan hari ketika syarat kedua terpenuhi.
#   TAHAN : sampai MA5 berada di bawah MA20 (cross down) DAN MACD dead cross
#           sama-sama terjadi SETELAH tanggal beli.
#   Status: pending = MA sudah cross up, menunggu golden cross MACD
#           open    = posisi sedang di-hold
#           closed  = posisi sudah ditutup
# Tidak ada stop loss dalam aturan ini; kolom worst_pct mencatat penurunan terdalam
# selama posisi dipegang supaya risikonya terlihat.
# =============================================================================

import logging
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg

logger = logging.getLogger(__name__)
_NEVER = -10 ** 9


def track(close: pd.Series, fast: int = 5, slow: int = 20, mf: int = 12, ms: int = 26,
          msig: int = 9, window: int = 10) -> dict:
    """Simulasikan aturan di atas pada satu seri penutupan. Return {'closed': [...], 'current': dict|None}."""
    close = close.dropna().astype(float)
    n = len(close)
    start = max(slow, ms + msig)               # warm-up indikator
    if n <= start + 2:
        return {"closed": [], "current": None}

    ma_f = close.rolling(fast).mean().to_numpy()
    ma_s = close.rolling(slow).mean().to_numpy()
    macd_s = close.ewm(span=mf, adjust=False).mean() - close.ewm(span=ms, adjust=False).mean()
    macd = macd_s.to_numpy()
    sig = macd_s.ewm(span=msig, adjust=False).mean().to_numpy()
    px, dates = close.to_numpy(), close.index
    bull_ma, bull_macd = ma_f > ma_s, macd > sig

    d = lambda i: dates[i].date()

    def record(entry_i, ma_ev, macd_ev, exit_i=None, warning=None):
        end = exit_i if exit_i is not None else n - 1
        worst = (float(np.min(px[entry_i:end + 1])) / float(px[entry_i]) - 1) * 100
        return {
            "status": "closed" if exit_i is not None else "open",
            "entry_date": d(entry_i), "entry_price": float(px[entry_i]),
            "exit_date": d(exit_i) if exit_i is not None else None,
            "exit_price": float(px[exit_i]) if exit_i is not None else None,
            "last_date": d(end), "last_price": float(px[end]),
            "return_pct": round(float(px[end] / px[entry_i] - 1) * 100, 2),
            "days_held": int((dates[end] - dates[entry_i]).days),
            "worst_pct": round(min(worst, 0.0), 2),
            "warning": warning, "ma_cross_date": d(ma_ev), "macd_cross_date": d(macd_ev),
        }

    state, pending_i, entry_i, ma_ev, macd_ev = "flat", None, None, None, None
    last_macd_up = last_ma_dn = last_macd_dn = _NEVER
    closed: List[dict] = []

    for i in range(start + 1, n):
        ma_up = bull_ma[i] and not bull_ma[i - 1]
        macd_up = bull_macd[i] and not bull_macd[i - 1]
        if (not bull_ma[i]) and bull_ma[i - 1]: last_ma_dn = i
        if (not bull_macd[i]) and bull_macd[i - 1]: last_macd_dn = i
        if macd_up: last_macd_up = i

        if state == "flat":
            if ma_up:
                if i - last_macd_up <= window and bull_macd[i]:      # MACD sudah golden cross lebih dulu
                    state, entry_i, ma_ev, macd_ev = "open", i, i, last_macd_up
                else:
                    state, pending_i = "pending", i
        elif state == "pending":
            if not bull_ma[i]:                                       # MA5 kembali di bawah MA20: batal
                state, pending_i = "flat", None
            elif macd_up:                                            # konfirmasi MACD datang
                state, entry_i, ma_ev, macd_ev = "open", i, pending_i, i
            elif i - pending_i >= window:                            # kedaluwarsa
                state, pending_i = "flat", None
        elif state == "open":
            if (not bull_ma[i]) and (not bull_macd[i]) and last_ma_dn > entry_i and last_macd_dn > entry_i:
                closed.append(record(entry_i, ma_ev, macd_ev, exit_i=i))
                state, entry_i = "flat", None

    current = None
    if state == "open":
        warn = "ma_down" if not bull_ma[-1] else ("macd_down" if not bull_macd[-1] else None)
        current = record(entry_i, ma_ev, macd_ev, warning=warn)
    elif state == "pending":
        current = {
            "status": "pending", "entry_date": None, "entry_price": None, "exit_date": None, "exit_price": None,
            "last_date": d(n - 1), "last_price": float(px[-1]),
            "return_pct": round(float(px[-1] / px[pending_i] - 1) * 100, 2),   # perubahan sejak MA cross up
            "days_held": int((dates[-1] - dates[pending_i]).days), "worst_pct": None,
            "warning": "macd_wait", "ma_cross_date": d(pending_i), "macd_cross_date": None,
        }
    return {"closed": closed, "current": current}


def track_all(ohlcv: Dict[str, pd.DataFrame]) -> List[dict]:
    """Jalankan pelacak untuk semua ticker. Return daftar baris (satu per posisi) dengan kunci 'ticker'."""
    p = dict(
        fast=cfg.MA_CROSS_FAST, slow=cfg.MA_CROSS_SLOW, mf=cfg.MACD_FAST, ms=cfg.MACD_SLOW,
        msig=cfg.MACD_SIGNAL, window=getattr(cfg, "SWING_CONFIRM_WINDOW", 10),
    )
    out: List[dict] = []
    for ticker, df in ohlcv.items():
        try:
            res = track(df["Close"], **p)
        except Exception as e:
            logger.warning(f"Tracker {ticker}: dilewati — {e}")
            continue
        for r in res["closed"] + ([res["current"]] if res["current"] else []):
            out.append({"ticker": str(ticker).upper(), **r})
    return out
