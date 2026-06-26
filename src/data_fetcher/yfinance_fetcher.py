# =============================================================================
# src/data_fetcher/yfinance_fetcher.py
# Download data OHLCV saham IDX dari Yahoo Finance via yfinance
# =============================================================================

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg

logger = logging.getLogger(__name__)


# =============================================================================
# FUNGSI PUBLIK
# =============================================================================

def fetch_ohlcv(
    tickers: List[str],
    period: str = cfg.YFINANCE_PERIOD,
    interval: str = cfg.YFINANCE_INTERVAL,
    use_cache: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Download data OHLCV untuk list ticker IDX.

    Parameters
    ----------
    tickers   : list ticker tanpa suffix, contoh ["BBCA", "TLKM"]
    period    : periode yfinance, contoh "30d", "60d", "1y"
    interval  : "1d" harian (default)
    use_cache : True = baca cache dulu, download hanya yang belum ada

    Returns
    -------
    dict { ticker: DataFrame } — kolom:
        Open, High, Low, Close, Volume,
        return_1d, change_3d, change_5d,
        vol_avg20, vol_ratio, high_5d
    """
    if use_cache and cfg.OHLCV_CACHE_PATH.exists():
        cached  = _load_cache()
        missing = [t for t in tickers if t not in cached]

        if not missing:
            logger.info(f"Cache hit semua {len(tickers)} ticker.")
            return {t: cached[t] for t in tickers}

        logger.info(
            f"Cache hit {len(tickers)-len(missing)} ticker, "
            f"download {len(missing)} ticker baru: {missing}"
        )
        fresh  = _download_batch(missing, period, interval)
        merged = {**cached, **fresh}
        _save_cache(merged)
        return {t: merged[t] for t in tickers if t in merged}

    # Tidak pakai cache — download semua
    data = _download_batch(tickers, period, interval)
    if use_cache:
        _save_cache(data)
    return data


def fetch_single(
    ticker: str,
    period: str = cfg.YFINANCE_PERIOD,
    interval: str = cfg.YFINANCE_INTERVAL,
) -> Optional[pd.DataFrame]:
    """
    Download satu ticker. Return None jika gagal.

    Contoh
    ------
    df = fetch_single("BBCA", period="90d")
    print(df.tail())
    """
    result = _download_batch([ticker], period, interval)
    return result.get(ticker)


def refresh_cache(tickers: List[str] = None) -> Dict[str, pd.DataFrame]:
    """
    Paksa download ulang semua ticker dan timpa cache lama.
    Dipanggil oleh scheduler (GitHub Actions / APScheduler) tiap hari.
    """
    tickers = tickers or cfg.DEFAULT_UNIVERSE
    logger.info(f"Refresh cache: {len(tickers)} ticker...")
    data = _download_batch(tickers, cfg.YFINANCE_PERIOD, cfg.YFINANCE_INTERVAL)
    _save_cache(data)
    logger.info(f"Cache diperbarui — {len(data)} ticker berhasil.")
    return data


def get_latest_price(tickers: List[str]) -> pd.DataFrame:
    """
    Return satu baris terakhir per ticker (harga & volume hari ini).
    Berguna untuk dashboard real-time Fase 2.

    Returns
    -------
    DataFrame index=ticker, kolom: Close, Volume, return_1d, vol_ratio
    """
    data = fetch_ohlcv(tickers, use_cache=True)
    rows = []
    for ticker, df in data.items():
        if df.empty:
            continue
        last = df.iloc[-1]
        rows.append({
            "ticker"   : ticker,
            "close"    : round(last["Close"], 0),
            "volume"   : int(last["Volume"]),
            "return_1d": round(last.get("return_1d", 0) * 100, 2),
            "vol_ratio": round(last.get("vol_ratio", 1), 2),
            "date"     : df.index[-1].date(),
        })
    return pd.DataFrame(rows).set_index("ticker")


# =============================================================================
# INTERNAL — DOWNLOAD & BATCH
# =============================================================================

def _download_batch(
    tickers: List[str],
    period: str,
    interval: str,
) -> Dict[str, pd.DataFrame]:
    """
    Download dalam batch kecil untuk menghindari rate limit Yahoo Finance.
    Batch size diatur di config: YFINANCE_BATCH_SIZE (default 20).
    Jeda 1 detik antar batch.
    """
    result: Dict[str, pd.DataFrame] = {}

    batches = [
        tickers[i : i + cfg.YFINANCE_BATCH_SIZE]
        for i in range(0, len(tickers), cfg.YFINANCE_BATCH_SIZE)
    ]

    for idx, batch in enumerate(batches):
        batch_jk = [t + cfg.YFINANCE_SUFFIX for t in batch]
        logger.info(f"Batch {idx+1}/{len(batches)}: {batch}")

        try:
            if len(batch_jk) == 1:
                # Single ticker — yfinance return format berbeda (tanpa level ticker)
                raw = yf.download(
                    batch_jk[0],
                    period=period,
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                )
                if not raw.empty:
                    df = _process_df(raw)
                    if df is not None:
                        result[batch[0]] = df
                else:
                    logger.warning(f"{batch[0]}: data kosong dari Yahoo")

            else:
                # Multi ticker — hasil digroup per ticker
                raw = yf.download(
                    batch_jk,
                    period=period,
                    interval=interval,
                    auto_adjust=True,
                    group_by="ticker",
                    progress=False,
                )

                for ticker, ticker_jk in zip(batch, batch_jk):
                    try:
                        # Akses kolom per ticker
                        df_raw = raw[ticker_jk][
                            ["Open", "High", "Low", "Close", "Volume"]
                        ].copy()
                        df_raw = df_raw.dropna(subset=["Close"])

                        if df_raw.empty:
                            logger.warning(f"{ticker}: data kosong")
                            continue

                        df = _process_df(df_raw)
                        if df is not None:
                            result[ticker] = df

                    except KeyError:
                        logger.warning(f"{ticker}: ticker tidak ditemukan di Yahoo Finance")
                    except Exception as e:
                        logger.warning(f"{ticker}: gagal parse — {e}")

        except Exception as e:
            logger.error(f"Batch {idx+1} error: {e}")

        # Jeda antar batch (kecuali batch terakhir)
        if idx < len(batches) - 1:
            time.sleep(1)

    logger.info(f"Download selesai: {len(result)}/{len(tickers)} ticker berhasil.")
    return result


# =============================================================================
# INTERNAL — PROSES & FEATURE ENGINEERING
# =============================================================================

def _process_df(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Normalisasi DataFrame dan tambahkan kolom turunan untuk sinyal ADMD.

    Kolom yang ditambahkan
    ----------------------
    return_1d  : persen perubahan harga 1 hari
    change_3d  : persen perubahan harga 3 hari (untuk Mark Down)
    change_5d  : persen perubahan harga 5 hari (untuk Akumulasi/Distribusi)
    vol_avg20  : rata-rata volume 20 hari
    vol_ratio  : volume hari ini / vol_avg20 (>1.5 = spike)
    high_5d    : highest High dalam 5 hari (untuk deteksi breakout Mark Up)
    """
    try:
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df = df.dropna(subset=["Close"])

        if len(df) < 5:
            return None

        df.index     = pd.to_datetime(df.index)
        df.index.name = "Date"

        # Pastikan tipe numerik
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["Close", "Volume"])

        # --- Return & perubahan harga ---
        df["return_1d"] = df["Close"].pct_change()
        df["change_3d"] = df["Close"].pct_change(3)
        df["change_5d"] = df["Close"].pct_change(5)

        # --- Volume ---
        df["vol_avg20"] = df["Volume"].rolling(20, min_periods=5).mean()
        df["vol_ratio"] = df["Volume"] / df["vol_avg20"]

        # --- Breakout reference ---
        # high_5d: High tertinggi dalam 5 hari terakhir
        # Pakai shift(1) supaya tidak include hari ini (untuk deteksi breakout)
        df["high_5d"] = df["High"].shift(1).rolling(5, min_periods=3).max()

        return df

    except Exception as e:
        logger.warning(f"_process_df error: {e}")
        return None


