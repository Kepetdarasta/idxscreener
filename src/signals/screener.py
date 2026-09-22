# =============================================================================
# src/signals/screener.py — Orchestrator ADMD
# Berjalan normal dengan atau tanpa data foreign flow
#
# PERUBAHAN dari versi sebelumnya (ditandai dengan komentar # >>> STAGE 3):
#   1. Import risk_manager
#   2. Setelah `combined` dibentuk, panggil risk_manager.attach_trade_setup()
#      supaya sinyal Mark Up otomatis dapat entry/stop/target/RR, dan sinyal
#      Mark Up dengan RR terlalu kecil DIBUANG dari hasil.
# Tidak ada bagian lain yang berubah.
# =============================================================================

import logging
from pathlib import Path
from typing import List
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg
from src.signals import accumulation, distribution, markup, markdown
from src.signals import risk_manager   # >>> STAGE 3
from src.signals import ma_cross, macd_cross

logger = logging.getLogger(__name__)

SIGNAL_FUNCS = {
    "Akumulasi" : accumulation.detect,
    "Distribusi": distribution.detect,
    "Mark Up"   : markup.detect,
    "Mark Down" : markdown.detect,
    "MA_Cross": ma_cross.detect,
    "MACD_Cross": macd_cross.detect,
}

SIGNAL_EMOJI = {
    "Akumulasi" : "🟢",
    "Distribusi": "🟠",
    "Mark Up"   : "🔵",
    "Mark Down" : "🔴",
    "MA_Cross"  : "📊",
    "MACD_Cross": "📈",
}

def run_all(
    tickers: List[str] = None,
    use_cache: bool = True,
    save_output: bool = True,
    foreign_flow: pd.DataFrame = None,   # ← bisa diisi dari luar (upload manual)
    as_of_date = None,   # >>> FIX: datetime.date — potong data sampai tanggal ini.
                          # None = pakai data real-time terbaru (mode harian normal).
) -> pd.DataFrame:
    from src.data_fetcher.yfinance_fetcher import fetch_ohlcv
    from src.data_fetcher.idx_foreign_parser import load_foreign_flow

    tickers = tickers or cfg.DEFAULT_UNIVERSE
    logger.info(
        f"Screening {len(tickers)} ticker — 4 sinyal ADMD"
        + (f" (as of {as_of_date})" if as_of_date else "")
    )

    # 1. OHLCV
    logger.info("Step 1/3: Download OHLCV...")
    ohlcv = fetch_ohlcv(tickers, use_cache=use_cache)
    if not ohlcv:
        logger.error("Tidak ada data OHLCV.")
        return pd.DataFrame()

    # >>> FIX: potong data supaya tidak "bocor" info dari SETELAH as_of_date —
    # tanpa ini, backfill tanggal lama tetap pakai data hari-ini-real-time,
    # bukan data "seolah-olah" sampai tanggal itu saja.
    if as_of_date is not None:
        cutoff = pd.Timestamp(as_of_date)
        ohlcv = {t: df[df.index.normalize() <= cutoff] for t, df in ohlcv.items()}
        ohlcv = {t: df for t, df in ohlcv.items() if not df.empty}
        if not ohlcv:
            logger.warning(f"Tidak ada data OHLCV sampai {as_of_date}.")
            return pd.DataFrame()

    # 2. Foreign flow — pakai yang dikirim dari luar, atau coba load dari disk
    if foreign_flow is not None:
        logger.info("Step 2/3: Pakai foreign flow dari parameter (upload manual).")
    else:
        logger.info("Step 2/3: Coba baca foreign flow dari data/raw/...")
        foreign_flow = load_foreign_flow(tickers, days=5)
        if foreign_flow.empty:
            logger.warning(
                "Data foreign flow tidak tersedia — "
                "Akumulasi & Distribusi berjalan dengan kriteria harga+volume saja."
            )

    # 3. Deteksi sinyal — ADMD tetap 1 baris/ticker (prioritas), MA/MACD cross
    # ditempel sebagai KOLOM TAMBAHAN supaya tidak saling menggusur.
    logger.info("Step 3/3: Deteksi sinyal...")
    admd_results = []
    trend_results = {}  # "MA_Cross" / "MACD_Cross" -> DataFrame, dipisah dari kompetisi ADMD

    for name, fn in SIGNAL_FUNCS.items():
        try:
            result = fn(ohlcv, foreign_flow)
            if not result.empty:
                if name in ("MA_Cross", "MACD_Cross"):
                    trend_results[name] = result
                else:
                    admd_results.append(result)
                logger.info(f"  {SIGNAL_EMOJI[name]} {name}: {len(result)} sinyal")
            else:
                logger.info(f"  — {name}: tidak ada sinyal")
        except Exception as e:
            logger.error(f"  ✗ {name}: {e}")

    if not admd_results and not trend_results:
        logger.warning("Tidak ada sinyal ditemukan.")
        return pd.DataFrame()

    # --- ADMD: tetap dedup 1 baris/ticker seperti sebelumnya ---
    base_cols = ["ticker", "signal", "close", "strength", "note"]
    if admd_results:
        combined = pd.concat(admd_results, ignore_index=True)
        combined["ticker"] = combined["ticker"].astype(str).str.upper().str.strip()

        SIGNAL_PRIORITY = {"Mark Up": 4, "Mark Down": 3, "Akumulasi": 2, "Distribusi": 1}
        combined["_priority"] = combined["signal"].map(SIGNAL_PRIORITY).fillna(0)
        combined = (
            combined
            .sort_values(["_priority", "strength"], ascending=[False, False])
            .drop_duplicates(subset="ticker", keep="first")
            .drop(columns="_priority")
        )
    else:
        combined = pd.DataFrame(columns=base_cols)

    # --- Trend: MA cross & MACD cross jadi kolom terpisah, bukan baris baru ---
    def _trend_columns(df, prefix):
        cols = ["ticker", f"{prefix}_signal", f"{prefix}_note"]
        if df is None or df.empty:
            return pd.DataFrame(columns=cols)
        out = df[["ticker", "signal", "note"]].rename(
            columns={"signal": f"{prefix}_signal", "note": f"{prefix}_note"}
        )
        out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
        return out

    ma_cols   = _trend_columns(trend_results.get("MA_Cross"), "ma_cross")
    macd_cols = _trend_columns(trend_results.get("MACD_Cross"), "macd_cross")

    # Ticker yang HANYA kena MA/MACD (tanpa sinyal ADMD hari itu) tetap harus
    # dimunculkan, bukan hilang begitu saja — makanya di-union dulu.
    all_tickers = set(combined["ticker"]) | set(ma_cols["ticker"]) | set(macd_cols["ticker"])
    missing = all_tickers - set(combined["ticker"])
    if missing:
        combined = pd.concat(
            [combined, pd.DataFrame({"ticker": list(missing)})],
            ignore_index=True
        )

    combined = combined.merge(ma_cols, on="ticker", how="left")
    combined = combined.merge(macd_cols, on="ticker", how="left")

    # Ticker trend-only tidak punya kolom 'close' dari ADMD — ambil dari OHLCV langsung.
    missing_close = combined["close"].isna()
    if missing_close.any():
        combined.loc[missing_close, "close"] = combined.loc[missing_close, "ticker"].map(
            lambda t: float(ohlcv[t]["Close"].iloc[-1]) if t in ohlcv and not ohlcv[t].empty else None
        )

    combined = combined.sort_values(["signal", "strength"], ascending=[True, False]).reset_index(drop=True)

    # >>> STAGE 3: RISK MANAGER : hitung entry/stop/target/RR untuk sinyal Mark Up,
    # buang sinyal Mark Up yang RR-nya di bawah threshold minimum.
    logger.info("Step 4/4: Hitung trade setup (Stage 3)...")
    combined = risk_manager.attach_trade_setup(combined, ohlcv)

    if save_output:
        cfg.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        combined.to_csv(cfg.SIGNALS_OUTPUT_PATH, index=False)
        logger.info(f"Hasil disimpan → {cfg.SIGNALS_OUTPUT_PATH}")

    has_foreign = not foreign_flow.empty
    logger.info(
        f"Selesai — {len(combined)} sinyal | "
        f"mode: {'dengan' if has_foreign else 'TANPA'} data asing"
    )
    return combined


