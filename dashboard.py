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
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

import config as cfg
from src.analysis.trend_indicators import (
    compute_indicators,
    find_crossovers,
    validate_leading_indicator,
    EVENT_MA_GOLDEN,
    EVENT_MA_DEATH,
    EVENT_MACD_BULL,
    EVENT_MACD_BEAR,
)

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

# Sinyal trend (MA cross & MACD cross) — kolom TERPISAH dari fase ADMD,
# jadi satu ticker bisa punya fase ADMD + sinyal trend sekaligus tanpa
# saling menggusur (lihat screener.py: run_all()).
TREND_LABEL = {
    "MA_Golden_Cross"   : "Golden Cross (MA5×MA20)",
    "MA_Death_Cross"    : "Death Cross (MA5×MA20)",
    "MACD_Bullish_Cross": "MACD Bullish",
    "MACD_Bearish_Cross": "MACD Bearish",
}
TREND_COLOR = {
    "MA_Golden_Cross"   : "#22c55e",
    "MA_Death_Cross"    : "#ef4444",
    "MACD_Bullish_Cross": "#3b82f6",
    "MACD_Bearish_Cross": "#f97316",
}

# Minimal jumlah hari histori supaya MACD (EMA26 + signal EMA9) cukup "matang"
# sebelum dianggap layak ditampilkan di chart perbandingan.
MA_SLOW_WINDOW_MIN = 35


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


@st.cache_data(ttl=cfg.DASHBOARD_REFRESH_SEC, show_spinner="Memuat histori harga...")
def load_ohlcv_history(stock_code: str) -> pd.Series:
    """Histori close price satu saham, index = tanggal. Untuk hitung MA/MACD penuh."""
    conn = get_conn()
    try:
        df = pd.read_sql(
            "SELECT trade_date, close_price FROM daily_ohlcv "
            "WHERE stock_code = %s ORDER BY trade_date",
            conn, params=(stock_code,),
        )
    finally:
        conn.close()
    if df.empty:
        return pd.Series(dtype=float)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df.set_index("trade_date")["close_price"]


@st.cache_data(ttl=cfg.DASHBOARD_REFRESH_SEC, show_spinner="Memuat histori harga semua saham...")
def load_ohlcv_all(tickers: tuple) -> dict:
    """Sama seperti load_ohlcv_history tapi untuk banyak ticker sekaligus (satu query)."""
    conn = get_conn()
    try:
        df = pd.read_sql(
            "SELECT stock_code, trade_date, close_price FROM daily_ohlcv "
            "WHERE stock_code = ANY(%s) ORDER BY stock_code, trade_date",
            conn, params=(list(tickers),),
        )
    finally:
        conn.close()
    if df.empty:
        return {}
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    return {
        t: g.set_index("trade_date")["close_price"]
        for t, g in df.groupby("stock_code")
    }


def phase_badge(phase: str) -> str:
    label = PHASE_LABEL.get(phase, phase)
    color = PHASE_COLOR.get(phase, "#6b7280")
    return f"<span style='background:{color}22;color:{color};padding:2px 10px;" \
           f"border-radius:10px;font-size:12.5px;font-weight:600'>{label}</span>"


def trend_badge(signal) -> str:
    if signal is None or (isinstance(signal, float) and pd.isna(signal)):
        return "<span style='color:#9ca3af;font-size:12.5px'>—</span>"
    label = TREND_LABEL.get(signal, signal)
    color = TREND_COLOR.get(signal, "#6b7280")
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

