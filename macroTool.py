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
def clean_sheet(df: pd.DataFrame) -> pd.DataFrame:
    """Standardise a single sheet: strip column names, parse Date, ffill blanks, sort."""
    df = df.copy()
    df.columns = df.columns.str.strip()
    # Find the date column (first column or one named Date)
    if "Date" not in df.columns:
        df = df.rename(columns={df.columns[0]: "Date"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    num_cols = df.select_dtypes(include="number").columns
    df[num_cols] = df[num_cols].ffill().bfill()
    return df

def shorten(col: str) -> str:
    """Strip Bloomberg suffix from column name."""
    return col.replace(" Comdty", "").replace(" Index", "").strip()

@st.cache_data
def load_sheets(file) -> dict:
    """Return dict of {sheet_name: DataFrame}. Reads file bytes once to avoid buffer exhaustion."""
    import io
    raw = file.read()          # read once into bytes
    name = file.name.lower()
    sheets = {}

    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(raw))
        df = clean_sheet(df)
        df.columns = [shorten(c) if c != "Date" else c for c in df.columns]
        sheets["yields"] = df
    else:
        xl = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
        for sheet in xl.sheet_names:
            try:
                df = xl.parse(sheet)
                if df.empty:
                    continue
                df = clean_sheet(df)
                df.columns = [shorten(c) if c != "Date" else c for c in df.columns]
                sheets[sheet] = df
            except Exception as e:
                st.warning(f"Could not parse sheet '{sheet}': {e}")
    return sheets

@st.cache_data
def load_data(file) -> pd.DataFrame:
    """Return yields sheet only, with short tenor column names."""
    sheets = load_sheets(file)
    df = sheets.get("yields", list(sheets.values())[0] if sheets else pd.DataFrame())
    rename = {
        "USGG2YR":  "2Y", "USGG10YR": "10Y", "USGG30YR": "30Y",
        "USGG3M":   "3M", "USGG5YR":  "5Y",  "USGG12M":  "12M",
        "USGG20YR": "20Y",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    return df

# ── Spread chart builder ──────────────────────────────────────────────────────
def spread_chart(df, short, long, title, lookback=60):
    if short not in df.columns or long not in df.columns:
        st.warning(f"Missing columns: {short} or {long}")
        return

    spread = (df[long] - df[short]) * 100  # bps
    regimes = add_regimes(df, f"{short}{long}", short, long, lookback)
    colors = [REGIME_COLORS.get(r, "#9ca3af") for r in regimes]

    dates = df["Date"].tolist()
    sv = spread.tolist()

    # Infer bar width from median date gap — handles daily or weekly data
    if len(dates) > 1:
        gaps = [(dates[i+1] - dates[i]).days for i in range(min(20, len(dates)-1))]
        median_gap = sorted(gaps)[len(gaps)//2]
    else:
        median_gap = 1
    bar_width_ms = int(median_gap * 0.7 * 86_400_000)

    fig = go.Figure()

    # Single bar trace with explicit width in ms.
    # All bars live in one trace so Plotly cannot drop any on zoom.
    # Explicit ms width prevents auto-rescaling on zoom (the disappearing bug).
    fig.add_trace(go.Bar(
        x=dates,
        y=sv,
        width=bar_width_ms,
        marker=dict(color=colors, line_width=0),
        showlegend=False,
        hovertemplate="<b>%{x|%b %d %Y}</b><br>Spread: %{y:.0f} bp<br>Regime: %{customdata}<extra></extra>",
        customdata=regimes,
    ))

    # Legend-only invisible traces
    seen = set()
    for regime, color in REGIME_COLORS.items():
        if regime in regimes and regime not in seen:
            seen.add(regime)
            fig.add_trace(go.Scatter(
                x=[None], y=[None],
                mode="markers",
                marker=dict(symbol="square", size=10, color=color),
                name=regime,
                showlegend=True,
            ))

    fig.add_hline(y=0, line_dash="dash", line_color="rgba(150,150,150,0.5)", line_width=1)

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        barmode="overlay",
        height=300,
        margin=dict(l=50, r=20, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=11)),
        yaxis=dict(title="bp", ticksuffix=" bp"),
        xaxis=dict(type="date", showgrid=False),
        hovermode="x",
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
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True})

# ── Main app ──────────────────────────────────────────────────────────────────
st.title("📈 US Treasury Yield Curve Dashboard")

