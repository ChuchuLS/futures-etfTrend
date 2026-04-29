import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
import time

# --- 1. 全资产配置清单 ---
ETFS = {
    'XLK': '科技', 'XLE': '能源', 'XLF': '金融', 'XLRE': '房地产', 'KBE': '银行股', 
    'KRE': '地区银行', 'ITB': '营建股', 'XHB': '家居装饰', 'XLI': '工业', 'XRT': '零售业', 
    'XLP': '必需消费', 'XLY': '可选消费', 'XLV': '医疗保健', 'XLU': '公用事业', 'IYT': '运输业', 
    'IBB': '生物科技', 'XSD': '半导体'
}
COMMODITIES = {
    "能源": {"USO": "WTI原油", "BNO": "布伦特原油", "NG=F": "天然气主力"},
    "金属": {"GLD": "黄金", "SLV": "白银", "CPER": "铜ETF", "PICK": "金属采矿", "DBB": "铝铜锌"},
    "农产品": {"SOYB": "大豆", "CORN": "玉米", "WEAT": "小麦", "SB=F": "原糖", "KC=F": "咖啡"}
}
BONDS = {
    "美国 (USA)": {"SHY": ("1-3Y短债", "2Y"), "IEF": ("7-10Y中债", "10Y"), "TLT": ("20Y+长债", "30Y")},
    "英国 (UK)": {"IGLT.L": ("英国国债", "10Y"), "VGOV.L": ("英国长债", "30Y")},
    "德国 (GER)": {"BUNT.DE": ("德国联邦债", "10Y"), "IS0L.DE": ("德国长债", "30Y")},
    "日本 (JPN)": {"2556.T": ("日本JGB中债", "10Y"), "2512.T": ("日本JGB长债", "30Y")},
    "澳洲 (AUS)": {"VAF.AX": ("澳洲综合债", "10Y")},
    "加拿大 (CAN)": {"VGV.TO": ("加拿大国债", "10Y"), "VLB.TO": ("加拿大长债", "30Y")}
}

st.set_page_config(page_title="全球宏观色谱工作站", layout="wide")

# --- 2. 核心数据引擎 ---
@st.cache_data(ttl=600)
def fetch_macro_data():
    # 抓取 2Y 和 10Y 用于色谱图
    curve_tickers = ["^TNX", "^ZT=F", "^FVX"]
    all_tickers = list(ETFS.keys()) + [t for cat in COMMODITIES.values() for t in cat.keys()] + [t for cat in BONDS.values() for t in cat.keys()] + curve_tickers
    
    df_raw = yf.download(all_tickers, period="2y", interval="1d", progress=False, threads=False)
    close_data = df_raw['Close'].ffill().bfill()
    
    df_rec = yf.download(all_tickers, period="2d", interval="5m", progress=False, threads=False)['Close'].ffill().bfill()
    bj_now = datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S')

    # --- 计算色谱历史 (Regime History) ---
    # 优先用 2Y (^ZT=F)，没数据用 5Y (^FVX)
    s_code = "^ZT=F" if not np.isnan(close_data["^ZT=F"].iloc[-1]) else "^FVX"
    
    hist_df = close_data[[s_code, "^TNX"]].copy()
    hist_df['Spread'] = hist_df["^TNX"] - hist_df[s_code]
    hist_df['d_short'] = hist_df[s_code].diff()
    hist_df['d_long'] = hist_df["^TNX"].diff()
    hist_df['d_spread'] = hist_df['Spread'].diff()

    def calc_regime(row):
        ds, d_s, d_l = row['d_spread'], row['d_short'], row['d_long']
        if ds > 0: # Steepening
            if d_s < 0 and d_l < 0: return "Bull Steepener", "#00FF00" # 绿
            if d_s > 0 and d_l > 0: return "Bear Steepener", "#FF8C00" # 橙
            return "Steepener Twist", "#FF00FF" # 粉
        else: # Flattening
            if d_s < 0 and d_l < 0: return "Bull Flattener", "#00FFFF" # 青
            if d_s > 0 and d_l > 0: return "Bear Flattener", "#FF0000" # 红
            return "Flattener Twist", "#FFFF00" # 黄

    regime_info = hist_df.apply(calc_regime, axis=1)
    hist_df['Regime'] = [x[0] for x in regime_info]
    hist_df['Color'] = [x[1] for x in regime_info]

    # 总结数据计算 (保持之前日期回溯逻辑)
    summary = []
    for ticker, name in {**ETFS, **{t:n for c in COMMODITIES.values() for t,n in c.items()}, **{t:n[0] for c in BONDS.values() for t,n in c.items()}}.items():
        if ticker not in close_data.columns: continue
        last, prev = df_rec[ticker].iloc[-1], close_data[ticker].iloc[-2]
        d_r = (last / prev) - 1
        date_str = df_rec.index[-1].strftime('%m-%d')
        if abs(d_r) < 0.00001:
            for i in range(1, 6):
                tr = (close_data[ticker].iloc[-i] / close_data[ticker].iloc[-(i+1)]) - 1
                if abs(tr) > 0.00001: d_r, last, date_str = tr, close_data[ticker].iloc[-i], close_data.index[-i].strftime('%m-%d'); break
        
        summary.append({"代码": ticker, "名称": name, "最新价": last, "日期": date_str, "价格变动": d_r, 
                        "分类": "国债" if ticker in [t for c in BONDS.values() for t in c.keys()] else "其他"})

    return close_data, pd.DataFrame(summary), bj_now, hist_df

