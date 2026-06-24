# =============================================================================
# src/data_fetcher/idx_foreign_parser.py
#
# Parse berbagai format CSV foreign flow untuk screening saham IDX.
#
# FORMAT YANG DIDUKUNG:
#
# Format A — Standar IDX (kolom: StockCode, ForeignBuy, ForeignSell, NetBuySell)
#   Nilai dalam RUPIAH
#   Nama file: foreign_flow_YYYYMMDD.csv
#
# Format B — Export broker/RTI (kolom: Code, Last, Frg Buy, Frg Sell, Net Buy)
#   Nilai dalam LOT → dikonversi otomatis ke Rupiah pakai kolom Last (harga)
#   Nama file: bebas, tapi harus ada di data/raw/
#
# Format C — Pivot (ticker sebagai baris, tanggal sebagai kolom)
#
# CARA PAKAI:
#   from src.data_fetcher.idx_foreign_parser import load_foreign_flow, get_net_5d
#   df  = load_foreign_flow(["BBCA","TLKM"], days=5)
#   net = get_net_5d(["BBCA","TLKM"])
# =============================================================================

import logging
from datetime import date, datetime, timedelta
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
    Baca semua file CSV foreign flow di data/raw/, gabungkan,
    dan hitung akumulasi net_5d per ticker.

    Parameters
    ----------
    tickers : filter ticker, None = semua
    days    : ambil N hari / file terbaru

    Returns
    -------
    DataFrame kolom:
        ticker, date, foreign_buy, foreign_sell, net_buy_sell, net_5d
    Semua nilai dalam RUPIAH.
    """
    files = _get_sorted_files()
    if not files:
        logger.warning(
            "Tidak ada file foreign flow di data/raw/\n"
            "  Upload CSV via dashboard atau simpan manual ke folder data/raw/"
        )
        return pd.DataFrame()

    recent = files[-days:] if len(files) > days else files
    logger.info(f"Membaca {len(recent)} file foreign flow...")

    dfs = []
    for f in recent:
        df = _parse_file(f)
        if df is not None and not df.empty:
            dfs.append(df)

    if not dfs:
        logger.error("Semua file gagal di-parse.")
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)

    # Filter ticker
    if tickers:
        combined = combined[combined["ticker"].isin([t.upper() for t in tickers])]

    # Deduplicate
    combined = combined.drop_duplicates(subset=["ticker","date"])
    combined = combined.sort_values(["ticker","date"]).reset_index(drop=True)

    # Akumulasi net_5d rolling per ticker
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
    """Return hanya baris hari terakhir yang tersedia per ticker."""
    df = load_foreign_flow(tickers, days=5)
    if df.empty:
        return df
    latest = df["date"].max()
    return df[df["date"] == latest].reset_index(drop=True)


def get_net_5d(tickers: List[str] = None) -> Dict[str, float]:
    """
    Return dict { ticker → net_buy_sell_5hari } dalam Rupiah.
    Positif = net buy, negatif = net sell.
    """
    df = load_foreign_flow(tickers, days=5)
    if df.empty:
        return {}
    return df.sort_values("date").groupby("ticker")["net_5d"].last().to_dict()


def get_available_dates() -> List[date]:
    """Return list tanggal file yang tersedia di data/raw/."""
    dates = []
    for f in _get_sorted_files():
        date_str = f.stem.replace("foreign_flow_","")
        try:
            dates.append(datetime.strptime(date_str, cfg.IDX_FOREIGN_DATE_FORMAT).date())
        except ValueError:
            pass
    return sorted(dates)


# =============================================================================
# INTERNAL — FILE DISCOVERY
# =============================================================================

def _get_sorted_files() -> List[Path]:
    """
    Return semua CSV di data/raw/ yang namanya foreign_flow_YYYYMMDD.csv,
    diurutkan dari lama ke baru.
    File dengan nama lain (misal upload langsung) diabaikan.
    """
    cfg.DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for f in cfg.DATA_RAW_DIR.glob("*.csv"):
        # Terima foreign_flow_YYYYMMDD.csv atau foreign_flow_upload_*.csv
        stem = f.stem
        date_str = stem.replace("foreign_flow_","").split("_")[0]
        try:
            datetime.strptime(date_str, cfg.IDX_FOREIGN_DATE_FORMAT)
            files.append(f)
        except ValueError:
            # Coba juga file yang tidak pakai prefix (upload langsung)
            if "foreign" in stem.lower() or "frg" in stem.lower():
                files.append(f)
    return sorted(set(files))


# =============================================================================
# INTERNAL — AUTO-DETECT FORMAT & PARSE
# =============================================================================

def _parse_file(filepath: Path) -> Optional[pd.DataFrame]:
    """Auto-detect format dan parse file CSV."""
    try:
        sample = pd.read_csv(
            filepath,
            encoding=cfg.IDX_FOREIGN_ENCODING,
            nrows=3,
            on_bad_lines="skip",
        )
        cols = [str(c).lower().strip().replace(" ","_") for c in sample.columns]

        # Format B: kolom 'code', 'last', 'frg_buy' → broker/RTI export
        if any(c in cols for c in ["code","frg_buy","frg_sell","net_buy"]):
            return _parse_format_broker(filepath)

        # Format A: kolom 'stockcode', 'foreignbuy' → IDX standar (nilai Rupiah)
        if any(c in cols for c in ["stockcode","stock_code","kode_saham","kode"]):
            return _parse_format_idx(filepath)

        # Format C: pivot (tanggal di header)
        if any(str(c).startswith("20") for c in sample.columns):
            return _parse_format_pivot(filepath)

        # Fallback: coba broker dulu, lalu IDX
        logger.warning(f"{filepath.name}: format tidak dikenal, coba auto-parse...")
        result = _parse_format_broker(filepath)
        if result is not None and not result.empty:
            return result
        return _parse_format_idx(filepath)

    except Exception as e:
        logger.error(f"Gagal baca {filepath.name}: {e}")
        return None


def _parse_format_broker(filepath: Path) -> Optional[pd.DataFrame]:
    """
    Format B — Export broker / RTI Business:
    Code | Last | Change | Change(%) | ... | Frg Buy | Frg Sell | Net Buy

    Nilai Frg Buy/Sell/Net Buy dalam LOT.
    Konversi ke Rupiah: nilai_lot × 100 × Last (harga per lembar)

    Tanggal diambil dari nama file jika ada (foreign_flow_YYYYMMDD.csv),
    atau pakai tanggal hari ini sebagai fallback.
    """
    try:
        df = pd.read_csv(
            filepath,
            encoding=cfg.IDX_FOREIGN_ENCODING,
            on_bad_lines="skip",
            thousands=",",    # handle "39,182,257" langsung
        )

        # Normalisasi nama kolom
        df.columns = [str(c).lower().strip().replace(" ","_") for c in df.columns]

        rename_map = {
            "code"     : "ticker",
            "symbol"   : "ticker",
            "last"     : "last_price",
            "close"    : "last_price",
            "harga"    : "last_price",
            "frg_buy"  : "lot_buy",
            "frg._buy" : "lot_buy",
            "foreign_buy": "lot_buy",
            "frg_sell" : "lot_sell",
            "frg._sell": "lot_sell",
            "foreign_sell": "lot_sell",
            "net_buy"  : "lot_net",
            "net_sell" : "lot_net",
            "net"      : "lot_net",
        }
        df = df.rename(columns={k:v for k,v in rename_map.items() if k in df.columns})

        if "ticker" not in df.columns:
            return None

        # Bersihkan angka (kadang masih ada koma meski pakai thousands=",")
        for col in ["last_price","lot_buy","lot_sell","lot_net"]:
            if col in df.columns:
                df[col] = _clean_number(df[col])

        # Hitung last_price jika tidak ada (fallback = 0, akan bikin nilai Rp = 0)
        if "last_price" not in df.columns:
            df["last_price"] = 0
            logger.warning(f"{filepath.name}: kolom harga tidak ditemukan, konversi Rupiah tidak akurat")

        # Konversi LOT → RUPIAH
        # 1 lot = 100 lembar saham
        df["foreign_buy"]  = df.get("lot_buy",  pd.Series(0, index=df.index)).fillna(0) * 100 * df["last_price"]
        df["foreign_sell"] = df.get("lot_sell", pd.Series(0, index=df.index)).fillna(0) * 100 * df["last_price"]

        if "lot_net" in df.columns:
            df["net_buy_sell"] = df["lot_net"].fillna(0) * 100 * df["last_price"]
        else:
            df["net_buy_sell"] = df["foreign_buy"] - df["foreign_sell"]

        # Ambil tanggal dari nama file, fallback hari ini
        df["date"] = _date_from_filename(filepath)

        # Bersihkan ticker
        df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
        df = df[df["ticker"].str.match(r"^[A-Z0-9]{1,6}$")]
        df = df.dropna(subset=["ticker","net_buy_sell"])

        result = df[["ticker","date","foreign_buy","foreign_sell","net_buy_sell"]].copy()
        logger.info(f"  ✓ {filepath.name}: {len(result)} saham (format broker, konversi lot→Rp)")
        return result

    except Exception as e:
        logger.error(f"Format broker gagal ({filepath.name}): {e}")
        return None


def _parse_format_idx(filepath: Path) -> Optional[pd.DataFrame]:
    """
    Format A — IDX standar:
    StockCode | StockName | ForeignBuy | ForeignSell | NetBuySell
    Nilai sudah dalam RUPIAH, tidak perlu konversi.
    """
    try:
        df = pd.read_csv(
            filepath,
            encoding=cfg.IDX_FOREIGN_ENCODING,
            on_bad_lines="skip",
        )
        df.columns = [str(c).lower().strip().replace(" ","_") for c in df.columns]

        rename_map = {
            "stockcode"       : "ticker",
            "stock_code"      : "ticker",
            "kode_saham"      : "ticker",
            "kode"            : "ticker",
            "emiten"          : "ticker",
            "foreignbuy"      : "foreign_buy",
            "foreign_buy"     : "foreign_buy",
            "pembelian_asing" : "foreign_buy",
            "foreignsell"     : "foreign_sell",
            "foreign_sell"    : "foreign_sell",
            "penjualan_asing" : "foreign_sell",
            "netbuysell"      : "net_buy_sell",
            "net_buy_sell"    : "net_buy_sell",
            "net_beli"        : "net_buy_sell",
            "net"             : "net_buy_sell",
        }
        df = df.rename(columns={k:v for k,v in rename_map.items() if k in df.columns})

        if "ticker" not in df.columns:
            return None

        for col in ["foreign_buy","foreign_sell","net_buy_sell"]:
            if col in df.columns:
                df[col] = _clean_number(df[col])

        if "net_buy_sell" not in df.columns:
            if "foreign_buy" in df.columns and "foreign_sell" in df.columns:
                df["net_buy_sell"] = df["foreign_buy"] - df["foreign_sell"]
            else:
                return None

        if "foreign_buy"  not in df.columns: df["foreign_buy"]  = None
        if "foreign_sell" not in df.columns: df["foreign_sell"] = None

        df["date"]   = _date_from_filename(filepath)
        df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
        df = df[df["ticker"].str.match(r"^[A-Z0-9]{1,6}$")]
        df = df.dropna(subset=["ticker","net_buy_sell"])

        result = df[["ticker","date","foreign_buy","foreign_sell","net_buy_sell"]].copy()
        logger.info(f"  ✓ {filepath.name}: {len(result)} saham (format IDX, nilai Rupiah)")
        return result

    except Exception as e:
        logger.error(f"Format IDX gagal ({filepath.name}): {e}")
        return None


def _parse_format_pivot(filepath: Path) -> Optional[pd.DataFrame]:
    """Format C — Pivot: ticker = baris, tanggal = kolom."""
    try:
        df = pd.read_csv(filepath, encoding=cfg.IDX_FOREIGN_ENCODING,
                         index_col=0, on_bad_lines="skip")
        df.index.name = "ticker"
        df.index = df.index.astype(str).str.upper().str.strip()

        df_long = df.reset_index().melt(id_vars="ticker",
                                        var_name="date", value_name="net_buy_sell")
        df_long["date"]         = pd.to_datetime(df_long["date"], errors="coerce")
        df_long["net_buy_sell"] = pd.to_numeric(
            df_long["net_buy_sell"].astype(str).str.replace(",",""), errors="coerce")
        df_long["foreign_buy"]  = None
        df_long["foreign_sell"] = None

        df_long = df_long.dropna(subset=["date","net_buy_sell"])
        df_long = df_long[df_long["ticker"].str.match(r"^[A-Z0-9]{1,6}$")]

        logger.info(f"  ✓ {filepath.name}: {df_long['ticker'].nunique()} saham (format pivot)")
        return df_long[["ticker","date","foreign_buy","foreign_sell","net_buy_sell"]]

    except Exception as e:
        logger.error(f"Format pivot gagal ({filepath.name}): {e}")
        return None


# =============================================================================
# HELPERS
# =============================================================================

def _date_from_filename(filepath: Path) -> pd.Timestamp:
    """Ambil tanggal dari nama file. Fallback ke hari ini."""
    stem     = filepath.stem
    date_str = stem.replace("foreign_flow_","").split("_")[0]
    try:
        return pd.Timestamp(datetime.strptime(date_str, cfg.IDX_FOREIGN_DATE_FORMAT))
    except ValueError:
        logger.debug(f"Tanggal tidak ditemukan di nama file {filepath.name}, pakai hari ini.")
        return pd.Timestamp(date.today())


def _clean_number(series: pd.Series) -> pd.Series:
    """Bersihkan format angka: koma ribuan, kurung = negatif, titik ribuan."""
    s = series.astype(str).str.strip()
    negative_mask = s.str.startswith("(") & s.str.endswith(")")
    s = s.str.replace(r"[()]","", regex=True)
    has_multi_dot = s.str.count(r"\.").gt(1)
    s[has_multi_dot] = s[has_multi_dot].str.replace(".","", regex=False)
    s = s.str.replace(",","", regex=False)
    result = pd.to_numeric(s, errors="coerce")
    result[negative_mask] = result[negative_mask].abs() * -1
    return result


# =============================================================================
# HELPER — buat sample CSV untuk testing
# =============================================================================

def create_sample_csv(target_date: date = None, output_dir: Path = None) -> Path:
    """Buat file CSV contoh format IDX untuk testing."""
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
        rows.append({"StockCode":ticker,"StockName":ticker,
                     "ForeignBuy":buy,"ForeignSell":sell,"NetBuySell":buy-sell})
    pd.DataFrame(rows).to_csv(output_path, index=False)
    logger.info(f"Sample CSV dibuat: {output_path}")
    return output_path


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    import shutil
    logging.basicConfig(level=logging.INFO, format=cfg.LOG_FORMAT)

    # Copy file upload ke data/raw/ dengan nama yang benar
    upload = Path("/mnt/user-data/uploads/foreign.csv")
    if upload.exists():
        dest = cfg.DATA_RAW_DIR / f"foreign_flow_{date.today().strftime('%Y%m%d')}.csv"
        shutil.copy(upload, dest)
        print(f"File ditest: {dest.name}")

    tickers = ["GOTO","BBCA","BBRI","TLKM","ADRO","MDKA"]
    print(f"\nTest load_foreign_flow: {tickers}")
    df = load_foreign_flow(tickers, days=5)
    if not df.empty:
        print(df[["ticker","date","foreign_buy","foreign_sell","net_buy_sell","net_5d"]].to_string(index=False))

    print(f"\nTest get_net_5d:")
    net = get_net_5d(tickers)
    for t, v in sorted(net.items(), key=lambda x: x[1], reverse=True):
        bar  = "▓" * min(int(abs(v)/10_000_000_000), 20)
        sign = "🟢 BUY " if v >= 0 else "🔴 SELL"
        print(f"  {t:<6} {sign}  Rp {v/1e9:>+8.1f}M  {bar}")
