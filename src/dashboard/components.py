# =============================================================================
# src/dashboard/components.py — Komponen UI reusable untuk Streamlit
# =============================================================================

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import config as cfg


def render_ohlcv_chart(ticker: str, df: pd.DataFrame) -> None:
    """
    Chart candlestick + volume bar dalam satu figure.
    Kolom yang dibutuhkan: Open, High, Low, Close, Volume
    """
    if df.empty or len(df) < 3:
        st.warning("Data tidak cukup untuk chart.")
        return

    df = df.tail(60).copy()  # maksimal 60 hari terakhir

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.03,
    )

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=ticker,
            increasing_line_color="#22c55e",
            decreasing_line_color="#ef4444",
        ),
        row=1, col=1,
    )

    # Volume bar — hijau jika naik, merah jika turun
    colors = [
        "#22c55e" if c >= o else "#ef4444"
        for c, o in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            name="Volume",
            marker_color=colors,
            opacity=0.7,
        ),
        row=2, col=1,
    )

    # Garis vol_avg20 jika ada
    if "vol_avg20" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["vol_avg20"],
                name="Vol MA20",
                line=dict(color="#f97316", width=1.5, dash="dot"),
            ),
            row=2, col=1,
        )

    fig.update_layout(
        title=f"{ticker} — Harga & Volume",
        height=460,
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f1f5f9")
    fig.update_yaxes(showgrid=True, gridcolor="#f1f5f9")

    st.plotly_chart(fig, width="stretch")


def render_foreign_flow_chart(ticker: str, foreign_df: pd.DataFrame) -> None:
    """
    Bar chart net buy/sell asing harian untuk satu ticker.
    Kolom yang dibutuhkan: ticker, date, net_buy_sell
    """
    data = foreign_df[foreign_df["ticker"] == ticker].copy()
    if data.empty:
        st.warning(f"Tidak ada data foreign flow untuk {ticker}.")
        return

    data = data.sort_values("date")
    colors = ["#22c55e" if v >= 0 else "#ef4444" for v in data["net_buy_sell"]]

    fig = go.Figure(
        go.Bar(
            x=data["date"],
            y=data["net_buy_sell"] / 1e9,
            marker_color=colors,
            name="Net Buy/Sell (Rp M)",
            text=[f"Rp {v/1e9:+.1f}M" for v in data["net_buy_sell"]],
            textposition="outside",
        )
    )

    fig.add_hline(y=0, line_width=1, line_color="#64748b")

    fig.update_layout(
        title=f"{ticker} — Net Buy/Sell Asing (Rp Miliar)",
        yaxis_title="Rp Miliar",
        height=280,
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#f1f5f9")

    st.plotly_chart(fig, width="stretch")


def render_signal_badge(signal: str) -> str:
    """Return HTML badge string untuk sinyal."""
    colors = {
        "Akumulasi" : "#22c55e",
        "Distribusi": "#f97316",
        "Mark Up"   : "#3b82f6",
        "Mark Down" : "#ef4444",
    }
    color = colors.get(signal, "#64748b")
    return (
        f'<span style="background:{color};color:white;'
        f'padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600">'
        f'{signal}</span>'
    )


def render_strength_bar(strength: float) -> None:
    """Progress bar dengan warna berdasarkan strength."""
    color = (
        "#22c55e" if strength >= 70
        else "#f97316" if strength >= 40
        else "#ef4444"
    )
    st.markdown(
        f'<div style="background:#f1f5f9;border-radius:6px;height:12px;overflow:hidden">'
        f'<div style="background:{color};width:{strength}%;height:100%"></div></div>'
        f'<p style="font-size:12px;color:#64748b;margin:2px 0">{strength:.1f}/100</p>',
        unsafe_allow_html=True,
    )


def render_metric_row(label: str, value: str, delta: str = None) -> None:
    """Metric card kecil dalam baris."""
    delta_html = ""
    if delta:
        color = "#22c55e" if delta.startswith("+") else "#ef4444"
        delta_html = f'<span style="color:{color};font-size:13px">{delta}</span>'
    st.markdown(
        f'<div style="background:#f8fafc;border:1px solid #e2e8f0;'
        f'border-radius:8px;padding:10px 14px;margin:4px 0">'
        f'<p style="font-size:12px;color:#64748b;margin:0">{label}</p>'
        f'<p style="font-size:20px;font-weight:700;margin:0">{value} {delta_html}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )
