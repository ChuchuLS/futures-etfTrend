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
        # Try openpyxl first (.xlsx), fall back to xlrd (.xls)
        try:
            xl = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
        except Exception:
            xl = pd.ExcelFile(io.BytesIO(raw), engine="xlrd")
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

# ── Live data fetch ───────────────────────────────────────────────────────────

# FRED series → our short yield column names
FRED_SERIES = {
    "DGS3MO": "3M",
    "DGS1":   "12M",
    "DGS2":   "2Y",
    "DGS5":   "5Y",
    "DGS10":  "10Y",
    "DGS20":  "20Y",
    "DGS30":  "30Y",
}

# yfinance tickers → column names matching our sheet columns
# Yields:     use FRED instead (more accurate)
# Metals:     GC=F (gold), SI=F (silver), HG=F (copper), PL=F (platinum), PA=F (palladium)
# LME metals: no free source — skip, keep historical only
# Energy:     CL=F (WTI crude), BZ=F (Brent), NG=F (nat gas)
YF_METAL_MAP = {
    "GC=F": "GC1",
    "SI=F": "SI1",
    "HG=F": "HG1",
    "PL=F": "PL1",
    "PA=F": "PA1",
}
YF_ENERGY_MAP = {
    "CL=F": "CL1 COMB",
    "BZ=F": "CO1",
    "NG=F": "NG1",
}

@st.cache_data(ttl=3600)  # refresh every hour
def fetch_fred_yields(start_date: str) -> pd.DataFrame:
    """Fetch Treasury CMT yields from FRED (no API key needed for these series)."""
    import urllib.request, json
    base = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
    frames = {}
    for series, col in FRED_SERIES.items():
        try:
            url = f"{base}{series}&vintage_date=9999-12-31"
            with urllib.request.urlopen(url, timeout=10) as r:
                import io as _io
                raw = r.read().decode()
            df = pd.read_csv(_io.StringIO(raw), parse_dates=["DATE"])
            df = df.rename(columns={"DATE": "Date", series: col})
            df = df[df["Date"] >= start_date]
            df[col] = pd.to_numeric(df[col], errors="coerce")
            frames[col] = df.set_index("Date")[col]
        except Exception:
            pass
    if not frames:
        return pd.DataFrame()
    result = pd.DataFrame(frames).reset_index()
    result = result.sort_values("Date").reset_index(drop=True)
    result = result.ffill().bfill()
    return result

@st.cache_data(ttl=3600)
def fetch_yf_prices(ticker_map: dict, start_date: str) -> pd.DataFrame:
    """Fetch commodity/energy prices from yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()
    tickers = list(ticker_map.keys())
    try:
        raw = yf.download(tickers, start=start_date, auto_adjust=True, progress=False)
        if raw.empty:
            return pd.DataFrame()
        # yfinance returns MultiIndex when multiple tickers
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw.xs("Close", axis=1, level=0)
        else:
            close = raw[["Close"]].rename(columns={"Close": tickers[0]})
        close = close.rename(columns=ticker_map)
        close.index.name = "Date"
        close = close.reset_index().sort_values("Date").reset_index(drop=True)
        close = close.ffill().bfill()
        return close
    except Exception:
        return pd.DataFrame()

def merge_with_live(hist_df: pd.DataFrame, live_df: pd.DataFrame) -> pd.DataFrame:
    """Append live rows that are newer than the last date in historical data."""
    if live_df.empty or hist_df.empty:
        return hist_df
    last_hist = hist_df["Date"].max()
    new_rows = live_df[live_df["Date"] > last_hist].copy()
    if new_rows.empty:
        return hist_df
    # Only keep columns that exist in hist_df
    common_cols = ["Date"] + [c for c in new_rows.columns if c in hist_df.columns and c != "Date"]
    new_rows = new_rows[common_cols]
    merged = pd.concat([hist_df, new_rows], ignore_index=True)
    merged = merged.sort_values("Date").reset_index(drop=True)
    merged = merged.ffill().bfill()
    return merged

# ── Main app ──────────────────────────────────────────────────────────────────
st.title("📈 US Treasury Yield Curve Dashboard")

uploaded = st.file_uploader("Upload your Bloomberg yield data (CSV or Excel)", type=["csv", "xlsx", "xls"])

if uploaded is None:
    st.info("Upload your file to get started. Expected columns: Date, USGG2YR Index, USGG10YR Index, USGG30YR Index (and optionally metal/energy sheets).")
    st.stop()

# Load all sheets once (cached by Streamlit)
all_sheets = load_sheets(uploaded)

# Derive yields dataframe from sheets
_yields_raw = all_sheets.get("yields", list(all_sheets.values())[0] if all_sheets else pd.DataFrame())
_rename = {"USGG2YR":"2Y","USGG10YR":"10Y","USGG30YR":"30Y",
           "USGG3M":"3M","USGG5YR":"5Y","USGG12M":"12M","USGG20YR":"20Y"}
df_hist = _yields_raw.rename(columns={k:v for k,v in _rename.items() if k in _yields_raw.columns})
metal_df_hist  = all_sheets.get("metal",  pd.DataFrame())
energy_df_hist = all_sheets.get("energy", pd.DataFrame())

# ── Live data top-up ──────────────────────────────────────────────────────────
with st.spinner("Fetching latest market data…"):
    _yield_start  = str(df_hist["Date"].max().date()) if not df_hist.empty else "2020-01-01"
    _metal_start  = str(metal_df_hist["Date"].max().date()) if not metal_df_hist.empty else "2020-01-01"
    _energy_start = str(energy_df_hist["Date"].max().date()) if not energy_df_hist.empty else "2020-01-01"

    live_yields = fetch_fred_yields(_yield_start)
    live_metals = fetch_yf_prices(YF_METAL_MAP,  _metal_start)
    live_energy = fetch_yf_prices(YF_ENERGY_MAP, _energy_start)

df        = merge_with_live(df_hist,         live_yields)
metal_df  = merge_with_live(metal_df_hist,   live_metals)
energy_df = merge_with_live(energy_df_hist,  live_energy)

tenors = [c for c in ["3M","12M","2Y","5Y","10Y","20Y","30Y"] if c in df.columns]

# Status banner
_last = df["Date"].max().strftime("%b %d, %Y") if not df.empty else "?"
st.caption(f"Yield data through **{_last}** (FRED live top-up) · Commodities via yfinance")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_yield, tab_comm, tab_corr = st.tabs(["📈 Yield Curve", "📦 Commodities & Energy", "🔗 Correlation"])

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — YIELD CURVE
# ════════════════════════════════════════════════════════════════════════════════
with tab_yield:
    st.sidebar.header("Yield Settings")
    period = st.sidebar.selectbox("Period", ["1Y", "2Y", "5Y", "10Y", "All"], index=2)
    lookback_weeks = st.sidebar.slider("Regime lookback (weeks)", 4, 26, 12)
    lookback = lookback_weeks * 5

    period_map = {"1Y": 252, "2Y": 504, "5Y": 1260, "10Y": 2520, "All": len(df)}
    n = period_map[period]
    df_view = df.iloc[-n:].reset_index(drop=True)

    latest = df_view[["Date"] + tenors].dropna().iloc[-1]
    prev   = df_view[["Date"] + tenors].dropna().iloc[-2]

    st.subheader(f"Latest: {latest['Date'].strftime('%b %d, %Y')}")
    cols_metrics = st.columns(len(tenors) + 2)
    for i, t in enumerate(tenors):
        chg = latest[t] - prev[t]
        cols_metrics[i].metric(label=t, value=f"{latest[t]:.2f}%",
                               delta=f"{chg:+.2f}%", delta_color="inverse")

    if "2Y" in tenors and "10Y" in tenors:
        s2s10 = (latest["10Y"] - latest["2Y"]) * 100
        p2s10 = (prev["10Y"]   - prev["2Y"])   * 100
        cols_metrics[-2].metric("2s10s", f"{s2s10:+.0f} bp", f"{s2s10-p2s10:+.1f} bp")

    if "10Y" in tenors and "30Y" in tenors:
        s10s30 = (latest["30Y"] - latest["10Y"]) * 100
        p10s30 = (prev["30Y"]   - prev["10Y"])   * 100
        cols_metrics[-1].metric("10s30s", f"{s10s30:+.0f} bp", f"{s10s30-p10s30:+.1f} bp")

    st.divider()
    st.subheader("Yield curve snapshot")
    yield_curve_snapshot(df_view, tenors)

    st.divider()
    spreads_to_plot = []
    if "2Y"  in tenors and "10Y" in tenors: spreads_to_plot.append(("2Y",  "10Y", "2s10s spread (bp)"))
    if "10Y" in tenors and "30Y" in tenors: spreads_to_plot.append(("10Y", "30Y", "10s30s spread (bp)"))
    if "3M"  in tenors and "10Y" in tenors: spreads_to_plot.append(("3M",  "10Y", "3m10y spread (bp)"))
    if "2Y"  in tenors and "5Y"  in tenors: spreads_to_plot.append(("2Y",  "5Y",  "2s5s spread (bp)"))
    if "5Y"  in tenors and "30Y" in tenors: spreads_to_plot.append(("5Y",  "30Y", "5s30s spread (bp)"))

    for short, long, title in spreads_to_plot:
        st.subheader(title)
        spread_chart(df_view, short, long, title, lookback=lookback)

    with st.expander("View raw data"):
        st.dataframe(df_view[["Date"] + tenors].set_index("Date").sort_index(ascending=False),
                     use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — COMMODITIES & ENERGY
# ════════════════════════════════════════════════════════════════════════════════
with tab_comm:
    st.sidebar.divider()
    st.sidebar.header("Commodities Settings")
    comm_period = st.sidebar.selectbox("Trend period", ["1Y","2Y","5Y","10Y","All"], index=2, key="comm_period")
    normalize   = st.sidebar.checkbox("Normalize to % return", value=False)
    comm_days   = {"1Y":365,"2Y":730,"5Y":1825,"10Y":3650,"All":99999}[comm_period]

    METAL_GROUPS = {
        "Precious Metals":   ["GC1", "SI1", "PL1", "PA1"],
        "Base Metals (LME)": ["LMCADS03","LMAHDS03","LMZSDS03","LMPBDS03","LMNIDS03","LMSNDS03"],
        "Copper":            ["HG1"],
    }

    def trend_chart(df, cols, title, period_days, normalize=False):
        available = [c for c in cols if c in df.columns]
        if not available:
            st.caption(f"No data found for: {cols}")
            return
        cutoff = df["Date"].max() - pd.Timedelta(days=period_days)
        dff = df[df["Date"] >= cutoff][["Date"] + available].copy()
        palette = ["#378ADD","#1D9E75","#D85A30","#9F77DD","#E8A838",
                   "#E05C8A","#4ade80","#f87171","#60a5fa","#facc15","#fb923c","#c084fc"]
        fig = go.Figure()
        for i, col in enumerate(available):
            y = dff[col].copy()
            if normalize:
                base = y.iloc[0] if y.iloc[0] != 0 else 1
                y = (y / base - 1) * 100
            fig.add_trace(go.Scatter(x=dff["Date"], y=y, name=col, mode="lines",
                                     line=dict(width=1.5, color=palette[i % len(palette)])))
        fig.update_layout(
            title=dict(text=title, font=dict(size=13)), height=280,
            margin=dict(l=50, r=20, t=36, b=36),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=10)),
            yaxis=dict(title="% change from start" if normalize else "Price"),
            xaxis=dict(type="date", showgrid=False),
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

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
            ecols = [c for c in energy_df.columns if c != "Date"]
            trend_chart(energy_df, ecols, "Energy prices", comm_days, normalize)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — CROSS-ASSET CORRELATION
# ════════════════════════════════════════════════════════════════════════════════
with tab_corr:
    st.sidebar.divider()
    st.sidebar.header("Correlation Settings")
    corr_window = st.sidebar.selectbox("Window", ["1M (21d)","3M (63d)","6M (126d)"], index=1, key="corr_win")
    corr_period = st.sidebar.selectbox("History", ["1Y","2Y","5Y","All"], index=1, key="corr_period")
    win_map = {"1M (21d)":21,"3M (63d)":63,"6M (126d)":126}
    window    = win_map[corr_window]
    corr_days = {"1Y":365,"2Y":730,"5Y":1825,"All":99999}[corr_period]

    def build_unified(sheets, days):
        frames = []
        for sheet, sdf in sheets.items():
            if sdf.empty or "Date" not in sdf.columns:
                continue
            cutoff = sdf["Date"].max() - pd.Timedelta(days=days)
            dff = sdf[sdf["Date"] >= cutoff].set_index("Date")
            dff.columns = [f"{sheet}:{c}" for c in dff.columns]
            frames.append(dff)
        if not frames:
            return pd.DataFrame()
        unified = frames[0]
        for f in frames[1:]:
            unified = unified.join(f, how="outer")
        return unified.sort_index().ffill().bfill()

    unified = build_unified(all_sheets, corr_days)

    if unified.empty:
        st.info("No data available for correlation.")
    else:
        all_assets = list(unified.columns)
        col_a, col_b = st.columns(2)
        default_a = next((c for c in all_assets if "10Y" in c), all_assets[0])
        default_b = next((c for c in all_assets if "GC1" in c or "CL1" in c), all_assets[min(1, len(all_assets)-1)])
        asset_a = col_a.selectbox("Asset A", all_assets, index=all_assets.index(default_a), key="ca")
        asset_b = col_b.selectbox("Asset B", all_assets, index=all_assets.index(default_b), key="cb")

        if asset_a != asset_b:
            rets = unified[[asset_a, asset_b]].pct_change().dropna()
            rolling_corr = rets[asset_a].rolling(window).corr(rets[asset_b]).dropna()
            colors = ["#1D9E75" if v >= 0 else "#D85A30" for v in rolling_corr]

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=rolling_corr.index, y=rolling_corr.values,
                marker=dict(color=colors, line_width=0),
                width=int(0.7 * 86_400_000), showlegend=False,
                hovertemplate="<b>%{x|%b %d %Y}</b><br>Corr: %{y:.3f}<extra></extra>",
            ))
            fig.add_hline(y=0,    line_dash="dash", line_color="rgba(150,150,150,0.5)", line_width=1)
            fig.add_hline(y=0.7,  line_dash="dot",  line_color="rgba(29,158,117,0.4)",  line_width=1)
            fig.add_hline(y=-0.7, line_dash="dot",  line_color="rgba(216,90,48,0.4)",   line_width=1)
            fig.update_layout(
                title=dict(text=f"Rolling {corr_window}: {asset_a} vs {asset_b}", font=dict(size=13)),
                height=300, margin=dict(l=50, r=20, t=40, b=36),
                yaxis=dict(title="Correlation", range=[-1.05, 1.05], tickformat=".2f"),
                xaxis=dict(type="date", showgrid=False),
                hovermode="x",
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader(f"Current {corr_window} correlation matrix")
            rets_all     = unified.pct_change().dropna().iloc[-window:]
            corr_matrix  = rets_all.corr()
            short_labels = [c.split(":")[-1] for c in corr_matrix.columns]
            z = corr_matrix.values.round(2).tolist()

            heat = go.Figure(go.Heatmap(
                z=z, x=short_labels, y=short_labels,
                colorscale="RdBu", zmid=0, zmin=-1, zmax=1,
                text=[[f"{v:.2f}" for v in row] for row in z],
                texttemplate="%{text}", textfont=dict(size=9),
                showscale=True, colorbar=dict(thickness=12, len=0.8),
            ))
            heat.update_layout(
                height=max(350, len(short_labels)*28 + 80),
                margin=dict(l=80, r=20, t=20, b=80),
                xaxis=dict(tickangle=-45, tickfont=dict(size=10)),
                yaxis=dict(tickfont=dict(size=10)),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(heat, use_container_width=True)
        else:
            st.info("Select two different assets to compute correlation.")
