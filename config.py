# =============================================================================
# config.py — Konfigurasi utama IDX Screener
# Semua threshold, path, dan parameter ada di sini.
# Jangan hardcode angka di dalam logika sinyal!
#
# VERSI INI = config asli + parameter Stage 1/2 (accumulation & markup baru,
# berbasis OBV/volatility) + Stage 3 (risk management: entry/stop/target).
# Ditandai # >>> STAGE 1/2 dan # >>> STAGE 3 di bagian yang baru ditambahkan.
# =============================================================================

from pathlib import Path
from dotenv import load_dotenv
import os
import pandas as pd  # taruh dekat import lain di atas

load_dotenv()  # baca .env untuk API keys

YFINANCE_BATCH_DELAY_SEC = 2   # jeda antar batch, hindari rate limit Yahoo

# =============================================================================
# PATHS
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR            = BASE_DIR / "data"
DATA_RAW_DIR        = DATA_DIR / "raw"
DATA_PROCESSED_DIR  = DATA_DIR / "processed"
DATA_UNIVERSE_DIR   = DATA_DIR / "universe"

# Pastikan folder ada saat pertama kali dijalankan
for _dir in [DATA_RAW_DIR, DATA_PROCESSED_DIR, DATA_UNIVERSE_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# File cache & output
OHLCV_CACHE_PATH    = DATA_PROCESSED_DIR / "ohlcv_cache.parquet"
SIGNALS_OUTPUT_PATH = DATA_PROCESSED_DIR / "signals_latest.csv"

# Daftar saham universe
UNIVERSE_LQ45_PATH      = DATA_UNIVERSE_DIR / "idx_lq45.csv"
UNIVERSE_HIDIV20_PATH   = DATA_UNIVERSE_DIR / "idx_idxhidiv20.csv"
UNIVERSE_WATCHLIST_PATH = DATA_UNIVERSE_DIR / "custom_watchlist.csv"

# =============================================================================
# DATA SOURCE
# =============================================================================

# Yahoo Finance
YFINANCE_SUFFIX  = ".JK"          # suffix ticker IDX di Yahoo Finance
YFINANCE_PERIOD  = "1y"          # periode download default (60 hari)
YFINANCE_INTERVAL = "1d"          # interval: 1d = harian
YFINANCE_BATCH_SIZE = 20          # max ticker per request (hindari rate limit)

# IDX Foreign Flow (download manual dari IDX.co.id)
IDX_FOREIGN_DATE_FORMAT = "%Y%m%d"   # format nama file: foreign_flow_YYYYMMDD.csv
IDX_FOREIGN_ENCODING    = "utf-8"

# API premium (Fase 3) — ambil dari .env
RTI_API_KEY  = os.getenv("RTI_API_KEY", "")
RTI_BASE_URL = os.getenv("RTI_BASE_URL", "https://api.rtiinvestor.com/v1")

# =============================================================================
# PARAMETER SINYAL — ADMD (versi lama, berbasis foreign flow)
# Sudah TIDAK dipakai oleh accumulation.py & distribution.py versi baru,
# dibiarkan di sini kalau-kalau masih dirujuk modul lain / mau dipakai lagi.
# =============================================================================

# --- AKUMULASI (lama) ---
ACCUM_NET_BUY_MIN      = 200_000_000_000   # Rp 200 miliar (dalam rupiah)
ACCUM_WINDOW_DAYS      = 5                 # periode akumulasi
ACCUM_PRICE_CHANGE_MAX = 0.05              # harga naik MAKSIMAL 5% (naik pelan)
ACCUM_PRICE_CHANGE_MIN = -0.01             # tidak boleh turun lebih dari 1%

# --- DISTRIBUSI (lama) ---
DIST_NET_SELL_MIN      = -150_000_000_000  # Rp -150 miliar (negatif = net sell)
DIST_WINDOW_DAYS       = 5
DIST_PRICE_CHANGE_MAX  = 0.02              # harga stagnan: naik maks 2%
DIST_PRICE_CHANGE_MIN  = -0.10             # atau turun maks 10%

# --- MARK UP ---
# Volume melonjak, harga breakout — dipakai ulang oleh markup.py versi baru
MARKUP_VOLUME_RATIO_MIN  = 1.5             # volume >= 1.5x rata-rata 20 hari
MARKUP_VOLUME_AVG_WINDOW = 20              # hari untuk hitung rata-rata volume
MARKUP_PRICE_BREAKOUT    = 0.03            # harga naik minimal 3% dalam 1 hari
MARKUP_BREAKOUT_WINDOW   = 5               # atau breakout dari high 5 hari terakhir

# --- MARK DOWN ---
# Dipakai ulang oleh markdown.py versi baru (kecuali MARKDOWN_NET_SELL_MIN, sudah tidak dipakai)
MARKDOWN_PRICE_DROP_MIN  = -0.05           # harga turun minimal 5% dalam 3 hari
MARKDOWN_PRICE_WINDOW    = 3
MARKDOWN_NET_SELL_MIN    = -50_000_000_000 # net sell asing Rp -50 miliar (lama, tidak dipakai lagi)
MARKDOWN_VOLUME_RATIO_MIN = 1.2            # volume di atas rata-rata (konfirmasi)

# =============================================================================
# >>> STAGE 1 & 2 — AKUMULASI/DISTRIBUSI & BREAKOUT/BREAKDOWN (versi baru)
# Dipakai accumulation.py, distribution.py, markup.py, markdown.py versi baru
# yang berbasis OBV + volatility contraction — tidak butuh foreign flow.
# =============================================================================

ACCUM_WINDOW_DAYS_V2      = 15    # window hitung slope OBV (periode akumulasi/distribusi)
ACCUM_BB_PERIOD           = 20    # periode Bollinger Band untuk ukur volatilitas
ACCUM_BB_LOOKBACK_DAYS    = 100   # histori pembanding untuk hitung persentil width
ACCUM_BB_PERCENTILE_MAX   = 0.25  # width sekarang harus di bawah persentil ke-25 histori

# =============================================================================
# >>> STAGE 3 — TRADE SETUP (entry / stop loss / target)
# Dipakai risk_manager.py untuk hitung level trading dari sinyal breakout (Mark Up)
# =============================================================================

STAGE3_RANGE_LOOKBACK_DAYS  = 20    # window untuk hitung tinggi range akumulasi (support-resistance)
STAGE3_ATR_PERIOD           = 14    # periode ATR standar
STAGE3_ATR_STOP_MULTIPLIER  = 1.5   # stop loss = range_low - (ATR x multiplier ini)
STAGE3_MIN_RISK_REWARD      = 2.0   # sinyal dengan RR di bawah ini dibuang dari hasil screening

# =============================================================================
# FALLBACK UNIVERSE — dipakai jika idx_all.csv tidak ada / gagal parse
# =============================================================================

# Emergency fallback minimal — dipakai HANYA jika idx_all.csv gagal dibaca total
LQ45 = ["BBCA", "BBRI", "BMRI", "TLKM", "ASII"]

# =============================================================================
# SCREENING UNIVERSE — Full IDX, sumber: daftar perusahaan tercatat BEI
# =============================================================================

import pandas as pd

UNIVERSE_ALL_PATH = DATA_UNIVERSE_DIR / "idx_all.csv"
LIQUID_BOARDS = {"Papan Utama"}

def load_idx_listing(path: Path):
    ...  # (kode yang sama seperti sebelumnya, tidak berubah)
# =============================================================================
# SCREENING UNIVERSE — Full IDX, sumber: daftar perusahaan tercatat BEI
# =============================================================================

UNIVERSE_ALL_PATH = DATA_UNIVERSE_DIR / "idx_all.csv"

# Papan yang dianggap "likuid" — sinyal berbasis foreign flow (Akumulasi/Distribusi) full jalan
LIQUID_BOARDS = {"Papan Utama"}

def load_idx_listing(path: Path):
    """
    Baca daftar resmi perusahaan tercatat BEI.
    Kolom sumber: No, Kode, Nama Perusahaan, Tanggal Pencatatan, Saham, Papan Pencatatan
    """
    if not path.exists():
        return pd.DataFrame(columns=["stock_code", "stock_name", "board", "listing_date"])

    df = pd.read_csv(path, thousands=",")  # "Saham" biasanya ada pemisah ribuan
    df = df.rename(columns={
        "Kode": "stock_code",
        "Nama Perusahaan": "stock_name",
        "Papan Pencatatan": "board",
        "Tanggal Pencatatan": "listing_date",
        "Saham": "shares_outstanding",
    })

    df["stock_code"] = df["stock_code"].astype(str).str.upper().str.strip()
    df["board"] = df["board"].astype(str).str.strip()

    # Buang baris kotor: kode bukan 4 huruf, atau papan kosong/NaN
    df = df[df["stock_code"].str.match(r"^[A-Z]{4}$", na=False)]
    df = df.dropna(subset=["board"])

    return df.drop_duplicates(subset="stock_code").reset_index(drop=True)


_LISTING = load_idx_listing(UNIVERSE_ALL_PATH)

# Semua saham → dipakai untuk golden cross & sinyal berbasis harga/volume
DEFAULT_UNIVERSE = _LISTING["stock_code"].tolist() if not _LISTING.empty else LQ45

# Subset likuid (Papan Utama) → dipakai untuk sinyal yang butuh foreign flow reliable
LIQUID_UNIVERSE = (
    _LISTING.loc[_LISTING["board"].isin(LIQUID_BOARDS), "stock_code"].tolist()
    if not _LISTING.empty else LQ45
)

# Map stock_code -> board, dipakai sync_stocks() untuk isi kolom board di DB
STOCK_BOARD_MAP = dict(zip(_LISTING["stock_code"], _LISTING["board"])) if not _LISTING.empty else {}


# =============================================================================
# Parsing tanggal listing (format BEI biasanya dd-mmm-yyyy atau dd/mm/yyyy, jadi pakai errors="coerce")
# =============================================================================
if not _LISTING.empty and "listing_date" in _LISTING.columns:
    _LISTING["listing_date"] = pd.to_datetime(
        _LISTING["listing_date"], errors="coerce", dayfirst=True
    ).dt.date

# =============================================================================
# FILTER SAHAM BARU LISTING — histori belum cukup untuk MA50/MA200 (golden cross)
# =============================================================================

MIN_LISTING_AGE_DAYS = 200  # ganti ke 50-60 kalau golden cross Anda pakai MA50, bukan MA200

def filter_by_listing_age(tickers: list[str], min_age_days: int = MIN_LISTING_AGE_DAYS,
                           reference_date=None) -> list[str]:
    """
    Buang ticker yang listing_date-nya lebih baru dari cutoff — histori harga
    belum cukup untuk indikator seperti golden cross (MA50/MA200).
    Ticker yang tidak ditemukan di data listing (misal fallback LQ45) tetap
    diikutkan apa adanya, karena saham lama pasti aman.
    """
    from datetime import date, timedelta
    import logging

    if _LISTING.empty or "listing_date" not in _LISTING.columns:
        return tickers

    reference_date = reference_date or date.today()
    cutoff = reference_date - timedelta(days=min_age_days)
    listing_map = dict(zip(_LISTING["stock_code"], _LISTING["listing_date"]))

    result, excluded = [], []
    for t in tickers:
        ld = listing_map.get(t)
        if ld is None or pd.isna(ld):
            result.append(t)          # tanggal tidak diketahui -> jangan exclude, lebih aman
        elif ld <= cutoff:
            result.append(t)          # sudah cukup umur
        else:
            excluded.append(t)        # terlalu baru, skip dari signal generation

    if excluded:
        logging.getLogger(__name__).info(
            f"Exclude {len(excluded)} saham baru listing (<{min_age_days} hari): "
            f"{excluded[:10]}{'...' if len(excluded) > 10 else ''}"
        )

    return result

# =============================================================================
# LOGGING
# =============================================================================

LOG_LEVEL  = "INFO"   # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_FILE   = BASE_DIR / "screener.log"

# =============================================================================
# DASHBOARD (Streamlit — Fase 2)
# =============================================================================

DASHBOARD_TITLE       = "IDX Screener — ADMD"
DASHBOARD_REFRESH_SEC = 3600          # auto-refresh tiap 1 jam (detik)
DASHBOARD_MAX_ROWS    = 50            # max baris ditampilkan di tabel

# Badge warna per sinyal (untuk UI)
SIGNAL_COLORS = {
    "Akumulasi" : "#22c55e",   # hijau
    "Distribusi": "#f97316",   # oranye
    "Mark Up"   : "#3b82f6",   # biru
    "Mark Down" : "#ef4444",   # merah
}

PHASE_COLORS = {
    "accumulation": "#22c55e",
    "markup":       "#3b82f6",
    "distribution": "#f97316",
    "markdown":     "#ef4444",
    "unknown":      "#9ca3af",
}

# =============================================================================
# SCHEDULER (GitHub Actions / APScheduler — Fase 2 & 3)
# =============================================================================

# Jam refresh data (WIB = UTC+7)
# Pasar IDX tutup 15:00 WIB, data tersedia ~16:00 WIB
SCHEDULER_HOUR_WIB   = 17   # jam 17.00 WIB
SCHEDULER_MINUTE     = 0
SCHEDULER_TIMEZONE   = "Asia/Jakarta"