def run_single(
    signal_name: str,
    tickers: List[str] = None,
    use_cache: bool = True,
    foreign_flow: pd.DataFrame = None,
) -> pd.DataFrame:
    from src.data_fetcher.yfinance_fetcher import fetch_ohlcv
    from src.data_fetcher.idx_foreign_parser import load_foreign_flow

    if signal_name not in SIGNAL_FUNCS:
        raise ValueError(f"Signal tidak dikenal: '{signal_name}'. Pilih: {list(SIGNAL_FUNCS)}")

    tickers = tickers or cfg.DEFAULT_UNIVERSE
    ohlcv   = fetch_ohlcv(tickers, use_cache=use_cache)

    if foreign_flow is None:
        foreign_flow = load_foreign_flow(tickers, days=5)

    return SIGNAL_FUNCS[signal_name](ohlcv, foreign_flow)


def print_summary(df: pd.DataFrame) -> None:
    if df.empty:
        print("\n  Tidak ada sinyal ditemukan.\n")
        return

    no_foreign = "data_asing" in df.columns and not df["data_asing"].any()

    print(f"\n{'='*65}")
    print(f"  IDX SCREENER — ADMD  ({len(df)} sinyal total)")
    if no_foreign:
        print(f"  ⚠  Mode: TANPA data asing — strength dikap 70 untuk Akumulasi/Distribusi")
    print(f"{'='*65}")

    for signal, emoji in SIGNAL_EMOJI.items():
        subset = df[df["signal"] == signal]
        if subset.empty:
            continue
        print(f"\n{emoji} {signal.upper()} ({len(subset)} saham)")

        # >>> STAGE 3: tampilkan entry/stop/target/RR kalau ada (khusus Mark Up)
        has_setup = "entry_price" in subset.columns and subset["entry_price"].notna().any()

        if has_setup:
            print(f"  {'Ticker':<7} {'Close':>9}  {'Str':>5}  {'Entry':>9}  {'Stop':>9}  {'Target':>9}  {'RR':>5}  Catatan")
            print(f"  {'-'*95}")
            for _, row in subset.iterrows():
                print(
                    f"  {row['ticker']:<7} "
                    f"Rp{row['close']:>8,.0f}  "
                    f"{row['strength']:>5.1f}  "
                    f"Rp{row.get('entry_price', 0) or 0:>7,.0f}  "
                    f"Rp{row.get('stop_loss', 0) or 0:>7,.0f}  "
                    f"Rp{row.get('target_price', 0) or 0:>7,.0f}  "
                    f"{row.get('risk_reward_ratio', 0) or 0:>5.2f}  "
                    f"{row.get('note', '')}"
                )
        else:
            print(f"  {'Ticker':<7} {'Close':>9}  {'Str':>5}  Catatan")
            print(f"  {'-'*56}")
            for _, row in subset.iterrows():
                print(
                    f"  {row['ticker']:<7} "
                    f"Rp{row['close']:>8,.0f}  "
                    f"{row['strength']:>5.1f}  "
                    f"{row.get('note', '')}"
                )

    print(f"\n{'='*65}\n")