tab_screening, tab_trend, tab_compare, tab_timeline, tab_keterangan = st.tabs(
    ["🔍 Screening", "📊 Trend MA/MACD", "🔬 Perbandingan Metode", "📈 Timeline Fase", "📋 Keterangan"]
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

        only_trend = st.checkbox(
            "Hanya tampilkan yang ada sinyal trend (MA/MACD cross) hari ini",
            value=False,
        )

        filtered = df_screen[df_screen["phase"].isin(selected_phases)]
        if selected_sectors:
            filtered = filtered[filtered["sector"].isin(selected_sectors)]
        filtered = filtered[filtered["signal_score"].fillna(0) >= min_score]
        if only_trend and "ma_cross_signal" in filtered.columns and "macd_cross_signal" in filtered.columns:
            filtered = filtered[
                filtered["ma_cross_signal"].notna() | filtered["macd_cross_signal"].notna()
            ]

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

        # Ringkasan sinyal trend hari ini (independen dari filter fase di atas)
        if "ma_cross_signal" in counts.columns and "macd_cross_signal" in counts.columns:
            trend_counts = pd.concat(
                [counts["ma_cross_signal"], counts["macd_cross_signal"]]
            ).dropna().value_counts()
            if not trend_counts.empty:
                st.caption(
                    "Sinyal trend hari ini: "
                    + " · ".join(
                        f"{TREND_LABEL.get(sig, sig)}: **{n}**"
                        for sig, n in trend_counts.items()
                    )
                )

        st.divider()
        st.caption(f"{len(filtered)} saham cocok filter")

        display_cols = [
            "stock_code", "stock_name", "sector", "close_price",
            "phase", "signal_type", "signal_score", "volume_ratio",
            "ff_net_today", "ma_cross_signal", "macd_cross_signal",
        ]
        display_cols = [c for c in display_cols if c in filtered.columns]
        show_df = filtered[display_cols].sort_values("signal_score", ascending=False).copy()
        show_df["phase"] = show_df["phase"].map(lambda p: PHASE_LABEL.get(p, p))
        if "ma_cross_signal" in show_df.columns:
            show_df["ma_cross_signal"] = show_df["ma_cross_signal"].map(
                lambda s: TREND_LABEL.get(s, s) if pd.notna(s) else "—"
            )
        if "macd_cross_signal" in show_df.columns:
            show_df["macd_cross_signal"] = show_df["macd_cross_signal"].map(
                lambda s: TREND_LABEL.get(s, s) if pd.notna(s) else "—"
            )

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
                "ma_cross_signal": st.column_config.TextColumn("MA Cross"),
                "macd_cross_signal": st.column_config.TextColumn("MACD Cross"),
            },
        )

# =============================================================================
# TAB — TREND MA/MACD (golden/death cross & MACD bullish/bearish)
# =============================================================================

with tab_trend:
    df_screen_trend = load_screening_latest()

    if df_screen_trend.empty:
        st.info("Belum ada data screening. Pastikan ETL pipeline sudah pernah jalan.")
    elif "ma_cross_signal" not in df_screen_trend.columns or "macd_cross_signal" not in df_screen_trend.columns:
        st.warning(
            "Kolom `ma_cross_signal` / `macd_cross_signal` belum ada di "
            "`v_screening_latest`. Pastikan view sudah di-update (lihat "
            "migration `ALTER TABLE screening_results ...` dan "
            "`CREATE OR REPLACE VIEW v_screening_latest ...`)."
        )
    else:
        latest_date = df_screen_trend["screen_date"].iloc[0]
        st.subheader(f"Sinyal trend — {latest_date}")
        st.caption(
            "Sinyal ini independen dari fase ADMD — satu saham bisa berada di "
            "fase Akumulasi tapi sudah menunjukkan MACD mulai bearish, misalnya. "
            "Keduanya ditampilkan apa adanya, tidak saling menggantikan."
        )

        trend_hits = df_screen_trend[
            df_screen_trend["ma_cross_signal"].notna()
            | df_screen_trend["macd_cross_signal"].notna()
        ].copy()

        if trend_hits.empty:
            st.info("Tidak ada sinyal MA cross atau MACD cross hari ini.")
        else:
            col_ma, col_macd = st.columns(2)

            with col_ma:
                st.markdown("#### MA Cross (MA5 × MA20)")
                ma_hits = trend_hits[trend_hits["ma_cross_signal"].notna()]
                if ma_hits.empty:
                    st.caption("Tidak ada.")
                for _, r in ma_hits.sort_values("ma_cross_signal").iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 2])
                        c1.markdown(
                            f"**{r['stock_code']}** — {r['stock_name']}<br>"
                            + trend_badge(r["ma_cross_signal"]),
                            unsafe_allow_html=True,
                        )
                        c2.markdown(
                            f"Rp{r['close_price']:,.0f}<br>"
                            f"Fase: {PHASE_LABEL.get(r['phase'], r['phase'])}",
                            unsafe_allow_html=True,
                        )

            with col_macd:
                st.markdown("#### MACD Cross")
                macd_hits = trend_hits[trend_hits["macd_cross_signal"].notna()]
                if macd_hits.empty:
                    st.caption("Tidak ada.")
                for _, r in macd_hits.sort_values("macd_cross_signal").iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 2])
                        c1.markdown(
                            f"**{r['stock_code']}** — {r['stock_name']}<br>"
                            + trend_badge(r["macd_cross_signal"]),
                            unsafe_allow_html=True,
                        )
                        c2.markdown(
                            f"Rp{r['close_price']:,.0f}<br>"
                            f"Fase: {PHASE_LABEL.get(r['phase'], r['phase'])}",
                            unsafe_allow_html=True,
                        )

            st.divider()
            st.caption("Ticker dengan sinyal ADMD + trend bersamaan (konfirmasi silang):")
            overlap = trend_hits[trend_hits["signal_type"].notna()]
            if overlap.empty:
                st.caption("Tidak ada saat ini.")
            else:
                overlap_cols = [
                    "stock_code", "stock_name", "phase", "signal_type",
                    "ma_cross_signal", "macd_cross_signal",
                ]
                overlap_show = overlap[overlap_cols].copy()
                overlap_show["phase"] = overlap_show["phase"].map(lambda p: PHASE_LABEL.get(p, p))
                overlap_show["ma_cross_signal"] = overlap_show["ma_cross_signal"].map(
                    lambda s: TREND_LABEL.get(s, s) if pd.notna(s) else "—"
                )
                overlap_show["macd_cross_signal"] = overlap_show["macd_cross_signal"].map(
                    lambda s: TREND_LABEL.get(s, s) if pd.notna(s) else "—"
                )
                st.dataframe(overlap_show, use_container_width=True, hide_index=True)

