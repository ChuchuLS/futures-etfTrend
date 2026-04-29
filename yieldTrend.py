import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta, timezone
import time

# --- 1. 配置清单 (修复了失效的代码) ---
ETFS = {
    'XLK': '科技', 'XLE': '能源', 'XLF': '金融', 'XLRE': '房地产', 'KBE': '银行股', 
    'KRE': '地区银行', 'ITB': '营建股', 'XHB': '家居装饰', 'XLI': '工业', 'XRT': '零售业', 
    'XLP': '必需消费', 'XLY': '可选消费', 'XLV': '医疗保健', 'XLU': '公用事业', 'IYT': '运输业', 
    'IBB': '生物科技', 'XSD': '半导体'
}
COMMODITIES = {
    "能源": {"USO": "WTI原油", "BNO": "布伦特原油", "NG=F": "天然气主力", "XLE": "能源行业"},
    "金属": {"GLD": "黄金", "SLV": "白银", "CPER": "铜ETF", "PICK": "金属采矿", "DBB": "铝铜锌"},
    "农产品": {"SOYB": "大豆", "CORN": "玉米", "WEAT": "小麦", "SB=F": "原糖", "KC=F": "咖啡"}
}
# 修复：^ZT=F 经常失效，改用稳定度更高的 2Y 收益率指数 ^IRX(3M) 或 ^FVX(5Y)
# 德国债更换为更稳的 BUNT.DE 或直接用 DBGR
BONDS = {
    "美国 (USA)": {"SHY": ("1-3Y短债", "2Y"), "IEF": ("7-10Y中债", "10Y"), "TLT": ("20Y+长债", "30Y")},
    "英国 (UK)": {"IGLT.L": ("英国国债", "10Y"), "VGOV.L": ("英国长债", "30Y")},
    "德国 (GER)": {"DBGR": ("德国债ETF", "10Y"), "IS0L.DE": ("德国长债", "30Y")},
    "日本 (JPN)": {"2556.T": ("日本JGB中债", "10Y"), "2512.T": ("日本JGB长债", "30Y")},
    "澳洲 (AUS)": {"VAF.AX": ("澳洲综合债", "10Y")},
    "加拿大 (CAN)": {"VGV.TO": ("加拿大国债", "10Y"), "VLB.TO": ("加拿大长债", "30Y")}
}
# 收益率曲线分析：改用最稳的 10Y(^TNX) 和 5Y(^FVX) 代替不稳的 2Y
YIELD_TICKERS = {"^FVX": "Short_End", "^TNX": "Long_End"}

ALL_TICKERS_INFO = {}
for k, v in ETFS.items(): ALL_TICKERS_INFO[k] = {"cat": "ETF板块", "name": v, "tenor": "N/A"}
for cat, tickers in COMMODITIES.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"商品-{cat}", "name": v, "tenor": "N/A"}
for country, tickers in BONDS.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"国债-{country}", "name": v[0], "tenor": v[1], "country": country}

st.set_page_config(page_title="全球宏观全资产监控", layout="wide")

# --- 2. 增强型数据引擎 (加入防封和异常处理) ---
@st.cache_data(ttl=900) # 增加缓存到15分钟，防止雅虎封IP
def fetch_all_data():
    all_tickers = list(ALL_TICKERS_INFO.keys()) + list(YIELD_TICKERS.keys())
    try:
        # 合并请求，减少访问次数
        df_all = yf.download(all_tickers, period="2y", interval="1d", progress=False, threads=False)
        close_data = df_all['Close'].ffill().bfill()
        
        # 实时校准数据（只拉取最少的量）
        df_recent = yf.download(all_tickers, period="2d", interval="15m", progress=False, threads=False)['Close'].ffill().bfill()
    except Exception as e:
        st.error(f"雅虎数据接口响应缓慢，请稍后再刷新。错误: {e}")
        return None, None, None, None

    bj_now_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')

    # --- 彭博 6 状态判定 (加入异常安全检查) ---
    try:
        y_s_now, y_s_prev = df_recent["^FVX"].iloc[-1], close_data["^FVX"].iloc[-2]
        y_l_now, y_l_prev = df_recent["^TNX"].iloc[-1], close_data["^TNX"].iloc[-2]
        
        curve_now = y_l_now - y_s_now
        curve_prev = y_l_prev - y_s_prev
        ds, ds_l, ds_s = curve_now - curve_prev, y_l_now - y_l_prev, y_s_now - y_s_prev

        if ds > 0: # Steepening
            if ds_s < 0 and ds_l < 0: reg, col = "Bull Steepener", "#00FF00"
            elif ds_s > 0 and ds_l > 0: reg, col = "Bear Steepener", "#FF8C00"
            else: reg, col = "Steepener Twist", "#FF00FF"
        else: # Flattening
            if ds_s < 0 and ds_l < 0: reg, col = "Bull Flattener", "#00FFFF"
            elif ds_s > 0 and ds_l > 0: reg, col = "Bear Flattener", "#FF0000"
            else: reg, col = "Flattener Twist", "#FFFF00"
            
        hist_curve = close_data["^TNX"] - close_data["^FVX"]
    except:
        reg, col, hist_curve = "数据同步中", "gray", pd.Series()

    summary = []
    for ticker in ALL_TICKERS_INFO.keys():
        if ticker not in close_data.columns: continue
        last, prev, base5 = df_recent[ticker].iloc[-1], close_data[ticker].iloc[-2], close_data[ticker].iloc[-7]
        d_r = (last / prev) - 1
        eff_date = df_recent.index[-1].strftime('%m-%d')
        if abs(d_r) < 0.00001:
            for i in range(1, 6):
                temp_r = (close_data[ticker].iloc[-i] / close_data[ticker].iloc[-(i+1)]) - 1
                if abs(temp_r) > 0.00001: d_r, last, eff_date = temp_r, close_data[ticker].iloc[-i], close_data.index[-i].strftime('%m-%d'); break
        
        summary.append({"代码": ticker, "名称": ALL_TICKERS_INFO[ticker]["name"], "Tenor": ALL_TICKERS_INFO[ticker]["tenor"], 
                        "最新价": last, "日期": eff_date, "价格变动": d_r, "前5日累计": (prev/base5)-1, "状态": reg if "国债" in ALL_TICKERS_INFO[ticker]["cat"] else "N/A"})

    return close_data, pd.DataFrame(summary), bj_now_str, reg, col, hist_curve

