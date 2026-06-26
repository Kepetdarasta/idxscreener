# =============================================================================
# src/data_fetcher/idx_foreign_parser.py
#
# Parse file CSV net buy/sell asing dari IDX.co.id
#
# CARA DOWNLOAD FILE DARI IDX:
#   1. Buka https://www.idx.co.id/id/data-pasar/laporan-statistik/foreign-flow
#   2. Pilih tanggal, klik Download
#   3. Simpan di: data/raw/foreign_flow_YYYYMMDD.csv
#      contoh   : data/raw/foreign_flow_20240611.csv
#
# FORMAT FILE IDX (biasanya):
#   StockCode | StockName | ForeignBuy | ForeignSell | NetBuySell
#   Nilai dalam satuan RUPIAH (bukan lot/lembar)
# =============================================================================

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config as cfg

logger = logging.getLogger(__name__)


# =============================================================================
# FUNGSI PUBLIK
# =============================================================================

def load_foreign_flow(
    tickers: List[str] = None,
    days: int = 5,
) -> pd.DataFrame:
    """
    Baca semua file CSV foreign flow yang tersedia di data/raw/,
    gabungkan N hari terakhir, dan hitung akumulasi net_5d per ticker.

    Parameters
    ----------
    tickers : list ticker yang ingin difilter, contoh ["BBCA", "TLKM"]
              None = semua ticker yang ada di file
    days    : ambil N hari terakhir (default 5)

    Returns
    -------
    DataFrame kolom:
        ticker, date, foreign_buy, foreign_sell, net_buy_sell, net_5d

    Keterangan net_5d
    -----------------
    Positif (+) = net buy asing (akumulasi)
    Negatif (-) = net sell asing (distribusi/markdown)
    """
    files = _get_sorted_files()

    if not files:
        logger.warning(
            "Tidak ada file foreign flow di data/raw/\n"
            "  → Download dari: https://www.idx.co.id/id/data-pasar/laporan-statistik/foreign-flow\n"
            "  → Simpan sebagai: data/raw/foreign_flow_YYYYMMDD.csv"
        )
        return pd.DataFrame()

    # Ambil N file terbaru
    recent = files[-days:] if len(files) > days else files
    logger.info(
        f"Membaca {len(recent)} file "
        f"({recent[0].stem} s/d {recent[-1].stem})..."
    )

    # Parse tiap file
    dfs = []
    for f in recent:
        df = _parse_file(f)
        if df is not None and not df.empty:
            dfs.append(df)

    if not dfs:
        logger.error("Semua file gagal di-parse. Cek format CSV.")
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)

    # Filter ticker jika diminta
    if tickers:
        tickers_upper = [t.upper().strip() for t in tickers]
        combined = combined[combined["ticker"].isin(tickers_upper)]

    # Deduplicate: kalau ada ticker yang muncul dua kali di hari yang sama, ambil satu
    combined = combined.drop_duplicates(subset=["ticker", "date"])
    combined = combined.sort_values(["ticker", "date"]).reset_index(drop=True)

    # Hitung net akumulasi 5 hari rolling per ticker
    combined["net_5d"] = (
        combined
        .groupby("ticker")["net_buy_sell"]
        .transform(lambda x: x.rolling(5, min_periods=1).sum())
    )

    logger.info(
        f"Foreign flow siap: {combined['ticker'].nunique()} ticker | "
        f"{combined['date'].min().date()} s/d {combined['date'].max().date()}"
    )
    return combined


def get_latest_foreign(tickers: List[str] = None) -> pd.DataFrame:
    """
    Return hanya baris hari terakhir yang tersedia per ticker.
    Kolom: ticker, date, foreign_buy, foreign_sell, net_buy_sell, net_5d

    Cocok untuk:
    - Ditampilkan di dashboard harian
    - Digabung dengan data OHLCV untuk screening
    """
    df = load_foreign_flow(tickers, days=5)
    if df.empty:
        return df

    latest_date = df["date"].max()
    result = df[df["date"] == latest_date].reset_index(drop=True)
    logger.info(f"Latest foreign flow: {len(result)} ticker per {latest_date.date()}")
    return result


