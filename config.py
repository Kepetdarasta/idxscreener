# =============================================================================
# config.py — Konfigurasi utama IDX Screener
# Semua threshold, path, dan parameter ada di sini.
# Jangan hardcode angka di dalam logika sinyal!
# =============================================================================

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()  # baca .env untuk API keys

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
YFINANCE_PERIOD  = "60d"          # periode download default (60 hari)
YFINANCE_INTERVAL = "1d"          # interval: 1d = harian
YFINANCE_BATCH_SIZE = 20          # max ticker per request (hindari rate limit)

# IDX Foreign Flow (download manual dari IDX.co.id)
IDX_FOREIGN_DATE_FORMAT = "%Y%m%d"   # format nama file: foreign_flow_YYYYMMDD.csv
IDX_FOREIGN_ENCODING    = "utf-8"

# API premium (Fase 3) — ambil dari .env
RTI_API_KEY  = os.getenv("RTI_API_KEY", "")
RTI_BASE_URL = os.getenv("RTI_BASE_URL", "https://api.rtiinvestor.com/v1")

# =============================================================================
# PARAMETER SINYAL — ADMD
# Ubah di sini untuk fine-tuning, TIDAK perlu menyentuh kode sinyal
# =============================================================================

# --- AKUMULASI ---
# Net buy asing Rp 200 miliar dalam 5 hari, harga naik pelan
ACCUM_NET_BUY_MIN      = 200_000_000_000   # Rp 200 miliar (dalam rupiah)
ACCUM_WINDOW_DAYS      = 5                 # periode akumulasi
ACCUM_PRICE_CHANGE_MAX = 0.05              # harga naik MAKSIMAL 5% (naik pelan)
ACCUM_PRICE_CHANGE_MIN = -0.01             # tidak boleh turun lebih dari 1%

# --- DISTRIBUSI ---
# Net sell asing Rp 150 miliar, harga stagnan/turun, ritel dominan beli
DIST_NET_SELL_MIN      = -150_000_000_000  # Rp -150 miliar (negatif = net sell)
DIST_WINDOW_DAYS       = 5
DIST_PRICE_CHANGE_MAX  = 0.02              # harga stagnan: naik maks 2%
DIST_PRICE_CHANGE_MIN  = -0.10             # atau turun maks 10%

# --- MARK UP ---
# Volume melonjak, harga breakout
MARKUP_VOLUME_RATIO_MIN  = 1.5             # volume >= 1.5x rata-rata 20 hari
MARKUP_VOLUME_AVG_WINDOW = 20              # hari untuk hitung rata-rata volume
MARKUP_PRICE_BREAKOUT    = 0.03            # harga naik minimal 3% dalam 1 hari
MARKUP_BREAKOUT_WINDOW   = 5              # atau breakout dari high 5 hari terakhir

# --- MARK DOWN ---
# Harga turun tajam, net sell asing berlanjut
MARKDOWN_PRICE_DROP_MIN  = -0.05           # harga turun minimal 5% dalam 3 hari
MARKDOWN_PRICE_WINDOW    = 3
MARKDOWN_NET_SELL_MIN    = -50_000_000_000 # net sell asing Rp -50 miliar
MARKDOWN_VOLUME_RATIO_MIN = 1.2            # volume di atas rata-rata (konfirmasi)

# =============================================================================
# SCREENING UNIVERSE DEFAULT
# Saham mana yang di-screen jika tidak ada input spesifik
# =============================================================================

# LQ45 — 45 saham paling likuid di IDX
LQ45 = [
    "AALI", "ACES", "ADRO", "AKRA", "AMRT", "ASII", "ASRI", "BBCA",
    "BBNI", "BBRI", "BBTN", "BMRI", "BRPT", "BSDE", "CPIN", "EMTK",
    "ERAA", "EXCL", "GGRM", "GOTO", "HMSP", "HRUM", "ICBP", "INCO",
    "INDF", "INTP", "ITMG", "JPFA", "JSMR", "KLBF", "MAPI", "MBMA",
    "MDKA", "MEDC", "MIKA", "PGAS", "PTBA", "PTPP", "SMGR", "TBIG",
    "TKIM", "TLKM", "TOWR", "UNTR", "UNVR",
]

# IDX High Dividend 20
IDXHIDIV20 = [
    "ADMR", "ASII", "BBCA", "BBNI", "BBRI", "BMRI", "BYAN",
    "CPIN", "ELSA", "GGRM", "HMSP", "ITMG", "JPFA", "MBAP",
    "PGAS", "PTBA", "PTRO", "SMGR", "TLKM", "UNTR",
]

# Default universe yang dipakai screener
DEFAULT_UNIVERSE = LQ45

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

# =============================================================================
# SCHEDULER (GitHub Actions / APScheduler — Fase 2 & 3)
# =============================================================================

# Jam refresh data (WIB = UTC+7)
# Pasar IDX tutup 15:00 WIB, data tersedia ~16:00 WIB
SCHEDULER_HOUR_WIB   = 17   # jam 17.00 WIB
SCHEDULER_MINUTE     = 0
SCHEDULER_TIMEZONE   = "Asia/Jakarta"