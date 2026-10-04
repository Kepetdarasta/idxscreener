# =============================================================================
# src/utils/asof.py — Potong data ke tanggal tertentu ("as of date")
#
# Dipakai oleh jalur Wyckoff (screener.py) dan jalur Swing (swing_screener.py)
# supaya backfill menghitung sinyal seolah-olah hari itu, bukan memakai data
# terbaru dengan label tanggal berbeda.
# =============================================================================

from typing import Dict, Optional

import pandas as pd


def truncate_ohlcv(ohlcv: Dict[str, pd.DataFrame], as_of_date) -> Dict[str, pd.DataFrame]:
    """Buang semua bar setelah as_of_date. as_of_date=None -> tidak diubah."""
    if as_of_date is None:
        return ohlcv

    cutoff = pd.Timestamp(as_of_date).normalize()
    out: Dict[str, pd.DataFrame] = {}

    for ticker, df in (ohlcv or {}).items():
        if df is None or df.empty:
            continue
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df.index = pd.to_datetime(df.index)
        idx = df.index
        c = cutoff.tz_localize(idx.tz) if idx.tz is not None else cutoff
        cut = df[idx.normalize() <= c]
        if not cut.empty:
            out[ticker] = cut
    return out


def truncate_foreign_flow(ff: Optional[pd.DataFrame], as_of_date) -> Optional[pd.DataFrame]:
    """Buang baris foreign flow setelah as_of_date (kolom 'date')."""
    if as_of_date is None or ff is None or ff.empty or "date" not in ff.columns:
        return ff
    cutoff = pd.Timestamp(as_of_date).normalize()
    d = pd.to_datetime(ff["date"]).dt.normalize()
    return ff[d <= cutoff].copy()