# =============================================================================
# TAB — PERBANDINGAN METODE (Wyckoff vs MA/MACD cross, independen)
# =============================================================================

with tab_compare:
    st.caption(
        "Membandingkan fase Wyckoff (ADMD) yang sudah berjalan dengan metode "
        "teknikal yang independen: MA5×MA20 cross dan MACD cross. Tujuannya "
        "melihat apakah golden cross / MACD bullish cenderung muncul **sebelum** "
        "fase akumulasi/mark up tercatat oleh metode Wyckoff — atau sebaliknya "
        "untuk distribusi/markdown."
    )

    compare_mode = st.radio(
        "Mode", ["📈 Chart per saham", "📋 Validasi leading indicator"],
        horizontal=True, key="compare_mode",
    )

    # -------------------------------------------------------------------
    # MODE 1 — Chart per saham: harga + MA/MACD + shading fase Wyckoff
    # -------------------------------------------------------------------
    if compare_mode == "📈 Chart per saham":
        tickers_all = sorted(cfg.DEFAULT_UNIVERSE)
        sel_ticker = st.selectbox("Pilih saham", tickers_all, key="cmp_ticker")

        close_hist = load_ohlcv_history(sel_ticker)

        if close_hist.empty or len(close_hist) < MA_SLOW_WINDOW_MIN:
            st.warning(
                f"Histori harga {sel_ticker} belum cukup panjang untuk hitung "
                f"MA20/MACD (butuh minimal ~35 hari data)."
            )
        else:
            ind = compute_indicators(close_hist)
            events = find_crossovers(ind)

            df_hist_all = load_phase_history()
            phases_sel = df_hist_all[df_hist_all["stock_code"] == sel_ticker].sort_values("phase_start")

            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35],
                vertical_spacing=0.04,
                subplot_titles=(
                    f"{sel_ticker} — Harga + MA5/MA20 (latar = fase Wyckoff)",
                    "MACD (12, 26, 9)",
                ),
            )

            # Shading fase Wyckoff sebagai latar belakang chart harga
            for _, r in phases_sel.iterrows():
                end = r["phase_end"] if pd.notna(r["phase_end"]) else ind.index.max()
                fig.add_vrect(
                    x0=r["phase_start"], x1=end,
                    fillcolor=PHASE_COLOR.get(r["phase"], "#6b7280"),
                    opacity=0.12, line_width=0, row=1, col=1,
                )

            fig.add_trace(go.Scatter(
                x=ind.index, y=ind["close"], name="Close",
                line=dict(color="#111827", width=1.3),
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=ind.index, y=ind["ma_fast"], name="MA5",
                line=dict(color="#3b82f6", width=1),
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=ind.index, y=ind["ma_slow"], name="MA20",
                line=dict(color="#f97316", width=1),
            ), row=1, col=1)

            golden_ev = events[events["type"] == EVENT_MA_GOLDEN]
            death_ev  = events[events["type"] == EVENT_MA_DEATH]
            if not golden_ev.empty:
                fig.add_trace(go.Scatter(
                    x=golden_ev["date"], y=ind.loc[golden_ev["date"], "ma_fast"],
                    mode="markers", name="Golden Cross",
                    marker=dict(symbol="star", size=12, color="#22c55e",
                                line=dict(width=1, color="#14532d")),
                ), row=1, col=1)
            if not death_ev.empty:
                fig.add_trace(go.Scatter(
                    x=death_ev["date"], y=ind.loc[death_ev["date"], "ma_fast"],
                    mode="markers", name="Death Cross",
                    marker=dict(symbol="star", size=12, color="#ef4444",
                                line=dict(width=1, color="#7f1d1d")),
                ), row=1, col=1)

            fig.add_trace(go.Bar(
                x=ind.index, y=ind["histogram"], name="Histogram",
                marker_color=["#22c55e" if v >= 0 else "#ef4444" for v in ind["histogram"].fillna(0)],
            ), row=2, col=1)
            fig.add_trace(go.Scatter(
                x=ind.index, y=ind["macd_line"], name="MACD line",
                line=dict(color="#3b82f6", width=1),
            ), row=2, col=1)
            fig.add_trace(go.Scatter(
                x=ind.index, y=ind["signal_line"], name="Signal line",
                line=dict(color="#f97316", width=1),
            ), row=2, col=1)

            fig.update_layout(
                height=680,
                legend=dict(orientation="h", y=1.06),
                margin=dict(t=70, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

            bullish_n = (events["type"] == EVENT_MACD_BULL).sum()
            bearish_n = (events["type"] == EVENT_MACD_BEAR).sum()
            st.caption(
                f"Sepanjang histori tersedia: {len(golden_ev)} golden cross · "
                f"{len(death_ev)} death cross · {bullish_n} MACD bullish · "
                f"{bearish_n} MACD bearish."
            )

    # -------------------------------------------------------------------
    # MODE 2 — Validasi leading indicator (semua saham, semua transisi fase)
    # -------------------------------------------------------------------
    else:
        lookback_days = st.slider(
            "Jendela pengecekan 'sebelum transisi' (hari)", 1, 20, 5, key="cmp_lookback"
        )
        tickers_all = tuple(sorted(cfg.DEFAULT_UNIVERSE))

        with st.spinner("Menghitung indikator untuk semua saham..."):
            ohlcv_by_ticker = load_ohlcv_all(tickers_all)
            df_hist_all = load_phase_history()
            result = validate_leading_indicator(df_hist_all, ohlcv_by_ticker, lookback_days)

        if result.empty:
            st.info("Belum cukup data phase_history / OHLCV untuk validasi.")
        else:
            summary = (
                result.groupby("phase")["leading_signal_found"]
                .agg(["sum", "count"])
                .rename(columns={"sum": "didahului_sinyal", "count": "total_transisi"})
            )
            summary["persentase"] = (
                summary["didahului_sinyal"] / summary["total_transisi"] * 100
            ).round(1)

            st.subheader(f"Ringkasan — sinyal trend dalam {lookback_days} hari sebelum transisi fase")
            metric_cols = st.columns(4)
            for i, phase in enumerate(["accumulation", "markup", "distribution", "markdown"]):
                with metric_cols[i]:
                    if phase in summary.index:
                        row = summary.loc[phase]
                        st.metric(
                            PHASE_LABEL[phase],
                            f"{row['persentase']:.0f}%",
                            help=(
                                f"{int(row['didahului_sinyal'])} dari "
                                f"{int(row['total_transisi'])} transisi fase "
                                f"{PHASE_LABEL[phase]} didahului golden/death cross "
                                f"atau MACD cross yang relevan."
                            ),
                        )
                    else:
                        st.metric(PHASE_LABEL[phase], "—")

            st.divider()
            st.caption("Rincian tiap transisi fase:")
            show = result.copy()
            show["phase"] = show["phase"].map(lambda p: PHASE_LABEL.get(p, p))
            show["phase_start"] = pd.to_datetime(show["phase_start"]).dt.strftime("%d %b %Y")
            show["leading_signal_found"] = show["leading_signal_found"].map({True: "✅ Ya", False: "❌ Tidak"})
            show["signal_type"] = show["signal_type"].map(
                lambda s: TREND_LABEL.get(s, s) if pd.notna(s) else "—"
            )
            st.dataframe(
                show[["stock_code", "phase", "phase_start", "leading_signal_found", "signal_type", "days_before"]],
                use_container_width=True, hide_index=True,
                column_config={
                    "stock_code": "Saham",
                    "phase": "Fase baru",
                    "phase_start": "Mulai",
                    "leading_signal_found": "Didahului sinyal?",
                    "signal_type": "Jenis sinyal",
                    "days_before": st.column_config.NumberColumn("Berapa hari sebelumnya"),
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