uploaded = st.file_uploader("Upload your Bloomberg yield data (CSV or Excel)", type=["csv", "xlsx", "xls"])

if uploaded is None:
    st.info("Upload your file to get started. Expected columns: Date, USGG2YR Index, USGG10YR Index, USGG30YR Index (and optionally 3M, 5Y, 12M, 20Y).")
    st.stop()

# Load all sheets once (cached by Streamlit)
all_sheets = all_sheets  # already loaded above

# Derive yields dataframe from sheets
_yields_raw = all_sheets.get("yields", list(all_sheets.values())[0] if all_sheets else pd.DataFrame())
_rename = {"USGG2YR":"2Y","USGG10YR":"10Y","USGG30YR":"30Y",
           "USGG3M":"3M","USGG5YR":"5Y","USGG12M":"12M","USGG20YR":"20Y"}
df = _yields_raw.rename(columns={k:v for k,v in _rename.items() if k in _yields_raw.columns})
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


# ════════════════════════════════════════════════════════════════════════════════
# COMMODITIES & ENERGY PAGE
# ════════════════════════════════════════════════════════════════════════════════

st.divider()
st.header("📦 Commodities & Energy — Long-term Trend")

sheets = all_sheets  # already loaded above

METAL_GROUPS = {
    "Precious Metals":  ["GC1", "SI1", "PL1", "PA1"],
    "Base Metals (LME)":["LMCADS03","LMAHDS03","LMZSDS03","LMPBDS03","LMNIDS03","LMSNDS03"],
    "Copper":           ["HG1"],
}
ENERGY_COLS = ["CL1 COMB", "CO1", "NG1"]

def trend_chart(df, cols, title, period_days, normalize=False):
    """Line chart of selected columns over the period."""
    available = [c for c in cols if c in df.columns]
    if not available:
        st.caption(f"No data for: {cols}")
        return
    cutoff = df["Date"].max() - pd.Timedelta(days=period_days)
    dff = df[df["Date"] >= cutoff][["Date"] + available].copy()

    fig = go.Figure()
    palette = ["#378ADD","#1D9E75","#D85A30","#9F77DD","#E8A838",
               "#E05C8A","#4ade80","#f87171","#60a5fa","#facc15","#fb923c","#c084fc"]
    for i, col in enumerate(available):
        y = dff[col]
        if normalize:
            base = y.iloc[0] if y.iloc[0] != 0 else 1
            y = (y / base - 1) * 100
        fig.add_trace(go.Scatter(
            x=dff["Date"], y=y,
            name=col, mode="lines",
            line=dict(width=1.5, color=palette[i % len(palette)]),
        ))

    yaxis_title = "% change from start" if normalize else "Price"
    fig.update_layout(
        title=dict(text=title, font=dict(size=13)),
        height=280,
        margin=dict(l=50, r=20, t=36, b=36),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=10)),
        yaxis=dict(title=yaxis_title),
        xaxis=dict(type="date", showgrid=False),
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

# Sidebar additions
st.sidebar.divider()
st.sidebar.subheader("Commodities")
comm_period = st.sidebar.selectbox("Trend period", ["1Y","2Y","5Y","10Y","All"], index=2, key="comm_period")
normalize = st.sidebar.checkbox("Normalize to % return", value=False)
comm_days = {"1Y":365,"2Y":730,"5Y":1825,"10Y":3650,"All":99999}[comm_period]

metal_df   = sheets.get("metal",   pd.DataFrame())
energy_df  = sheets.get("energy",  pd.DataFrame())

if metal_df.empty and energy_df.empty:
    st.info("No 'metal' or 'energy' sheets found in the uploaded file.")
else:
    if not metal_df.empty:
        st.subheader("Metals")
        for group_name, cols in METAL_GROUPS.items():
            avail = [c for c in cols if c in metal_df.columns]
            if avail:
                trend_chart(metal_df, avail, group_name, comm_days, normalize)

    if not energy_df.empty:
        st.subheader("Energy")
        # Use whatever columns exist (CL1, CO1, NG1 variants)
        ecols = [c for c in energy_df.columns if c != "Date"]
        trend_chart(energy_df, ecols, "Energy prices", comm_days, normalize)

# ════════════════════════════════════════════════════════════════════════════════
# CROSS-ASSET CORRELATION PAGE
# ════════════════════════════════════════════════════════════════════════════════

st.divider()
st.header("🔗 Cross-asset Rolling Correlation")

