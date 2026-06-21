# =============================================================================
# run_screening.py — CLI entry point IDX Screener
#
# Cara pakai:
#   python run_screening.py                          # semua sinyal, LQ45
#   python run_screening.py --signal Akumulasi       # satu sinyal saja
#   python run_screening.py --tickers BBCA BBRI TLKM # ticker custom
#   python run_screening.py --no-cache               # paksa download ulang
#   python run_screening.py --no-save                # tidak simpan CSV
# =============================================================================

import argparse
import logging
import sys
from pathlib import Path

import config as cfg

logging.basicConfig(
    level=getattr(logging, cfg.LOG_LEVEL),
    format=cfg.LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(cfg.LOG_FILE),
    ],
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="IDX Screener — Akumulasi / Distribusi / Mark Up / Mark Down",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--signal",
        choices=["Akumulasi", "Distribusi", "Mark Up", "Mark Down", "semua"],
        default="semua",
        help=(
            "Sinyal yang dijalankan (default: semua)\n"
            "  Akumulasi  — net buy asing + harga naik pelan\n"
            "  Distribusi — net sell asing + harga stagnan\n"
            "  Mark Up    — volume spike + breakout\n"
            "  Mark Down  — harga turun tajam + net sell berlanjut\n"
        ),
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        metavar="TICKER",
        help="Ticker IDX tanpa .JK, contoh: BBCA BBRI TLKM (default: LQ45)",
    )
    parser.add_argument(
        "--universe",
        choices=["lq45", "hidiv20", "custom"],
        default="lq45",
        help="Universe preset (default: lq45). Diabaikan jika --tickers diisi.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Paksa download ulang OHLCV, abaikan cache",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Jangan simpan hasil ke CSV",
    )
    parser.add_argument(
        "--min-strength",
        type=float,
        default=0.0,
        metavar="N",
        help="Filter: hanya tampilkan sinyal dengan strength >= N (0–100)",
    )
    return parser.parse_args()


def resolve_tickers(args) -> list:
    """Tentukan list ticker berdasarkan --tickers atau --universe."""
    if args.tickers:
        tickers = [t.upper().strip() for t in args.tickers]
        logger.info(f"Universe: custom ({len(tickers)} ticker dari argumen)")
        return tickers

    universe_map = {
        "lq45"   : cfg.LQ45,
        "hidiv20": cfg.IDXHIDIV20,
        "custom" : cfg.DEFAULT_UNIVERSE,
    }
    tickers = universe_map[args.universe]
    logger.info(f"Universe: {args.universe.upper()} ({len(tickers)} ticker)")
    return tickers


def main():
    args    = parse_args()
    tickers = resolve_tickers(args)

    from src.signals.screener import run_all, run_single, print_summary

    use_cache   = not args.no_cache
    save_output = not args.no_save

    logger.info(
        f"Mulai screening — "
        f"sinyal: {args.signal} | ticker: {len(tickers)} | cache: {use_cache}"
    )

    # Jalankan screening
    if args.signal == "semua":
        df = run_all(tickers=tickers, use_cache=use_cache, save_output=save_output)
    else:
        df = run_single(signal_name=args.signal, tickers=tickers, use_cache=use_cache)

    # Filter minimum strength
    if args.min_strength > 0 and not df.empty:
        before = len(df)
        df = df[df["strength"] >= args.min_strength].reset_index(drop=True)
        logger.info(f"Filter strength >= {args.min_strength}: {before} → {len(df)} sinyal")

    # Tampilkan hasil
    print_summary(df)

    if save_output and not df.empty:
        print(f"  💾 Hasil disimpan → {cfg.SIGNALS_OUTPUT_PATH}\n")

    return df


if __name__ == "__main__":
    main()
