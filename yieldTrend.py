import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import time

# --- 1. 配置清单 ---
ETFS = {
    'XLE': '能源', 'XLF': '金融', 'XLK': '科技', 'XLRE': '房地产', 'KBE': '银行股', 
    'KRE': '地区银行', 'ITB': '营建股', 'XHB': '家居装饰', 'XLI': '工业', 'XRT': '零售业', 
    'XLP': '必需消费', 'XLY': '可选消费', 'XLV': '医疗保健', 'XLU': '公用事业', 'IYT': '运输业', 
    'IBB': '生物科技', 'XSD': '半导体'
}
COMMODITIES = {
    "能源": {"USO": "WTI原油", "BNO": "布伦特原油", "NG=F": "天然气主力", "XLE": "能源行业"},
    "金属": {"GLD": "黄金", "SLV": "白银", "CPER": "铜ETF", "PICK": "金属采矿", "DBB": "铝铜锌"},
    "农产品": {"SOYB": "大豆", "CORN": "玉米", "WEAT": "小麦", "SB=F": "原糖", "KC=F": "咖啡"}
}
BONDS = {
    "美国 (USA)": {"SHY": ("1-3Y短债", "2Y"), "IEF": ("7-10Y中债", "10Y"), "TLT": ("20Y+长债", "30Y")},
    "英国 (UK)": {"IGLT.L": ("英国国债", "10Y"), "VGOV.L": ("英国长债", "30Y")},
    "德国 (GER)": {"BUND.DE": ("德国联邦债", "10Y"), "IS0L.DE": ("德国长债", "30Y")},
    "日本 (JPN)": {"2556.T": ("日本JGB中债", "10Y"), "2512.T": ("日本JGB长债", "30Y")},
    "澳洲 (AUS)": {"VAF.AX": ("澳洲综合债", "10Y")},
    "加拿大 (CAN)": {"VGV.TO": ("加拿大国债", "10Y"), "VLB.TO": ("加拿大长债", "30Y")}
}
# 收益率曲线核心源 (2Y vs 10Y)
YIELD_TICKERS = {"^ZT=F": "2Y", "^TNX": "10Y"}

ALL_TICKERS_INFO = {}
for k, v in ETFS.items(): ALL_TICKERS_INFO[k] = {"cat": "ETF板块", "name": v, "tenor": "N/A"}
for cat, tickers in COMMODITIES.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"商品-{cat}", "name": v, "tenor": "N/A"}
for country, tickers in BONDS.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"国债-{country}", "name": v[0], "tenor": v[1], "country": country}

st.set_page_config(page_title="全球宏观全资产监控", layout="wide")

# --- 2. 核心逻辑： regime 计算 ---
@st.cache_data(ttl=300)
def fetch_all_data():
    all_tickers = list(ALL_TICKERS_INFO.keys()) + list(YIELD_TICKERS.keys())
    df_hist = yf.download(all_tickers, period="2y", interval="1d", progress=False, threads=True)
    close_data = df_hist['Close'].ffill().bfill()
    df_recent = yf.download(all_tickers, period="2d", interval="5m", progress=False)['Close'].ffill().bfill()
    
    # 构造绘图用的 DataFrame (Spread + Regime)
    hist_bond = close_data[["^ZT=F", "^TNX"]].copy()
    hist_bond['Spread'] = hist_bond["^TNX"] - hist_bond["^ZT=F"]
    hist_bond['d2'] = hist_bond["^ZT=F"].diff()
    hist_bond['d10'] = hist_bond["^TNX"].diff()
    hist_bond['ds'] = hist_bond['Spread'].diff()

    def get_color(row):
        ds, d2, d10 = row['ds'], row['d2'], row['d10']
        if ds > 0: # Steepening
            if d2 < 0 and d10 < 0: return "Bull Steepener", "#00FF00" # Lime
            if d2 > 0 and d10 > 0: return "Bear Steepener", "#FF8C00" # Orange
            return "Steepener Twist", "#FF00FF" # Magenta
        else: # Flattening
            if d2 < 0 and d10 < 0: return "Bull Flattener", "#00FFFF" # Cyan
            if d2 > 0 and d10 > 0: return "Bear Flattener", "#FF0000" # Red
            return "Flattener Twist", "#FFFF00" # Yellow

    regime_results = hist_bond.apply(lambda r: get_color(r), axis=1)
    hist_bond['Regime'] = [x[0] for x in regime_results]
    hist_bond['Color'] = [x[1] for x in regime_results]

    summary = []
    for ticker in ALL_TICKERS_INFO.keys():
        if ticker not in close_data.columns: continue
        last, prev = df_recent[ticker].iloc[-1], close_data[ticker].iloc[-2]
        d_r = (last / prev) - 1
        if abs(d_r) < 0.00001:
            for i in range(1, 6):
                temp_r = (close_data[ticker].iloc[-i] / close_data[ticker].iloc[-(i+1)]) - 1
                if abs(temp_r) > 0.00001: d_r, last = temp_r, close_data[ticker].iloc[-i]; break
        summary.append({"代码": ticker, "名称": ALL_TICKERS_INFO[ticker]["name"], "Tenor": ALL_TICKERS_INFO[ticker]["tenor"], 
                        "最新价": last, "价格变动": d_r, "状态": hist_bond['Regime'].iloc[-1] if "国债" in ALL_TICKERS_INFO[ticker]["cat"] else "N/A"})

    return close_data, pd.DataFrame(summary), hist_bond