# --- 3. UI 渲染 ---
try:
    close_data, df_sum, update_time, hist_bond = fetch_macro_data()
    st.title("🌐 全球宏观色谱分析工作站")
    st.write(f"同步时间 (北京): `{update_time}`")

    tabs = st.tabs(["📋 全市场汇总", "🧠 跨市场色谱分析", "📊 板块 ETF", "🛡️ 大宗商品", "🏛️ 全球国债"])

    # --- TAB: 跨市场色谱分析 (重点修复区) ---
    with tabs[1]:
        current = hist_bond.iloc[-1]
        st.markdown(f"### 🛡️ 当前宏观状态: <span style='color:{current['Color']}'>{current['Regime']}</span>", unsafe_html=True)
        
        # 绘制彭博风格色谱图
        fig = go.Figure()
        # 1. 绘制色谱柱 (Bar)
        fig.add_trace(go.Bar(
            x=hist_bond.index, y=hist_bond['Spread'],
            marker_color=hist_bond['Color'],
            marker_line_width=0,
            opacity=0.8,
            name="Regime",
            customdata=hist_bond['Regime'],
            hovertemplate="日期: %{x}<br>利差: %{y:.2f} bps<br>状态: %{customdata}<extra></extra>"
        ))
        # 2. 绘制利差连线 (Scatter)
        fig.add_trace(go.Scatter(
            x=hist_bond.index, y=hist_bond['Spread'],
            line=dict(color='white', width=1.5),
            name="2s10s Spread",
            hoverinfo='skip'
        ))

        fig.update_layout(
            height=500, template="plotly_dark", showlegend=False,
            margin=dict(l=10, r=10, t=30, b=10),
            yaxis=dict(title="Spread (Bps)", zeroline=True, zerolinecolor='gray')
        )
        st.plotly_chart(fig, width="stretch", config={'responsive': True})

        # 自定义图例 (美化版)
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.markdown("🟢 **牛陡**\n(Bull Steep)")
        c2.markdown("🟠 **熊陡**\n(Bear Steep)")
        c3.markdown("💗 **扭曲陡**\n(Twist Steep)")
        c4.markdown("🔵 **牛平**\n(Bull Flat)")
        c5.markdown("🔴 **熊平**\n(Bear Flat)")
        c6.markdown("🟡 **扭曲平**\n(Twist Flat)")
        st.info("💡 价格逻辑：价格涨(绿) = 收益率跌。国债板块的状态由美债 2s10s 曲线实时驱动。")

    # --- TAB: 汇总 ---
    with tabs[0]:
        st.dataframe(df_sum.style.format({"最新价":"{:.2f}","价格变动":"{:.2%}"})
                     .map(lambda x: 'color: #00ff00' if isinstance(x,float) and x>0 else 'color: #ff4b4b' if isinstance(x,float) and x<0 else '', subset=["价格变动"]),
                     width="stretch", height=600, hide_index=True)

    # --- TAB: ETF ---
    with tabs[2]:
        cols = st.columns(4)
        for i, (t, n) in enumerate(ETFS.items()):
            with cols[i%4]:
                data = close_data[t].dropna()
                fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#00d4ff', width=1.5)))
                fig.update_layout(title=f"<b>{t}</b> ({n})", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5))
                st.plotly_chart(fig, use_container_width=True)

    # 后续国债和商品分页逻辑保持一致... (此处略，完整版已包含在下面)
    with tabs[3]:
        for cat, tks in COMMODITIES.items():
            st.markdown(f"#### {cat}类")
            cols = st.columns(4)
            for i, (t, n) in enumerate(tks.items()):
                with cols[i%4]:
                    data = close_data[t].dropna()
                    fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ff9900', width=1.5)))
                    fig.update_layout(title=f"<b>{t}</b> ({n})", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5))
                    st.plotly_chart(fig, use_container_width=True)

    with tabs[4]:
        b_tabs = st.tabs(list(BONDS.keys()))
        for b_tab, country in zip(b_tabs, BONDS.keys()):
            with b_tab:
                cols = st.columns(4)
                for i, (t, (n, ten)) in enumerate(BONDS[country].items()):
                    with cols[i%4]:
                        data = close_data[t].dropna()
                        fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ffcc00', width=1.5)))
                        fig.update_layout(title=f"<b>{t}</b>", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5))
                        st.plotly_chart(fig, use_container_width=True)

    if st.sidebar.checkbox("自动刷新", value=True):
        time.sleep(60); st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
