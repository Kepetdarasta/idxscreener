# =============================================================================
# dashboard.py — Dashboard Streamlit IDX Screener V2
#
# Menggabungkan 2 fitur roadmap:
#   1. Dashboard screening dengan filter fase (tab "Screening")
#   2. Chart historis pergerakan fase ADMD (tab "Timeline Fase")
#
# Jalankan:
#   streamlit run dashboard.py
#
# Butuh package tambahan (belum ada di requirements.txt sebelumnya):
#   pip install streamlit plotly
# =============================================================================

import os
from pathlib import Path
from datetime import date

import pandas as pd
import psycopg2
import streamlit as st
import plotly.express as px
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

import config as cfg

# =============================================================================
# SETUP
# =============================================================================

st.set_page_config(page_title=cfg.DASHBOARD_TITLE, page_icon="📊", layout="wide")

# Mapping fase (DB, lowercase english) -> label & warna Indonesia
# Warna diambil dari config.SIGNAL_COLORS supaya konsisten dengan sinyal v1
PHASE_LABEL = {
    "accumulation": "Akumulasi",
    "markup": "Mark Up",
    "distribution": "Distribusi",
    "markdown": "Mark Down",
    "unknown": "Unknown",
}
PHASE_COLOR = {
    "accumulation": cfg.SIGNAL_COLORS["Akumulasi"],
    "markup": cfg.SIGNAL_COLORS["Mark Up"],
    "distribution": cfg.SIGNAL_COLORS["Distribusi"],
    "markdown": cfg.SIGNAL_COLORS["Mark Down"],
    "unknown": "#6b7280",
}


def get_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        st.error("DATABASE_URL tidak ditemukan di .env — cek konfigurasi.")
        st.stop()
    return psycopg2.connect(url)


@st.cache_data(ttl=cfg.DASHBOARD_REFRESH_SEC, show_spinner="Memuat data screening...")
def load_screening_latest() -> pd.DataFrame:
    conn = get_conn()
    try:
        df = pd.read_sql("SELECT * FROM v_screening_latest", conn)
    finally:
        conn.close()
    return df


@st.cache_data(ttl=cfg.DASHBOARD_REFRESH_SEC, show_spinner="Memuat histori fase...")
def load_phase_history() -> pd.DataFrame:
    conn = get_conn()
    try:
        df = pd.read_sql(
            """
            SELECT
                ph.stock_code, s.stock_name, s.sector, ph.phase,
                ph.phase_start, ph.phase_end,
                ph.price_at_start, ph.price_at_end, ph.price_change_pct
            FROM phase_history ph
            JOIN stocks s ON s.stock_code = ph.stock_code
            ORDER BY ph.stock_code, ph.phase_start
            """,
            conn,
        )
    finally:
        conn.close()
    df["phase_start"] = pd.to_datetime(df["phase_start"])
    df["phase_end_disp"] = pd.to_datetime(df["phase_end"]).fillna(pd.Timestamp.now())
    return df


def phase_badge(phase: str) -> str:
    label = PHASE_LABEL.get(phase, phase)
    color = PHASE_COLOR.get(phase, "#6b7280")
    return f"<span style='background:{color}22;color:{color};padding:2px 10px;" \
           f"border-radius:10px;font-size:12.5px;font-weight:600'>{label}</span>"


def fmt_rupiah(v: float) -> str:
    sign = "-" if v < 0 else ""
    absv = abs(v)
    if absv >= 1_000_000_000_000:
        return f"{sign}Rp {absv/1e12:.1f} triliun"
    if absv >= 1_000_000_000:
        return f"{sign}Rp {absv/1e9:.0f} miliar"
    if absv >= 1_000_000:
        return f"{sign}Rp {absv/1e6:.0f} juta"
    return f"{sign}Rp {absv:,.0f}"


def fmt_pct(v: float) -> str:
    return f"{v*100:+.1f}%"


# =============================================================================
# HEADER
# =============================================================================

st.title(f"📊 {cfg.DASHBOARD_TITLE}")
st.caption("Data ter-refresh otomatis tiap "
           f"{cfg.DASHBOARD_REFRESH_SEC // 60} menit dari Neon PostgreSQL.")

tab_screening, tab_timeline, tab_keterangan = st.tabs(
    ["🔍 Screening", "📈 Timeline Fase", "📋 Keterangan"]
)

# =============================================================================
# TAB 1 — SCREENING DENGAN FILTER FASE
# =============================================================================

