import logging
import config as cfg
from src.signals.screener import run_all, print_summary

# Supaya log tampil di terminal (penting untuk melihat baris ✗)
logging.basicConfig(level=logging.INFO, format=cfg.LOG_FORMAT)

df = run_all(use_cache=False, save_output=False)
print_summary(df)