# --- 3. UI 展示 ---
try:
    close_data, df_summary, hist_bond = fetch_all_data()
    st.title("🌐 全球宏观资产监控系统 (Bloomberg 色谱版)")

    tabs = st.tabs(["📋 全市场汇总", "🧠 跨市场逻辑分析", "📊 板块 ETF", "🛡️ 大宗商品", "🏛️ 全球国债"])

    # --- TAB 跨市场逻辑分析 (复刻彭博色谱图) ---
    with tabs[1]:
        st.subheader("📊 美债 2s10s 收益率曲线色谱图 (Regime History)")
        
        # 绘制彭博风格色谱图
        fig = go.Figure()
        # 背景色条 (Bar)
        fig.add_trace(go.Bar(
            x=hist_bond.index, y=hist_bond['Spread'],
            marker_color=hist_bond['Color'],
            marker_line_width=0,
            opacity=0.6,
            name="Macro Regime",
            hovertemplate="日期: %{x}<br>Regime: %{customdata}<extra></extra>",
            customdata=hist_bond['Regime']
        ))
        # 利差主线 (Line)
        fig.add_trace(go.Scatter(
            x=hist_bond.index, y=hist_bond['Spread'],
            line=dict(color='white', width=2),
            name="2s10s Spread"
        ))

        fig.update_layout(
            height=500, template="plotly_dark",
            showlegend=False,
            margin=dict(l=10, r=10, t=30, b=10),
            yaxis=dict(title="Spread (Bps)", zeroline=True, zerolinecolor='red')
        )
        st.plotly_chart(fig, use_container_width=True)

        # 图例说明
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.markdown("🟢 **Bull Steepener**\n(牛陡:利好科技/金)")
        c2.markdown("🟠 **Bear Steepener**\n(熊陡:利好能源/金)")
        c3.markdown("💗 **Steepener Twist**\n(扭曲陡:变局)")
        c4.markdown("🔵 **Bull Flattener**\n(牛平:利好长债)")
        c5.markdown("🔴 **Bear Flattener**\n(熊平:利空风险)")
        c6.markdown("🟡 **Flattener Twist**\n(扭曲平:防御)")

    # --- 其他 Tab 保持原有的规整表格逻辑 ---
    with tabs[0]:
        st.dataframe(df_summary.style.format({"最新价":"{:.2f}","价格变动":"{:.2%}"}), width="stretch", height=600, hide_index=True)

    with tabs[2]:
        st.subheader("📋 ETF 板块走势")
        cols = st.columns(4)
        for i, (t, n) in enumerate(ETFS.items()):
            with cols[i%4]:
                data = close_data[t].dropna()
                st.plotly_chart(go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#00d4ff', width=1.5))).update_layout(title=f"{t} ({n})", height=180, template="plotly_dark", margin=dict(l=5,r=5,t=30,b=5), showlegend=False), use_container_width=True, config={'displayModeBar':False})

    with tabs[3]:
        for cat, tks in COMMODITIES.items():
            st.markdown(f"#### {cat}类")
            cols = st.columns(4)
            for i, (t, n) in enumerate(tks.items()):
                with cols[i%4]:
                    data = close_data[t].dropna()
                    st.plotly_chart(go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ff9900', width=1.5))).update_layout(title=f"{t} ({n})", height=180, template="plotly_dark", margin=dict(l=5,r=5,t=30,b=5), showlegend=False), use_container_width=True, config={'displayModeBar':False})

    with tabs[4]:
        tenor = st.selectbox("选择期限：", ["10Y", "30Y", "2Y"])
        bond_comp = df_summary[df_summary['Tenor'] == tenor].sort_values("价格变动", ascending=False)
        st.dataframe(bond_comp, width="stretch", hide_index=True)
        st.divider()
        b_tabs = st.tabs(list(BONDS.keys()))
        for b_tab, country in zip(b_tabs, BONDS.keys()):
            with b_tab:
                cols = st.columns(4)
                for i, (t, (n, ten)) in enumerate(BONDS[country].items()):
                    with cols[i%4]:
                        data = close_data[t].dropna()
                        st.plotly_chart(go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ffcc00', width=1.5))).update_layout(title=f"{t} ({n})", height=180, template="plotly_dark", margin=dict(l=5,r=5,t=30,b=5), showlegend=False), use_container_width=True, config={'displayModeBar':False})

    if st.sidebar.checkbox("自动刷新 (60s)", value=True):
        time.sleep(60); st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