def get_net_5d(tickers: List[str] = None) -> Dict[str, float]:
    """
    Shortcut: return dict { ticker → net_buy_sell_5hari } dalam rupiah.

    Dipakai langsung oleh sinyal Akumulasi, Distribusi, Mark Down.

    Contoh output
    -------------
    {
        "BBCA":  250_000_000_000,   # net buy Rp 250M → Akumulasi
        "UNVR": -180_000_000_000,   # net sell Rp 180M → Distribusi
    }
    """
    df = load_foreign_flow(tickers, days=5)
    if df.empty:
        return {}

    # Ambil nilai net_5d terbaru per ticker
    latest = (
        df.sort_values("date")
        .groupby("ticker")["net_5d"]
        .last()
    )
    return latest.to_dict()


def get_available_dates() -> List[date]:
    """
    Return list tanggal yang tersedia dari file di data/raw/.
    Berguna untuk validasi dan debugging.
    """
    files = _get_sorted_files()
    dates = []
    for f in files:
        try:
            date_str = f.stem.replace("foreign_flow_", "")
            dates.append(datetime.strptime(date_str, cfg.IDX_FOREIGN_DATE_FORMAT).date())
        except ValueError:
            pass
    return sorted(dates)


# =============================================================================
# INTERNAL — FILE DISCOVERY
# =============================================================================

def _get_sorted_files() -> List[Path]:
    """
    Return list file foreign_flow_*.csv di data/raw/, urut dari lama ke baru.
    Hanya file dengan nama format yang benar yang diambil.
    """
    cfg.DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    files = []

    for f in cfg.DATA_RAW_DIR.glob("foreign_flow_*.csv"):
        # Validasi format nama file
        date_str = f.stem.replace("foreign_flow_", "")
        try:
            datetime.strptime(date_str, cfg.IDX_FOREIGN_DATE_FORMAT)
            files.append(f)
        except ValueError:
            logger.warning(f"Nama file tidak sesuai format: {f.name} (expected: foreign_flow_YYYYMMDD.csv)")

    return sorted(files)


# =============================================================================
# INTERNAL — PARSER
# =============================================================================

def _parse_file(filepath: Path) -> Optional[pd.DataFrame]:
    """
    Parse satu file CSV. Auto-detect format IDX.
    Return DataFrame ternormalisasi atau None jika gagal.
    """
    try:
        # Baca sample untuk deteksi format
        sample = pd.read_csv(
            filepath,
            encoding=cfg.IDX_FOREIGN_ENCODING,
            nrows=3,
            on_bad_lines="skip",
        )
        cols_lower = [str(c).lower().strip().replace(" ", "_") for c in sample.columns]

        # Deteksi format berdasarkan nama kolom
        has_stock_col = any(
            k in col
            for col in cols_lower
            for k in ("stockcode", "kode_saham", "kode", "stock_code")
        )
        has_date_col = any(
            str(c).startswith("20") or str(c).startswith("19")
            for c in sample.columns
        )

        if has_stock_col:
            return _parse_format_vertical(filepath)
        elif has_date_col:
            return _parse_format_pivot(filepath)
        else:
            # Coba format vertical dulu sebagai fallback
            logger.warning(f"{filepath.name}: format tidak dikenal, coba parse sebagai format vertikal...")
            return _parse_format_vertical(filepath)

    except Exception as e:
        logger.error(f"Gagal baca {filepath.name}: {e}")
        return None


