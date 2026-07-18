import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

url = os.getenv("DATABASE_URL")  # <-- isi nama variable-nya, bukan URL-nya
print("Connecting to:", url[:40], "...")  # print sebagian untuk verifikasi

conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
tables = cur.fetchall()
print("Tabel ditemukan:", [t[0] for t in tables])
conn.close()
print("Koneksi berhasil!")