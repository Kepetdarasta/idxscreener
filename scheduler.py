# =============================================================================
# scheduler.py — Jalankan ETL pipeline otomatis setiap hari (EOD)
#
# Cara pakai:
#   python scheduler.py          ← jalan terus di background, trigger EOD
#   python scheduler.py --now    ← langsung run sekali sekarang (untuk test)
#
# Requirement:
#   pip install schedule
# =============================================================================

import argparse
import logging
import time
from datetime import date, datetime

import schedule

from etl_pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Jam trigger EOD — 16:15 WIB (market tutup 15:00, data biasanya siap ~16:00)
EOD_TIME = "16:15"


def job():
    today = date.today()
    if today.weekday() >= 5:
        logger.info(f"Skip — hari ini weekend ({today})")
        return
    logger.info(f"Scheduler trigger — mulai ETL untuk {today}")
    run_pipeline(trade_date=today)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="Langsung run sekali sekarang")
    parser.add_argument("--time", default=EOD_TIME, help=f"Jam trigger HH:MM (default {EOD_TIME})")
    args = parser.parse_args()

    if args.now:
        logger.info("Mode --now: langsung run ETL pipeline...")
        run_pipeline(trade_date=date.today())
        return

    logger.info(f"Scheduler aktif — ETL akan jalan setiap hari jam {args.time} WIB")
    logger.info("Tekan Ctrl+C untuk berhenti.")

    schedule.every().day.at(args.time).do(job)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