def _parse_format_vertical(filepath: Path) -> Optional[pd.DataFrame]:
    """
    Format VERTIKAL (paling umum dari IDX):
    Satu baris per saham, kolom = StockCode, ForeignBuy, ForeignSell, NetBuySell

    Contoh
    ------
    StockCode | StockName | ForeignBuy  | ForeignSell | NetBuySell
    BBCA      | BCA       | 350000000000| 100000000000| 250000000000
    """
    try:
        df = pd.read_csv(
            filepath,
            encoding=cfg.IDX_FOREIGN_ENCODING,
            on_bad_lines="skip",
        )

        # Normalisasi nama kolom
        df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]

        # Peta semua variasi nama kolom yang mungkin dari IDX
        rename_map = {
            # Ticker
            "stockcode"       : "ticker",
            "stock_code"      : "ticker",
            "kode_saham"      : "ticker",
            "kode"            : "ticker",
            "emiten"          : "ticker",
            # Foreign buy
            "foreignbuy"      : "foreign_buy",
            "foreign_buy"     : "foreign_buy",
            "pembelian_asing" : "foreign_buy",
            "beli_asing"      : "foreign_buy",
            "f_buy"           : "foreign_buy",
            # Foreign sell
            "foreignsell"     : "foreign_sell",
            "foreign_sell"    : "foreign_sell",
            "penjualan_asing" : "foreign_sell",
            "jual_asing"      : "foreign_sell",
            "f_sell"          : "foreign_sell",
            # Net
            "netbuysell"      : "net_buy_sell",
            "net_buy_sell"    : "net_buy_sell",
            "net_beli"        : "net_buy_sell",
            "net"             : "net_buy_sell",
            "netsell"         : "net_buy_sell",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        # Wajib ada kolom ticker
        if "ticker" not in df.columns:
            logger.warning(f"{filepath.name}: kolom ticker/StockCode tidak ditemukan")
            return None

        # Tambah tanggal dari nama file
        date_str   = filepath.stem.replace("foreign_flow_", "")
        file_date  = datetime.strptime(date_str, cfg.IDX_FOREIGN_DATE_FORMAT)
        df["date"] = pd.Timestamp(file_date)

        # Bersihkan dan konversi angka
        # IDX kadang pakai format "1.250.000.000" (titik sebagai ribuan)
        for col in ["foreign_buy", "foreign_sell", "net_buy_sell"]:
            if col in df.columns:
                df[col] = _clean_number(df[col])

        # Hitung net jika kolom net tidak ada
        if "net_buy_sell" not in df.columns:
            if "foreign_buy" in df.columns and "foreign_sell" in df.columns:
                df["net_buy_sell"] = df["foreign_buy"] - df["foreign_sell"]
            else:
                logger.warning(f"{filepath.name}: tidak bisa hitung net_buy_sell")
                return None

        # Tambah foreign_buy / foreign_sell jika tidak ada
        if "foreign_buy"  not in df.columns: df["foreign_buy"]  = None
        if "foreign_sell" not in df.columns: df["foreign_sell"] = None

        # Bersihkan ticker
        df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()

        # Buang baris tidak valid
        df = df[df["ticker"].str.len().between(1, 6)]          # ticker IDX max 6 karakter
        df = df[~df["ticker"].str.contains(r"[^A-Z0-9]")]      # hanya huruf & angka
        df = df.dropna(subset=["ticker", "net_buy_sell"])

        result = df[["ticker", "date", "foreign_buy", "foreign_sell", "net_buy_sell"]].copy()
        logger.info(f"  ✓ {filepath.name}: {len(result)} saham (format vertikal)")
        return result

    except Exception as e:
        logger.error(f"Format vertikal gagal ({filepath.name}): {e}")
        return None


def _parse_format_pivot(filepath: Path) -> Optional[pd.DataFrame]:
    """
    Format PIVOT: Ticker sebagai baris, tanggal sebagai kolom header.
    Di-melt menjadi format panjang (long format).

    Contoh
    ------
    Ticker | 2024-06-01 | 2024-06-02 | 2024-06-03
    BBCA   | 250000000  | -50000000  | 100000000
    TLKM   | -80000000  | 20000000   | 150000000
    """
    try:
        df = pd.read_csv(
            filepath,
            encoding=cfg.IDX_FOREIGN_ENCODING,
            index_col=0,
            on_bad_lines="skip",
        )
        df.index.name = "ticker"
        df.index      = df.index.astype(str).str.upper().str.strip()

        # Melt wide → long
        df_long = df.reset_index().melt(
            id_vars="ticker",
            var_name="date",
            value_name="net_buy_sell",
        )

        df_long["date"]         = pd.to_datetime(df_long["date"], errors="coerce")
        df_long["net_buy_sell"] = pd.to_numeric(
            df_long["net_buy_sell"].astype(str).str.replace(",", ""),
            errors="coerce",
        )
        df_long["foreign_buy"]  = None
        df_long["foreign_sell"] = None

        df_long = df_long.dropna(subset=["date", "net_buy_sell"])
        df_long = df_long[df_long["ticker"].str.len().between(1, 6)]

        logger.info(f"  ✓ {filepath.name}: {df_long['ticker'].nunique()} saham (format pivot)")
        return df_long[["ticker", "date", "foreign_buy", "foreign_sell", "net_buy_sell"]]

    except Exception as e:
        logger.error(f"Format pivot gagal ({filepath.name}): {e}")
        return None


# =============================================================================
# INTERNAL — HELPERS
# =============================================================================

def _clean_number(series: pd.Series) -> pd.Series:
    """
    Bersihkan angka dari format IDX yang tidak konsisten.
    Handle: "1.250.000.000", "1,250,000,000", "(500000000)", "1250000000"
    """
    s = series.astype(str).str.strip()

    # Handle tanda kurung = negatif: (500000) → -500000
    negative_mask = s.str.startswith("(") & s.str.endswith(")")
    s = s.str.replace(r"[()]", "", regex=True)

    # Deteksi apakah titik dipakai sebagai ribuan atau desimal
    # Heuristik: jika ada format "1.234.567" → titik = ribuan
    has_multi_dot = s.str.count(r"\.").gt(1)
    s_clean = s.copy()
    s_clean[has_multi_dot] = s[has_multi_dot].str.replace(".", "", regex=False)

    # Hapus koma (separator ribuan gaya barat)
    s_clean = s_clean.str.replace(",", "", regex=False)

    result = pd.to_numeric(s_clean, errors="coerce")

    # Terapkan negatif
    result[negative_mask] = result[negative_mask].abs() * -1
    return result


# =============================================================================
# HELPER — buat sample CSV untuk testing
# =============================================================================

def create_sample_csv(
    target_date: date = None,
    output_dir: Path = None,
) -> Path:
    """
    Buat file CSV contoh dengan data random untuk testing.
    Tidak perlu download dari IDX.

    Contoh
    ------
    path = create_sample_csv()
    df   = load_foreign_flow(["BBCA", "TLKM"])
    """
    import random
    random.seed(42)

    target_date = target_date or date.today()
    output_dir  = output_dir or cfg.DATA_RAW_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"foreign_flow_{target_date.strftime(cfg.IDX_FOREIGN_DATE_FORMAT)}.csv"

    rows = []
    for ticker in cfg.DEFAULT_UNIVERSE:
        buy  = random.randint(10_000, 800_000) * 1_000_000
        sell = random.randint(10_000, 800_000) * 1_000_000
        rows.append({
            "StockCode"  : ticker,
            "StockName"  : ticker,
            "ForeignBuy" : buy,
            "ForeignSell": sell,
            "NetBuySell" : buy - sell,
        })

    pd.DataFrame(rows).to_csv(output_path, index=False)
    logger.info(f"Sample CSV dibuat: {output_path} ({len(rows)} saham)")
    return output_path


# =============================================================================
# QUICK TEST — python src/data_fetcher/idx_foreign_parser.py
# =============================================================================

if __name__ == "__main__":
    import sys
    from datetime import timedelta

    logging.basicConfig(level=logging.INFO, format=cfg.LOG_FORMAT)

    # Buat 5 hari sample data jika belum ada
    existing = _get_sorted_files()
    if not existing:
        print("Tidak ada file foreign flow, membuat 5 hari sample data...")
        today = date.today()
        for i in range(5):
            d = today - timedelta(days=i)
            if d.weekday() < 5:  # skip weekend
                create_sample_csv(target_date=d)
        print()

    # Test load_foreign_flow
    test_tickers = ["BBCA", "BBRI", "TLKM", "ASII", "BMRI"]
    print(f"{'='*60}")
    print(f"  TEST load_foreign_flow — {test_tickers}")
    print(f"{'='*60}")
    df = load_foreign_flow(test_tickers, days=5)
    if not df.empty:
        print(df.to_string(index=False))

    # Test get_net_5d
    print(f"\n{'='*60}")
    print("  TEST get_net_5d (akumulasi 5 hari)")
    print(f"{'='*60}")
    net = get_net_5d(test_tickers)
    for ticker, val in sorted(net.items(), key=lambda x: x[1], reverse=True):
        bar    = "▓" * int(abs(val) / 50_000_000_000)
        sign   = "🟢 BUY " if val >= 0 else "🔴 SELL"
        print(f"  {ticker:<6} {sign}  Rp {val/1e9:>+8.1f} M  {bar}")

    # Test tanggal tersedia
    print(f"\n  Tanggal tersedia: {get_available_dates()}")