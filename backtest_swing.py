# =============================================================================
# backtest_swing.py — Backtest strategi swing: masuk saat Swing Setup, tahan
# sampai cross turun (tanpa time stop), stop loss ATR sebagai pengaman.
#
# Aturan simulasi (tanpa lookahead):
#   - Sinyal dihitung dari data s/d penutupan hari i (pakai swing_setup._analyze
#     yang SAMA dengan jalur live, jendela 180 bar ~ SWING_HISTORY_PERIOD 9mo)
#   - Entry di HARGA BUKA hari i+1 (dilewati jika sudah gap di bawah stop)
#   - Stop tetap = close sinyal - 2xATR14; kena jika Low <= stop (gap: harga buka)
#   - Cross turun terdeteksi di penutupan hari j -> keluar di HARGA BUKA hari j+1
#   - Satu posisi per saham; biaya bolak-balik dipotong dari tiap trade
#
# Tiga varian aturan keluar dibandingkan: MA (MA5 cross bawah MA20),
# MACD (MACD cross bawah signal), Either (mana yang lebih dulu).
#
# Jalankan:  python backtest_swing.py                 (3 tahun, LQ45, sinyal Confirmed)
#            python backtest_swing.py --levels all    (Confirmed + Early)
#            python backtest_swing.py --period 5y --cost 0.005
# =============================================================================

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.swing import swing_setup as ss

logger = logging.getLogger(__name__)

WINDOW = 180                      # bar yang dilihat detektor tiap hari (sama dengan live ~9mo)
EXIT_MODES = ("MA", "MACD", "Either")


def _down_events(d: pd.DataFrame):
    """Boolean per bar: terjadi cross turun pada penutupan bar tsb (kausal)."""
    c = d["Close"]
    f, s = c.rolling(ss.MA_FAST).mean(), c.rolling(ss.MA_SLOW).mean()
    macd = c.ewm(span=ss.MACD_FAST, adjust=False).mean() - c.ewm(span=ss.MACD_SLOW, adjust=False).mean()
    sig = macd.ewm(span=ss.MACD_SIGNAL, adjust=False).mean()
    ma_dn = ((f.shift(1) >= s.shift(1)) & (f < s)).to_numpy()
    macd_dn = ((macd.shift(1) >= sig.shift(1)) & (macd < sig)).to_numpy()
    return ma_dn, macd_dn


def _find_exit(e, stop, mode, o, l, c, ma_dn, macd_dn):
    """Return (bar_keluar, harga_keluar, alasan). Posisi dibuka di bar e (harga buka)."""
    n = len(c)
    for j in range(e, n):
        if l[j] <= stop:
            return j, (o[j] if o[j] <= stop else stop), "stop"
        ev = ma_dn[j] if mode == "MA" else macd_dn[j] if mode == "MACD" else (ma_dn[j] or macd_dn[j])
        if ev:
            return (j + 1, o[j + 1], "cross") if j + 1 < n else (j, c[j], "open")
    return n - 1, c[n - 1], "open"


def simulate_ticker(ticker, df, levels, cost, modes=EXIT_MODES):
    d = df.sort_index()
    o, l, c = d["Open"].to_numpy(float), d["Low"].to_numpy(float), d["Close"].to_numpy(float)
    ma_dn, macd_dn = _down_events(d)
    n, cache, trades = len(d), {}, []

    def signal_at(i):
        if i not in cache:
            cache[i] = ss._analyze(ticker, d.iloc[max(0, i - WINDOW + 1): i + 1])
        return cache[i]

    for mode in modes:
        i = ss.MIN_HISTORY_DAYS
        while i < n - 1:
            r = signal_at(i)
            if r is None or r["signal"] not in levels or r["stop_price"] is None:
                i += 1
                continue
            e, stop = i + 1, float(r["stop_price"])
            if o[e] <= stop:                       # gap di bawah stop: tidak bisa masuk
                i += 1
                continue
            x, px, reason = _find_exit(e, stop, mode, o, l, c, ma_dn, macd_dn)
            trades.append({
                "ticker": ticker, "exit_mode": mode, "signal": r["signal"],
                "signal_date": d.index[i], "entry_date": d.index[e], "entry": o[e],
                "exit_date": d.index[x], "exit": px, "reason": reason, "stop": stop,
                "ret": px / o[e] - 1 - cost, "days": x - e,
            })
            i = max(x, i + 1)
    return trades