# =============================================================================
# INTERNAL — CACHE (Parquet)
# =============================================================================

def _save_cache(data: Dict[str, pd.DataFrame]) -> None:
    """
    Simpan setiap ticker sebagai file parquet terpisah.
    Format parquet jauh lebih cepat dan hemat disk vs CSV.
    """
    cfg.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    saved = 0
    for ticker, df in data.items():
        try:
            path = cfg.DATA_PROCESSED_DIR / f"{ticker}.parquet"
            df.to_parquet(path)
            saved += 1
        except Exception as e:
            logger.warning(f"Gagal simpan cache {ticker}: {e}")
    logger.info(f"Cache disimpan: {saved}/{len(data)} file → {cfg.DATA_PROCESSED_DIR}")


def _load_cache() -> Dict[str, pd.DataFrame]:
    """
    Baca semua file .parquet dari folder processed/.
    Return dict kosong jika folder tidak ada atau kosong.
    """
    if not cfg.DATA_PROCESSED_DIR.exists():
        return {}

    data = {}
    for path in cfg.DATA_PROCESSED_DIR.glob("*.parquet"):
        ticker = path.stem
        try:
            data[ticker] = pd.read_parquet(path)
        except Exception as e:
            logger.warning(f"Gagal baca cache {ticker}: {e}")

    if data:
        logger.info(f"Cache dimuat: {len(data)} ticker dari {cfg.DATA_PROCESSED_DIR}")
    return data


# =============================================================================
# QUICK TEST — python src/data_fetcher/yfinance_fetcher.py
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format=cfg.LOG_FORMAT)

    test_tickers = ["BBCA", "BBRI", "TLKM", "ASII", "BMRI"]
    print(f"\n{'='*55}")
    print(f"  TEST: download {len(test_tickers)} saham IDX")
    print(f"{'='*55}")

    data = fetch_ohlcv(test_tickers, period="30d", use_cache=False)

    if not data:
        print("Tidak ada data — cek koneksi internet.")
    else:
        for ticker, df in data.items():
            last = df.iloc[-1]
            print(
                f"\n  {ticker:<6} | "
                f"{len(df)} hari | "
                f"Rp {last['Close']:,.0f} | "
                f"Vol ratio {last['vol_ratio']:.2f}x | "
                f"5d change {last['change_5d']*100:+.2f}%"
            )
        print(f"\n  Kolom: {list(df.columns)}")

    print(f"\n{'='*55}")
    print("  Test get_latest_price:")
    summary = get_latest_price(test_tickers[:3])
    print(summary.to_string())