# =============================================================================
# test_new_signals.py — Cek cepat sinyal MA cross & MACD cross, TANPA tulis ke DB
#
# Jalankan dari root project:
#   py test_new_signals.py
#
# Catatan: setelah perubahan run_all(), MA cross & MACD cross TIDAK LAGI
# muncul di kolom 'signal' utama (itu tetap dipakai untuk ADMD). Keduanya
# sekarang ada di kolom terpisah: ma_cross_signal / ma_cross_note dan
# macd_cross_signal / macd_cross_note — supaya tidak saling menggusur
# sinyal ADMD di ticker & hari yang sama.
# =============================================================================

import pandas as pd

from src.signals.screener import run_all

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", None)

print("Menjalankan screener (ini akan download OHLCV, mohon tunggu)...")
df = run_all(save_output=False)

if df.empty:
    print("\nTidak ada sinyal sama sekali. Screener gagal / OHLCV kosong.")
    raise SystemExit

print(f"\nTotal baris (ticker unik): {len(df)}")
print("Daftar signal_type (ADMD) yang muncul:", df["signal"].dropna().unique())

# --- Bagian ADMD seperti biasa ---
admd_cols = [c for c in ["ticker", "signal", "close", "strength", "note"] if c in df.columns]
print("\n--- Sinyal ADMD (kolom 'signal') ---")
print(df[admd_cols].to_string(index=False))

# --- Bagian trend: MA cross ---
if "ma_cross_signal" in df.columns:
    ma_hits = df[df["ma_cross_signal"].notna()]
    print(f"\n--- MA Cross ditemukan: {len(ma_hits)} ticker ---")
    if not ma_hits.empty:
        print(ma_hits[["ticker", "signal", "ma_cross_signal", "ma_cross_note"]].to_string(index=False))
else:
    print("\n[!] Kolom 'ma_cross_signal' tidak ada di hasil — cek apakah run_all() sudah diperbarui.")

# --- Bagian trend: MACD cross ---
if "macd_cross_signal" in df.columns:
    macd_hits = df[df["macd_cross_signal"].notna()]
    print(f"\n--- MACD Cross ditemukan: {len(macd_hits)} ticker ---")
    if not macd_hits.empty:
        print(macd_hits[["ticker", "signal", "macd_cross_signal", "macd_cross_note"]].to_string(index=False))
else:
    print("\n[!] Kolom 'macd_cross_signal' tidak ada di hasil — cek apakah run_all() sudah diperbarui.")

# --- Contoh kasus yang tadinya "hilang": ADMD + trend bentrok di ticker sama ---
if "ma_cross_signal" in df.columns and "macd_cross_signal" in df.columns:
    overlap = df[
        df["signal"].notna()
        & (df["ma_cross_signal"].notna() | df["macd_cross_signal"].notna())
    ]
    print(f"\n--- Ticker dengan sinyal ADMD + trend bersamaan: {len(overlap)} ---")
    if not overlap.empty:
        print(overlap[["ticker", "signal", "ma_cross_signal", "macd_cross_signal"]].to_string(index=False))
