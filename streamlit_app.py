# =============================================================================
# streamlit_app.py — Entry point untuk Streamlit Cloud
# File ini harus ada di ROOT project agar Streamlit Cloud bisa detect otomatis
# =============================================================================
import sys
from pathlib import Path

# Pastikan src/ bisa di-import
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Redirect ke app utama
from src.dashboard.app import *
