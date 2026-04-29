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
YIELD_TICKERS = {"^ZT=F": "US 2Y Yield", "^TNX": "US 10Y Yield"}

ALL_TICKERS_INFO = {}
for k, v in ETFS.items(): ALL_TICKERS_INFO[k] = {"cat": "ETF板块", "name": v, "tenor": "N/A"}
for cat, tickers in COMMODITIES.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"商品-{cat}", "name": v, "tenor": "N/A"}
for country, tickers in BONDS.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"国债-{country}", "name": v[0], "tenor": v[1], "country": country}

st.set_page_config(page_title="全球宏观全资产看板", layout="wide")

# --- 2. 数据引擎：复刻彭博 lookback 逻辑 ---
@st.cache_data(ttl=300)
def fetch_all_data():
    all_tickers = list(ALL_TICKERS_INFO.keys()) + list(YIELD_TICKERS.keys())
    df_hist = yf.download(all_tickers, period="1y", interval="1d", progress=False, threads=True)
    close_data = df_hist['Close'].ffill().bfill()
    df_recent = yf.download(all_tickers, period="2d", interval="5m", progress=False)['Close'].ffill().bfill()
    bj_now_str = (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')

    # --- 彭博 6 状态判定逻辑实现 ---
    y2_now, y2_prev = df_recent["^ZT=F"].iloc[-1], close_data["^ZT=F"].iloc[-2]
    y10_now, y10_prev = df_recent["^TNX"].iloc[-1], close_data["^TNX"].iloc[-2]
    
    curve_now = y10_now - y2_now
    curve_prev = y10_prev - y2_prev
    
    # 状态初始化
    regime = "横盘中性"
    color_regime = "gray"

    # Steepening (曲线变陡: curve > prev)
    if curve_now > curve_prev:
        if y2_now < y2_prev and y10_now < y10_prev: regime, color_regime = "Bull Steepener (牛陡)", "lime"
        elif y2_now > y2_prev and y10_now > y10_prev: regime, color_regime = "Bear Steepener (熊陡)", "orange"
        elif y2_now < y2_prev and y10_now > y10_prev: regime, color_regime = "Steepener Twist (扭曲变陡)", "yellow"
    # Flattening (曲线变平: curve < prev)
    else:
        if y2_now < y2_prev and y10_now < y10_prev: regime, color_regime = "Bull Flattener (牛平)", "cyan"
        elif y2_now > y2_prev and y10_now > y10_prev: regime, color_regime = "Bear Flattener (熊平)", "red"
        elif y2_now > y2_prev and y10_now < y10_prev: regime, color_regime = "Flattener Twist (扭曲变平)", "magenta"

    summary = []
    for ticker in ALL_TICKERS_INFO.keys():
        if ticker not in close_data.columns: continue
        info = ALL_TICKERS_INFO[ticker]
        last, prev, base5 = df_recent[ticker].iloc[-1], close_data[ticker].iloc[-2], close_data[ticker].iloc[-7]
        d_r = (last / prev) - 1
        eff_date = df_recent.index[-1].strftime('%m-%d')
        if abs(d_r) < 0.00001:
            for i in range(1, 6):
                temp_r = (close_data[ticker].iloc[-i] / close_data[ticker].iloc[-(i+1)]) - 1
                if abs(temp_r) > 0.00001: d_r, last, eff_date = temp_r, close_data[ticker].iloc[-i], close_data.index[-i].strftime('%m-%d'); break
        
        p_r = (prev / base5) - 1
        status = regime if "国债" in info["cat"] else ("⭐反转" if d_r*p_r < 0 else ("📈上涨" if d_r > 0 else "📉下跌"))
            
        summary.append({
            "代码": ticker, "名称": info["name"], "分类": info["cat"], "Tenor": info["tenor"], 
            "最新价": last, "行情日期": eff_date, "价格变动": d_r, "前5日累计": p_r, 
            "状态趋势": status, "国家": info.get("country", "N/A")
        })
    return close_data, pd.DataFrame(summary), bj_now_str, regime, color_regime

def render_styled_table(df, height="content"):
    styler = df.style.format({"最新价": "{:.2f}", "价格变动": "{:.2%}", "前5日累计": "{:.2%}"})
    existing = df.columns.tolist()
    subset = [c for c in ["价格变动", "前5日累计"] if c in existing]
    if subset:
        styler = styler.map(lambda x: 'color: #00ff00' if isinstance(x,float) and x>0 else 'color: #ff4b4b' if isinstance(x,float) and x<0 else '', subset=subset)
    st.dataframe(styler, width="stretch", height=height, hide_index=True)

# --- 3. UI 主逻辑 ---
try:
    close_data, df_summary, update_time, regime_now, regime_color = fetch_all_data()
    st.title("🌐 全球宏观资产监控工作站")
    st.write(f"最后同步 (北京): `{update_time}`")

    tabs = st.tabs(["📋 全市场汇总", "🧠 跨市场逻辑分析", "📊 板块 ETF", "🛡️ 大宗商品", "🏛️ 全球国债"])

    # --- TAB 1: 汇总 ---
    with tabs[0]:
        st.subheader("🚀 全资产排行榜")
        render_styled_table(df_summary, height=600)

    # --- TAB 2: 跨市场逻辑分析 (完全复刻彭博状态) ---
    with tabs[1]:
        st.info(f"### 🛡️ 收益率曲线 6 状态诊断：:{regime_color}[{regime_now}]")
        
        cols = st.columns(3)
        cols[0].markdown(f"**Bull Steepener (牛陡)**\n\n🟢 2Y↓, 10Y↓ (2Y跌更快)\n\n**利好**: 黄金、科技、地产")
        cols[1].markdown(f"**Bear Steepener (熊陡)**\n\n🟠 2Y↑, 10Y↑ (10Y涨更快)\n\n**利好**: 能源、金融、商品")
        cols[2].markdown(f"**Steepener Twist (扭曲陡)**\n\n🟡 2Y↓, 10Y↑\n\n**利好**: 银行、再通胀标的")
        
        cols2 = st.columns(3)
        cols2[0].markdown(f"**Bull Flattener (牛平)**\n\n🔵 2Y↓, 10Y↓ (10Y跌更快)\n\n**利好**: 纯债(TLT)、公用事业")
        cols2[1].markdown(f"**Bear Flattener (熊平)**\n\n🔴 2Y↑, 10Y↑ (2Y涨更快)\n\n**利空**: 所有的成长股估值")
        cols2[2].markdown(f"**Flattener Twist (扭曲平)**\n\n🟣 2Y↑, 10Y↓\n\n**状态**: 深度防御模式")

        st.divider()
        c1, c2 = st.columns([0.4, 0.6])
        with c1:
            st.markdown("##### 🚀 联动逻辑校验")
            pairs = [("USO", "XLE", "再通胀联动"), ("TLT", "XLK", "估值敏感联动"), ("GLD", "TLT", "避险情绪联动")]
            for c1_code, c2_code, label in pairs:
                r1 = df_summary[df_summary['代码'] == c1_code]['价格变动'].values[0]
                r2 = df_summary[df_summary['代码'] == c2_code]['价格变动'].values[0]
                st.write(f"**{label}**")
                st.markdown(f"状态: {'✅ 吻合' if (r1*r2>0) else '❌ 背离'} | {c1_code}: {r1:+.2%} | {c2_code}: {r2:+.2%}")
        with c2:
            st.markdown("##### 🌡️ 核心资产相关性矩阵")
            corr = close_data[["XLK", "XLE", "TLT", "USO", "GLD", "XSD"]].pct_change().tail(30).corr()
            st.plotly_chart(px.imshow(corr, text_auto=".2f", color_continuous_scale='RdBu_r', aspect="auto").update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=10,b=10)), use_container_width=True)

    # --- 其他分页保持逻辑 (TABS 2-4) ---
    with tabs[2]:
        render_styled_table(df_summary[df_summary['分类'] == "ETF板块"][["代码", "名称", "最新价", "行情日期", "价格变动", "前5日累计", "状态趋势"]])
        st.divider(); cols = st.columns(4)
        for i, (ticker, name) in enumerate(ETFS.items()):
            with cols[i % 4]:
                data = close_data[ticker].dropna()
                st.plotly_chart(go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#00d4ff', width=1.5))).update_layout(title=f"<b>{ticker}</b> ({name})", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5)), use_container_width=True, config={'displayModeBar': False})

    with tabs[3]:
        render_styled_table(df_summary[df_summary['分类'].str.contains("商品")][["代码", "名称", "分类", "最新价", "行情日期", "价格变动", "前5日累计", "状态趋势"]])
        st.divider()
        for cat, tickers in COMMODITIES.items():
            st.markdown(f"#### {cat}类详情")
            cols = st.columns(4)
            for i, (ticker, name) in enumerate(tickers.items()):
                with cols[i % 4]:
                    data = close_data[ticker].dropna()
                    st.plotly_chart(go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ff9900', width=1.5))).update_layout(title=f"<b>{ticker}</b> ({name})", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5)), use_container_width=True, config={'displayModeBar': False})

    with tabs[4]:
        st.subheader("📊 期限横向大比武 (自动同步 6 状态)")
        selected_tenor = st.selectbox("选择对比期限：", ["10Y", "30Y", "2Y"])
        bond_comp = df_summary[df_summary['Tenor'] == selected_tenor].sort_values("价格变动", ascending=False)
        render_styled_table(bond_comp[["国家", "代码", "最新价", "行情日期", "价格变动", "前5日累计", "状态趋势"]], height="content")
        st.divider(); b_tabs = st.tabs(list(BONDS.keys()))
        for b_tab, (country, tickers_dict) in zip(b_tabs, BONDS.items()):
            with b_tab:
                cols = st.columns(4)
                for i, (ticker, (name, tenor)) in enumerate(tickers_dict.items()):
                    with cols[i % 4]:
                        data = close_data[ticker].dropna()
                        st.plotly_chart(go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ffcc00', width=1.5))).update_layout(title=f"<b>{ticker}</b> ({name})", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5)), use_container_width=True, config={'displayModeBar': False})

    if st.sidebar.checkbox("自动刷新 (60s)", value=True):
        time.sleep(60); st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