def run_backtest(ohlcv, levels, cost):
    allt, bh = [], []
    for k, (t, df) in enumerate(ohlcv.items(), 1):
        if df is None or len(df) < ss.MIN_HISTORY_DAYS + 20:
            continue
        allt += simulate_ticker(t, df, levels, cost)
        c = df.sort_index()["Close"].to_numpy(float)
        i0 = ss.MIN_HISTORY_DAYS
        bh.append(((c[-1] / c[i0] - 1) / (len(c) - i0), len(c) - i0))
        logger.info(f"  [{k}/{len(ohlcv)}] {t}")
    trades = pd.DataFrame(allt)
    bh_day = float(np.mean([b[0] for b in bh])) if bh else float("nan")
    return trades, bh_day, len(bh), (int(np.mean([b[1] for b in bh])) if bh else 0)


def _stats(g):
    r = g["ret"]; w, ls = r[r > 0], r[r <= 0]
    return pd.Series({
        "trades": len(r), "win%": (r > 0).mean() * 100, "avg%": r.mean() * 100,
        "median%": r.median() * 100, "avg_win%": w.mean() * 100 if len(w) else 0.0,
        "avg_loss%": ls.mean() * 100 if len(ls) else 0.0,
        "PF": (w.sum() / abs(ls.sum())) if ls.sum() < 0 else np.inf,
        "avg_days": g["days"].mean(), "worst%": r.min() * 100,
        "stop%": (g["reason"] == "stop").mean() * 100,
        "ret/day%": r.sum() / max(g["days"].sum(), 1) * 100,
    })


def _table(trades, keys):
    """Statistik per grup (tanpa groupby.apply, supaya jalan di semua versi pandas)."""
    return pd.DataFrame({k: _stats(g) for k, g in trades.groupby(keys)}).T


def report(trades, bh_day, n_tickers, n_bars):
    if trades.empty:
        print("\nTidak ada trade — histori terlalu pendek atau tidak ada sinyal."); return
    print(f"\n{'=' * 78}\n  BACKTEST SWING — {n_tickers} saham, ±{n_bars} bar per saham\n{'=' * 78}")
    print(_table(trades, "exit_mode").round(2).to_string())
    if len(trades["signal"].unique()) > 1:
        print("\nPer jenis sinyal:")
        print(_table(trades, ["exit_mode", "signal"]).round(2).to_string())
    print(f"\nPembanding beli-dan-tahan: ±{bh_day * 100:.3f}% per hari (rata-rata, pendekatan linear)")
    print("Bandingkan dengan kolom ret/day% (return per hari yang benar-benar dipegang).")
    print("Catatan: universe = LQ45 SAAT INI (survivorship bias: saham yang dulu masuk lalu keluar tidak ikut).")
    print("Hasil historis bukan jaminan hasil ke depan.")


if __name__ == "__main__":
    import config as cfg
    from src.swing.swing_screener import _fetch_history

    ap = argparse.ArgumentParser(description="Backtest swing: tahan sampai cross turun")
    ap.add_argument("--period", default="3y", help="histori yfinance (default 3y)")
    ap.add_argument("--cost", type=float, default=0.004, help="biaya bolak-balik (default 0.4%%)")
    ap.add_argument("--levels", choices=["confirmed", "all"], default="confirmed")
    ap.add_argument("--out", default="backtest_swing_trades.csv")
    a = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
    levels = {ss.SIGNAL_CONFIRMED} if a.levels == "confirmed" else {ss.SIGNAL_CONFIRMED, ss.SIGNAL_EARLY}
    ohlcv = _fetch_history(tuple(sorted({t.upper() for t in cfg.DEFAULT_UNIVERSE})), a.period)
    logger.info(f"Data: {len(ohlcv)} saham, period={a.period}, levels={a.levels}, cost={a.cost:.2%}")

    trades, bh_day, n, bars = run_backtest(ohlcv, levels, a.cost)
    if not trades.empty:
        trades.to_csv(a.out, index=False); logger.info(f"Detail trade → {a.out}")
    report(trades, bh_day, n, bars)
