# =============================================================================
# config.py — Konfigurasi utama IDX Screener
# Auto-detect: lokal vs Streamlit Cloud
# =============================================================================

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# =============================================================================
# DETECT ENVIRONMENT
# =============================================================================

IS_CLOUD = os.environ.get("STREAMLIT_SHARING_MODE") == "streamlit_sharing" \
        or os.environ.get("IS_STREAMLIT_CLOUD", "").lower() == "true" \
        or not Path("/home").exists() \
        or os.environ.get("HOSTNAME", "").startswith("streamlit")

# =============================================================================
# PATHS — lokal pakai ./data, cloud pakai /tmp
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent

if IS_CLOUD:
    DATA_DIR = Path("/tmp/idxscreener")
else:
    DATA_DIR = BASE_DIR / "data"

DATA_RAW_DIR        = DATA_DIR / "raw"
DATA_PROCESSED_DIR  = DATA_DIR / "processed"
DATA_UNIVERSE_DIR   = DATA_DIR / "universe"

for _dir in [DATA_RAW_DIR, DATA_PROCESSED_DIR, DATA_UNIVERSE_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

OHLCV_CACHE_PATH    = DATA_PROCESSED_DIR / "ohlcv_cache.parquet"
SIGNALS_OUTPUT_PATH = DATA_PROCESSED_DIR / "signals_latest.csv"

UNIVERSE_LQ45_PATH      = DATA_UNIVERSE_DIR / "idx_lq45.csv"
UNIVERSE_HIDIV20_PATH   = DATA_UNIVERSE_DIR / "idx_idxhidiv20.csv"
UNIVERSE_WATCHLIST_PATH = DATA_UNIVERSE_DIR / "custom_watchlist.csv"

# =============================================================================
# DATA SOURCE
# =============================================================================

YFINANCE_SUFFIX    = ".JK"
YFINANCE_PERIOD    = "60d"
YFINANCE_INTERVAL  = "1d"
YFINANCE_BATCH_SIZE = 20

IDX_FOREIGN_DATE_FORMAT = "%Y%m%d"
IDX_FOREIGN_ENCODING    = "utf-8"

RTI_API_KEY  = os.getenv("RTI_API_KEY", "")
RTI_BASE_URL = os.getenv("RTI_BASE_URL", "")
SECTORS_API_KEY = os.getenv("SECTORS_API_KEY", "")

# =============================================================================
# PARAMETER SINYAL — ADMD
# =============================================================================

ACCUM_NET_BUY_MIN      = 200_000_000_000
ACCUM_WINDOW_DAYS      = 5
ACCUM_PRICE_CHANGE_MAX = 0.05
ACCUM_PRICE_CHANGE_MIN = -0.01

DIST_NET_SELL_MIN      = -150_000_000_000
DIST_WINDOW_DAYS       = 5
DIST_PRICE_CHANGE_MAX  = 0.02
DIST_PRICE_CHANGE_MIN  = -0.10

MARKUP_VOLUME_RATIO_MIN  = 1.5
MARKUP_VOLUME_AVG_WINDOW = 20
MARKUP_PRICE_BREAKOUT    = 0.03
MARKUP_BREAKOUT_WINDOW   = 5

MARKDOWN_PRICE_DROP_MIN   = -0.05
MARKDOWN_PRICE_WINDOW     = 3
MARKDOWN_NET_SELL_MIN     = -50_000_000_000
MARKDOWN_VOLUME_RATIO_MIN = 1.2

# =============================================================================
# UNIVERSE
# =============================================================================

LQ45 = [
    "AALI","ACES","ADRO","AKRA","AMRT","ASII","ASRI","BBCA",
    "BBNI","BBRI","BBTN","BMRI","BRPT","BSDE","CPIN","EMTK",
    "ERAA","EXCL","GGRM","GOTO","HMSP","HRUM","ICBP","INCO",
    "INDF","INTP","ITMG","JPFA","JSMR","KLBF","MAPI","MBMA",
    "MDKA","MEDC","MIKA","PGAS","PTBA","PTPP","SMGR","TBIG",
    "TKIM","TLKM","TOWR","UNTR","UNVR",
]

IDXHIDIV20 = [
    "ADMR","ASII","BBCA","BBNI","BBRI","BMRI","BYAN",
    "CPIN","ELSA","GGRM","HMSP","ITMG","JPFA","MBAP",
    "PGAS","PTBA","PTRO","SMGR","TLKM","UNTR",
]

DEFAULT_UNIVERSE = LQ45

# =============================================================================
# LOGGING
# =============================================================================

LOG_LEVEL  = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_FILE   = Path("/tmp/screener.log") if IS_CLOUD else BASE_DIR / "screener.log"

# =============================================================================
# DASHBOARD
# =============================================================================

DASHBOARD_TITLE       = "IDX Screener — ADMD"
DASHBOARD_REFRESH_SEC = 3600
DASHBOARD_MAX_ROWS    = 50

SIGNAL_COLORS = {
    "Akumulasi" : "#22c55e",
    "Distribusi": "#f97316",
    "Mark Up"   : "#3b82f6",
    "Mark Down" : "#ef4444",
}

# =============================================================================
# SCHEDULER
# =============================================================================

SCHEDULER_HOUR_WIB = 17
SCHEDULER_MINUTE   = 0
SCHEDULER_TIMEZONE = "Asia/Jakarta"