with tab_screening:
    df_screen = load_screening_latest()

    if df_screen.empty:
        st.info("Belum ada data screening. Pastikan ETL pipeline sudah pernah jalan.")
    else:
        latest_date = df_screen["screen_date"].iloc[0]
        st.subheader(f"Hasil screening — {latest_date}")

        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            phase_options = sorted(df_screen["phase"].dropna().unique().tolist())
            selected_phases = st.multiselect(
                "Filter fase", options=phase_options,
                default=phase_options,
                format_func=lambda p: PHASE_LABEL.get(p, p),
            )
        with col2:
            sector_options = sorted(df_screen["sector"].dropna().unique().tolist())
            selected_sectors = st.multiselect("Filter sektor", options=sector_options)
        with col3:
            min_score = st.slider("Skor minimum", 0, 100, 0)

        filtered = df_screen[df_screen["phase"].isin(selected_phases)]
        if selected_sectors:
            filtered = filtered[filtered["sector"].isin(selected_sectors)]
        filtered = filtered[filtered["signal_score"].fillna(0) >= min_score]

        # Ringkasan jumlah saham per fase (dari data yang SUDAH difilter sektor,
        # supaya tetap relevan meski checkbox fase belum semua dicentang)
        counts = df_screen.copy()
        if selected_sectors:
            counts = counts[counts["sector"].isin(selected_sectors)]
        count_by_phase = counts["phase"].value_counts()

        metric_cols = st.columns(len(PHASE_LABEL) - 1)  # exclude 'unknown'
        for i, phase in enumerate(["accumulation", "markup", "distribution", "markdown"]):
            with metric_cols[i]:
                st.metric(PHASE_LABEL[phase], int(count_by_phase.get(phase, 0)))

        st.divider()
        st.caption(f"{len(filtered)} saham cocok filter")

        display_cols = [
            "stock_code", "stock_name", "sector", "close_price",
            "phase", "signal_type", "signal_score", "volume_ratio",
            "ff_net_today",
        ]
        display_cols = [c for c in display_cols if c in filtered.columns]
        show_df = filtered[display_cols].sort_values("signal_score", ascending=False).copy()
        show_df["phase"] = show_df["phase"].map(lambda p: PHASE_LABEL.get(p, p))

        st.dataframe(
            show_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "close_price": st.column_config.NumberColumn("Harga", format="Rp %d"),
                "signal_score": st.column_config.ProgressColumn(
                    "Skor", min_value=0, max_value=100, format="%d"
                ),
                "volume_ratio": st.column_config.NumberColumn("Vol Ratio", format="%.2fx"),
                "ff_net_today": st.column_config.NumberColumn("FF Net (lot)", format="%d"),
            },
        )

# =============================================================================
# TAB 2 — TIMELINE FASE
# =============================================================================

with tab_timeline:
    df_hist = load_phase_history()

    if df_hist.empty:
        st.info("Belum ada data phase_history. Pastikan ETL pipeline sudah pernah jalan.")
    else:
        view = st.radio("Tampilan", ["Semua saham", "Per saham"], horizontal=True)

        color_map = {p: c for p, c in PHASE_COLOR.items()}

        if view == "Semua saham":
            # urutkan saham: kelompokkan berdasarkan fase aktif sekarang
            last_phase = (
                df_hist.sort_values("phase_start")
                .groupby("stock_code")
                .tail(1)
                .set_index("stock_code")["phase"]
            )
            order = last_phase.sort_values().index.tolist()

            fig = px.timeline(
                df_hist,
                x_start="phase_start", x_end="phase_end_disp",
                y="stock_code", color="phase",
                color_discrete_map=color_map,
                category_orders={"stock_code": order},
                hover_data={
                    "phase_start": "|%d %b %Y",
                    "phase_end": True,
                    "price_at_start": ":.0f",
                    "price_at_end": ":.0f",
                    "price_change_pct": ":.2f",
                },
                labels={"phase": "Fase"},
                height=max(400, len(order) * 22),
            )
            fig.update_yaxes(autorange="reversed", title=None)
            fig.update_xaxes(title=None)
            fig.for_each_trace(lambda t: t.update(name=PHASE_LABEL.get(t.name, t.name)))
            st.plotly_chart(fig, use_container_width=True)

        else:
            tickers = sorted(df_hist["stock_code"].unique())
            selected = st.selectbox("Pilih saham", tickers)
            sub = df_hist[df_hist["stock_code"] == selected].sort_values("phase_start")

            stock_name = sub["stock_name"].iloc[0]
            current = sub.iloc[-1]
            st.markdown(
                f"### {selected} — {stock_name}  {phase_badge(current['phase'])}",
                unsafe_allow_html=True,
            )

            fig = px.timeline(
                sub,
                x_start="phase_start", x_end="phase_end_disp",
                y=["" for _ in range(len(sub))],
                color="phase",
                color_discrete_map=color_map,
                hover_data={
                    "phase_start": "|%d %b %Y",
                    "phase_end": True,
                    "price_at_start": ":.0f",
                    "price_at_end": ":.0f",
                    "price_change_pct": ":.2f",
                },
                labels={"phase": "Fase"},
                height=140,
            )
            fig.update_yaxes(visible=False)
            fig.update_xaxes(title=None)
            fig.for_each_trace(lambda t: t.update(name=PHASE_LABEL.get(t.name, t.name)))
            st.plotly_chart(fig, use_container_width=True)

            st.caption("Rincian tiap fase (terbaru di atas):")
            for _, r in sub.sort_values("phase_start", ascending=False).iterrows():
                end_label = (
                    r["phase_end"].strftime("%d %b %Y")
                    if pd.notna(r["phase_end"]) else "berjalan"
                )
                dur = (
                    (pd.Timestamp(r["phase_end"]) - r["phase_start"]).days
                    if pd.notna(r["phase_end"])
                    else (pd.Timestamp.now() - r["phase_start"]).days
                )
                pct = r["price_change_pct"]
                pct_str = f"{pct:+.2f}%" if pd.notna(pct) else "—"
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
                    c1.markdown(phase_badge(r["phase"]), unsafe_allow_html=True)
                    c2.write(f"{r['phase_start'].strftime('%d %b %Y')} – {end_label} ({dur} hari)")
                    c3.write(f"Rp{r['price_at_start']:,.0f} → "
                             f"{'Rp' + format(r['price_at_end'], ',.0f') if pd.notna(r['price_at_end']) else '—'}")
                    c4.write(pct_str)