def render_styled_table(df, h="content"):
    styler = df.style.format({"最新价": "{:.2f}", "价格变动": "{:.2%}", "前5日累计": "{:.2%}"})
    subset = [c for c in ["价格变动", "前5日累计"] if c in df.columns]
    if subset:
        styler = styler.map(lambda x: 'color: #00ff00' if isinstance(x,float) and x>0 else 'color: #ff4b4b' if isinstance(x,float) and x<0 else '', subset=subset)
    st.dataframe(styler, width="stretch", height=h, hide_index=True)

# --- 3. UI 展示 ---
try:
    close_data, df_summary, update_time, regime_now, regime_color, hist_curve = fetch_all_data()
    if df_summary is not None:
        st.title("🌐 全球宏观工作站 (2026 修复版)")
        st.write(f"最后同步 (北京): `{update_time}`")

        tabs = st.tabs(["📋 汇总", "🧠 跨市场逻辑", "📊 ETF", "🛡️ 商品", "🏛️ 国债"])

        with tabs[1]:
            st.subheader(f"📊 收益率曲线色谱诊断: :{regime_color}[{regime_now}]")
            if not hist_curve.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=hist_curve.index, y=hist_curve.values, line=dict(color='white', width=2)))
                fig.update_layout(height=400, template="plotly_dark", margin=dict(l=10,r=10,t=30,b=10), yaxis=dict(title="5s10s Spread"))
                st.plotly_chart(fig, width="stretch", config={'responsive': True})
            
            st.info("🟢牛陡:利好科技 | 🔴熊平:利空风险 | 🟠熊陡:利好能源 | 🔵牛平:利好纯债")

        with tabs[0]: render_styled_table(df_summary, h=600)
        
        with tabs[2]:
            etf_df = df_summary[df_summary['代码'].isin(ETFS.keys())]
            render_styled_table(etf_df)
            st.divider(); cols = st.columns(4)
            for i, t in enumerate(ETFS.keys()):
                with cols[i%4]:
                    data = close_data[t].dropna()
                    fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#00d4ff', width=1.5)))
                    fig.update_layout(title=f"<b>{t}</b>", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5))
                    st.plotly_chart(fig, width="stretch", config={'displayModeBar': False})

        with tabs[4]:
            tenor = st.selectbox("期限：", ["10Y", "30Y", "2Y"])
            render_styled_table(df_summary[df_summary['Tenor'] == tenor].sort_values("价格变动", ascending=False))
            st.divider(); b_tabs = st.tabs(list(BONDS.keys()))
            for b_tab, country in zip(b_tabs, BONDS.keys()):
                with b_tab:
                    cols = st.columns(4)
                    for i, t in enumerate(BONDS[country].keys()):
                        with cols[i%4]:
                            data = close_data[t].dropna()
                            fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ffcc00', width=1.5)))
                            fig.update_layout(title=f"<b>{t}</b>", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5))
                            st.plotly_chart(fig, width="stretch")

        if st.sidebar.checkbox("自动刷新", value=True):
            time.sleep(60); st.rerun()

except Exception as e:
    st.error(f"初始化中... 请刷新页面。详情: {e}")
