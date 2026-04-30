"""
Yield Curve Dashboard — Streamlit
==================================
Run:
    pip install streamlit pandas plotly
    streamlit run yield_curve_dashboard.py

Expects a CSV/Excel with columns:
    Date, USGG2YR Index, USGG10YR Index, USGG30YR Index
    (and optionally USGG3M Index, USGG5YR Index, USGG12M Index, USGG20YR Index)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from pathlib import Path

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="US Yield Curve Dashboard",
    page_icon="📈",
    layout="wide",
)

# ── Regime classification (12-week / ~3-month lookback) ──────────────────────
REGIME_COLORS = {
    "Bull Steepener":  "#4ade80",
    "Bear Steepener":  "#f87171",
    "Steepener Twist": "#facc15",
    "Bull Flattener":  "#60a5fa",
    "Bear Flattener":  "#fb923c",
    "Flattener Twist": "#c084fc",
    "Unchanged":       "#9ca3af",
}

def classify_regime(curve, curve_lb, y_short, y_short_lb, y_long, y_long_lb, eps=0.01):
    steep = curve > curve_lb + eps
    flat  = curve < curve_lb - eps
    s_up  = y_short > y_short_lb + eps
    l_up  = y_long  > y_long_lb  + eps
    s_dn  = y_short < y_short_lb - eps
    l_dn  = y_long  < y_long_lb  - eps

    if steep and s_dn and l_dn: return "Bull Steepener"
    if steep and s_up and l_up: return "Bear Steepener"
    if steep and s_dn and l_up: return "Steepener Twist"
    if flat  and s_dn and l_dn: return "Bull Flattener"
    if flat  and s_up and l_up: return "Bear Flattener"
    if flat  and s_up and l_dn: return "Flattener Twist"
    return "Unchanged"

def add_regimes(df, spread_col, short_col, long_col, lookback=60):
    """Add a regime column for a given spread."""
    curve    = df[long_col]  - df[short_col]
    curve_lb = curve.shift(lookback)
    s_lb     = df[short_col].shift(lookback)
    l_lb     = df[long_col].shift(lookback)

    regimes = []
    for i in range(len(df)):
        if pd.isna(curve_lb.iloc[i]):
            regimes.append("Unchanged")
        else:
            regimes.append(classify_regime(
                curve.iloc[i], curve_lb.iloc[i],
                df[short_col].iloc[i], s_lb.iloc[i],
                df[long_col].iloc[i],  l_lb.iloc[i],
            ))
    return regimes

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data
def load_data(file) -> pd.DataFrame:
    name = file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)

    df.columns = df.columns.str.strip()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    # Rename Bloomberg tickers to short names
    rename = {
        "USGG2YR Index":  "2Y",
        "USGG10YR Index": "10Y",
        "USGG30YR Index": "30Y",
        "USGG3M Index":   "3M",
        "USGG5YR Index":  "5Y",
        "USGG12M Index":  "12M",
        "USGG20YR Index": "20Y",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    return df

# ── Spread chart builder ──────────────────────────────────────────────────────
def spread_chart(df, short, long, title, lookback=60):
    if short not in df.columns or long not in df.columns:
        st.warning(f"Missing columns: {short} or {long}")
        return

    spread = (df[long] - df[short]) * 100  # in bps
    regimes = add_regimes(df, f"{short}{long}", short, long, lookback)

    fig = go.Figure()

    # One bar trace per regime so legend works
    for regime, color in REGIME_COLORS.items():
        mask = [r == regime for r in regimes]
        if not any(mask):
            continue
        fig.add_trace(go.Bar(
            x=df["Date"][mask],
            y=spread[mask],
            name=regime,
            marker_color=color,
            showlegend=True,
        ))

    # Zero line
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(150,150,150,0.5)", line_width=1)

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        barmode="overlay",
        bargap=0.05,
        height=300,
        margin=dict(l=50, r=20, t=40, b=40),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0, font=dict(size=11),
        ),
        yaxis=dict(title="bp", ticksuffix=" bp"),
        xaxis=dict(showgrid=False),
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Full yield curve snapshot ─────────────────────────────────────────────────
def yield_curve_snapshot(df, tenors_available):
    order = ["3M", "12M", "2Y", "5Y", "10Y", "20Y", "30Y"]
    cols  = [c for c in order if c in tenors_available]
    if len(cols) < 2:
        return

    latest = df[["Date"] + cols].dropna().iloc[-1]
    prev   = df[["Date"] + cols].dropna().iloc[-2] if len(df) > 1 else latest
    wk_ago = df[["Date"] + cols].dropna().iloc[-6] if len(df) > 5 else latest

    x_labels = cols
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x_labels, y=[latest[c] for c in cols],
                             mode="lines+markers", name=str(latest["Date"].date()),
                             line=dict(color="#378ADD", width=2), marker=dict(size=7)))
    fig.add_trace(go.Scatter(x=x_labels, y=[wk_ago[c] for c in cols],
                             mode="lines+markers", name=str(wk_ago["Date"].date()) + " (1wk ago)",
                             line=dict(color="#9ca3af", width=1, dash="dash"), marker=dict(size=5)))
    fig.update_layout(
        height=280,
        margin=dict(l=50, r=20, t=30, b=40),
        yaxis=dict(title="Yield (%)", tickformat=".2f"),
        xaxis=dict(title="Tenor"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=11)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Main app ──────────────────────────────────────────────────────────────────
st.title("📈 US Treasury Yield Curve Dashboard")

uploaded = st.file_uploader("Upload your Bloomberg yield data (CSV or Excel)", type=["csv", "xlsx", "xls"])

if uploaded is None:
    st.info("Upload your file to get started. Expected columns: Date, USGG2YR Index, USGG10YR Index, USGG30YR Index (and optionally 3M, 5Y, 12M, 20Y).")
    st.stop()

df = load_data(uploaded)
tenors = [c for c in ["3M","12M","2Y","5Y","10Y","20Y","30Y"] if c in df.columns]

# ── Sidebar controls ──────────────────────────────────────────────────────────
st.sidebar.header("Settings")
period = st.sidebar.selectbox("Period", ["1Y", "2Y", "5Y", "10Y", "All"], index=2)
lookback_weeks = st.sidebar.slider("Regime lookback (weeks)", 4, 26, 12)
lookback = lookback_weeks * 5  # trading days approx

period_map = {"1Y": 252, "2Y": 504, "5Y": 1260, "10Y": 2520, "All": len(df)}
n = period_map[period]
df_view = df.iloc[-n:].reset_index(drop=True)

# ── Metric row ────────────────────────────────────────────────────────────────
latest = df_view[["Date"] + tenors].dropna().iloc[-1]
prev   = df_view[["Date"] + tenors].dropna().iloc[-2]

st.subheader(f"Latest: {latest['Date'].strftime('%b %d, %Y')}")
cols_metrics = st.columns(len(tenors) + 2)
for i, t in enumerate(tenors):
    chg = latest[t] - prev[t]
    cols_metrics[i].metric(label=t, value=f"{latest[t]:.2f}%",
                           delta=f"{chg:+.2f}%", delta_color="inverse")

# Key spreads
if "2Y" in tenors and "10Y" in tenors:
    s2s10 = (latest["10Y"] - latest["2Y"]) * 100
    p2s10 = (prev["10Y"]   - prev["2Y"])   * 100
    cols_metrics[-2].metric("2s10s", f"{s2s10:+.0f} bp", f"{s2s10-p2s10:+.1f} bp")

if "10Y" in tenors and "30Y" in tenors:
    s10s30 = (latest["30Y"] - latest["10Y"]) * 100
    p10s30 = (prev["30Y"]   - prev["10Y"])   * 100
    cols_metrics[-1].metric("10s30s", f"{s10s30:+.0f} bp", f"{s10s30-p10s30:+.1f} bp")

st.divider()

# ── Yield curve snapshot ──────────────────────────────────────────────────────
st.subheader("Yield curve snapshot")
yield_curve_snapshot(df_view, tenors)

st.divider()

# ── Spread charts ─────────────────────────────────────────────────────────────
spreads_to_plot = []
if "2Y"  in tenors and "10Y" in tenors: spreads_to_plot.append(("2Y",  "10Y", "2s10s spread (bp)"))
if "10Y" in tenors and "30Y" in tenors: spreads_to_plot.append(("10Y", "30Y", "10s30s spread (bp)"))
if "3M"  in tenors and "10Y" in tenors: spreads_to_plot.append(("3M",  "10Y", "3m10y spread (bp)"))
if "2Y"  in tenors and "5Y"  in tenors: spreads_to_plot.append(("2Y",  "5Y",  "2s5s spread (bp)"))
if "5Y"  in tenors and "30Y" in tenors: spreads_to_plot.append(("5Y",  "30Y", "5s30s spread (bp)"))

for short, long, title in spreads_to_plot:
    st.subheader(title)
    spread_chart(df_view, short, long, title, lookback=lookback)

# ── Raw data expander ─────────────────────────────────────────────────────────
with st.expander("View raw data"):
    st.dataframe(df_view[["Date"] + tenors].set_index("Date").sort_index(ascending=False),
                 use_container_width=True)