# =============================================================================
# TAB 3 — KETERANGAN (kriteria & parameter sinyal, otomatis dari config.py)
# =============================================================================

with tab_keterangan:
    st.subheader("Kriteria sinyal ADMD")
    st.caption(
        "Nilai di bawah diambil langsung dari `config.py` — kalau kamu ubah "
        "parameter di sana, tab ini otomatis ikut berubah."
    )

    c1, c2 = st.columns(2)

    with c1:
        with st.container(border=True):
            st.markdown(phase_badge("accumulation") + " **Akumulasi**", unsafe_allow_html=True)
            st.markdown(f"""
- Net **buy** asing minimal **{fmt_rupiah(cfg.ACCUM_NET_BUY_MIN)}**
  dalam **{cfg.ACCUM_WINDOW_DAYS} hari**
- Harga naik pelan: maksimal **{fmt_pct(cfg.ACCUM_PRICE_CHANGE_MAX)}**,
  minimal **{fmt_pct(cfg.ACCUM_PRICE_CHANGE_MIN)}**
""")

        with st.container(border=True):
            st.markdown(phase_badge("markup") + " **Mark Up**", unsafe_allow_html=True)
            st.markdown(f"""
- Volume ≥ **{cfg.MARKUP_VOLUME_RATIO_MIN}x** rata-rata
  **{cfg.MARKUP_VOLUME_AVG_WINDOW} hari**
- Harga naik minimal **{fmt_pct(cfg.MARKUP_PRICE_BREAKOUT)}** dalam 1 hari,
  atau breakout dari high **{cfg.MARKUP_BREAKOUT_WINDOW} hari** terakhir
""")

    with c2:
        with st.container(border=True):
            st.markdown(phase_badge("distribution") + " **Distribusi**", unsafe_allow_html=True)
            st.markdown(f"""
- Net **sell** asing minimal **{fmt_rupiah(cfg.DIST_NET_SELL_MIN)}**
  dalam **{cfg.DIST_WINDOW_DAYS} hari**
- Harga stagnan/turun: maksimal **{fmt_pct(cfg.DIST_PRICE_CHANGE_MAX)}**,
  minimal **{fmt_pct(cfg.DIST_PRICE_CHANGE_MIN)}**
""")

        with st.container(border=True):
            st.markdown(phase_badge("markdown") + " **Mark Down**", unsafe_allow_html=True)
            st.markdown(f"""
- Harga turun minimal **{fmt_pct(cfg.MARKDOWN_PRICE_DROP_MIN)}**
  dalam **{cfg.MARKDOWN_PRICE_WINDOW} hari**
- Net sell asing minimal **{fmt_rupiah(cfg.MARKDOWN_NET_SELL_MIN)}**
- Volume konfirmasi ≥ **{cfg.MARKDOWN_VOLUME_RATIO_MIN}x** rata-rata
""")

    st.warning(
        "⚠️ Kalau data foreign flow hari itu tidak tersedia (belum di-upload CSV "
        "IDX), sinyal **Akumulasi** & **Distribusi** tetap jalan hanya dengan "
        "kriteria harga + volume, dan `strength` di-cap maksimal **70**.",
        icon="⚠️",
    )

    st.divider()
    st.subheader("Arti kolom")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**`screening_results`**")
        st.markdown("""
| Kolom | Arti |
|---|---|
| `volume_ratio` | Volume hari ini vs rata-rata 20 hari. `>1.5` = volume tinggi |
| `ff_net_3d/5d/20d` | Kumulatif net foreign flow (lot), jangka pendek → bulanan |
| `signal_score` | Skor gabungan teknikal + foreign flow, 0–100 |
| `phase` | Fase Wyckoff saat ini |
""")
    with col_b:
        st.markdown("**`phase_history`**")
        st.markdown("""
| Kolom | Arti |
|---|---|
| `phase_end = NULL` | Saham masih berada di fase tersebut |
| `duration_days` | Durasi fase (hari), auto-generated dari DB |
| `price_change_pct` | Perubahan harga selama fase, auto-generated |
| `ff_net_cumulative` | Total net foreign flow selama fase berlangsung |
""")

    st.divider()
    st.subheader("Strategi per fase")
    st.info(
        "ℹ️ Ini kerangka umum berdasarkan metode **Wyckoff** (bukan saran keuangan "
        "personal, bukan jaminan hasil). Sinyal dari screener ini murni membaca "
        "pola harga & foreign flow historis — tidak memperhitungkan kondisi "
        "fundamental, berita, atau profil risiko masing-masing orang. Selalu "
        "riset mandiri (DYOR) dan pertimbangkan konsultasi dengan penasihat "
        "keuangan berlisensi sebelum mengambil keputusan.",
        icon="ℹ️",
    )

    s1, s2 = st.columns(2)
    with s1:
        with st.container(border=True):
            st.markdown(phase_badge("accumulation") + " **Akumulasi**", unsafe_allow_html=True)
            st.markdown("""
**Konteks:** dugaan institusi/asing mulai mengumpulkan barang, harga cenderung sideways/naik pelan.

- Mulai **cicil beli bertahap (DCA)**, hindari all-in — fase ini masih rawan gagal
  jadi reversal beneran ("false accumulation")
- Tunggu `signal_score` cukup tinggi & `ff_net_3d`/`ff_net_5d` konsisten positif
  beberapa hari berturut, bukan cuma 1 hari
- Fase yang baru mulai (`duration_days` kecil, 0–2 hari) → masih rawan noise, lebih aman tunggu konfirmasi dulu
""")

        with st.container(border=True):
            st.markdown(phase_badge("markup") + " **Mark Up**", unsafe_allow_html=True)
            st.markdown("""
**Konteks:** breakout terkonfirmasi, momentum naik sudah jalan.

- Ini fase paling umum buat **menambah posisi (add) atau hold** kalau sudah
  cicil beli di fase akumulasi
- Entry baru di fase ini risikonya lebih tinggi (sudah naik duluan) —
  pertimbangkan posisi lebih kecil / tunggu pullback
- Pasang trailing stop, karena mark up bisa berbalik cepat jadi distribusi
""")

    with s2:
        with st.container(border=True):
            st.markdown(phase_badge("distribution") + " **Distribusi**", unsafe_allow_html=True)
            st.markdown("""
**Konteks:** dugaan institusi/asing mulai lepas barang ke ritel, harga stagnan/mulai lemah.

- Pertimbangkan **kurangi porsi bertahap (scale out / take profit sebagian)**,
  bukan tunggu sampai konfirmasi markdown penuh
- Hindari nambah posisi baru di fase ini
- Perhatikan `ff_net_cumulative` — makin negatif & makin lama fase ini
  berlangsung, makin kuat sinyal keluarnya asing
""")

        with st.container(border=True):
            st.markdown(phase_badge("markdown") + " **Mark Down**", unsafe_allow_html=True)
            st.markdown("""
**Konteks:** downtrend terkonfirmasi, tekanan jual dominan.

- **Hindari entry baru** di fase ini
- Kalau masih pegang posisi, ini biasanya sudah terlambat untuk cut loss "murah" —
  pertimbangkan sesuai rencana risk management masing-masing
- Fase ini sering pendek (lihat rata-rata `duration_days` di tab Timeline) —
  pantau terus, biasanya diikuti akumulasi baru yang jadi titik re-entry berikutnya
""")

    st.divider()
    st.caption(
        "Universe default: " + ("LQ45" if cfg.DEFAULT_UNIVERSE == cfg.LQ45 else "custom")
        + f" ({len(cfg.DEFAULT_UNIVERSE)} saham) · "
        f"Scheduler ETL: setiap hari bursa jam {cfg.SCHEDULER_HOUR_WIB}:00 WIB"
    )