# Sidebar
st.sidebar.divider()
st.sidebar.subheader("Correlation")
corr_window = st.sidebar.selectbox("Window", ["1M (21d)","3M (63d)","6M (126d)"], index=1, key="corr_win")
corr_period = st.sidebar.selectbox("History", ["1Y","2Y","5Y","All"], index=1, key="corr_period")
win_map = {"1M (21d)":21,"3M (63d)":63,"6M (126d)":126}
window = win_map[corr_window]
corr_days = {"1Y":365,"2Y":730,"5Y":1825,"All":99999}[corr_period]

# Build unified price dataframe from all sheets
def build_unified(sheets, days):
    frames = []
    for sheet, df in sheets.items():
        if df.empty or "Date" not in df.columns:
            continue
        cutoff = df["Date"].max() - pd.Timedelta(days=days)
        dff = df[df["Date"] >= cutoff].set_index("Date")
        # Prefix columns with sheet name to avoid collisions
        dff.columns = [f"{sheet}:{c}" for c in dff.columns]
        frames.append(dff)
    if not frames:
        return pd.DataFrame()
    unified = frames[0]
    for f in frames[1:]:
        unified = unified.join(f, how="outer")
    unified = unified.sort_index().ffill().bfill()
    return unified

# Let user pick two assets to correlate
unified = build_unified(sheets, corr_days)
if unified.empty:
    st.info("Upload a multi-sheet file to see cross-asset correlations.")
else:
    all_assets = list(unified.columns)
    col_a, col_b = st.columns(2)
    default_a = next((c for c in all_assets if "10Y" in c or "GC1" in c), all_assets[0])
    default_b = next((c for c in all_assets if "CL1" in c or "GC1" in c and c != default_a), all_assets[min(1,len(all_assets)-1)])
    asset_a = col_a.selectbox("Asset A", all_assets, index=all_assets.index(default_a), key="ca")
    asset_b = col_b.selectbox("Asset B", all_assets, index=all_assets.index(default_b), key="cb")

    if asset_a != asset_b:
        rets = unified[[asset_a, asset_b]].pct_change().dropna()
        rolling_corr = rets[asset_a].rolling(window).corr(rets[asset_b]).dropna()

        # Color by positive/negative
        colors = ["#1D9E75" if v >= 0 else "#D85A30" for v in rolling_corr]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=rolling_corr.index,
            y=rolling_corr.values,
            marker=dict(color=colors, line_width=0),
            width=int(0.7 * 86_400_000),
            showlegend=False,
            hovertemplate="<b>%{x|%b %d %Y}</b><br>Corr: %{y:.3f}<extra></extra>",
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="rgba(150,150,150,0.5)", line_width=1)
        fig.add_hline(y=0.7,  line_dash="dot", line_color="rgba(29,158,117,0.4)",  line_width=1)
        fig.add_hline(y=-0.7, line_dash="dot", line_color="rgba(216,90,48,0.4)",   line_width=1)
        fig.update_layout(
            title=dict(text=f"Rolling {corr_window} correlation: {asset_a} vs {asset_b}", font=dict(size=13)),
            height=300,
            margin=dict(l=50, r=20, t=40, b=36),
            yaxis=dict(title="Correlation", range=[-1.05, 1.05], tickformat=".2f",
                       zeroline=False),
            xaxis=dict(type="date", showgrid=False),
            hovermode="x",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Correlation heatmap across all assets (latest window)
        st.subheader(f"Current {corr_window} correlation matrix")
        rets_all = unified.pct_change().dropna().iloc[-window:]
        corr_matrix = rets_all.corr()
        # Strip sheet prefix for display
        short_labels = [c.split(":")[-1] for c in corr_matrix.columns]

        import plotly.figure_factory as ff
        z = corr_matrix.values.round(2).tolist()
        heat = go.Figure(go.Heatmap(
            z=z,
            x=short_labels, y=short_labels,
            colorscale="RdBu", zmid=0, zmin=-1, zmax=1,
            text=[[f"{v:.2f}" for v in row] for row in z],
            texttemplate="%{text}",
            textfont=dict(size=9),
            showscale=True,
            colorbar=dict(thickness=12, len=0.8),
        ))
        heat.update_layout(
            height=max(350, len(short_labels)*28 + 80),
            margin=dict(l=80, r=20, t=20, b=80),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10)),
            yaxis=dict(tickfont=dict(size=10)),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(heat, use_container_width=True)
    else:
        st.info("Select two different assets to compute correlation.")
