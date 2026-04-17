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
# 收益率曲线核心数据源
YIELD_TICKERS = {"^ZT=F": "US 2Y Yield", "^TNX": "US 10Y Yield"}

ALL_TICKERS_INFO = {}
for k, v in ETFS.items(): ALL_TICKERS_INFO[k] = {"cat": "ETF板块", "name": v, "tenor": "N/A"}
for cat, tickers in COMMODITIES.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"商品-{cat}", "name": v, "tenor": "N/A"}
for country, tickers in BONDS.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"国债-{country}", "name": v[0], "tenor": v[1], "country": country}

st.set_page_config(page_title="全球宏观全资产看板", layout="wide")

# --- 2. 增强型数据引擎 ---
@st.cache_data(ttl=300)
def fetch_all_data():
    all_tickers = list(ALL_TICKERS_INFO.keys()) + list(YIELD_TICKERS.keys())
    df_hist = yf.download(all_tickers, period="1y", interval="1d", progress=False, threads=True)
    close_data = df_hist['Close'].ffill().bfill()
    df_recent = yf.download(all_tickers, period="2d", interval="5m", progress=False)['Close'].ffill().bfill()
    bj_now_str = (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')

    # 计算美债曲线 Regime
    y10_now, y10_prev = df_recent["^TNX"].iloc[-1], close_data["^TNX"].iloc[-2]
    y2_now, y2_prev = df_recent["^ZT=F"].iloc[-1], close_data["^ZT=F"].iloc[-2]
    d10, d2 = y10_now - y10_prev, y2_now - y2_prev
    s_now, s_prev = y10_now - y2_now, y10_prev - y2_prev
    
    if d10 < 0 and d2 < 0: # Bull
        regime = "Bull Steepening (牛陡)" if (s_now > s_prev) else "Bull Flattening (牛平)"
    else: # Bear
        regime = "Bear Steepening (熊陡)" if (s_now > s_prev) else "Bear Flattening (熊平)"

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
                if abs(temp_r) > 0.00001: d_r, last = temp_r, close_data[ticker].iloc[-i]; eff_date = close_data.index[-i].strftime('%m-%d'); break
        
        p_r = (prev / base5) - 1
        
        # --- 核心：状态判定逻辑修改 ---
        if "国债" in info["cat"]:
            status = regime # 国债板块直接显示当前的四象限状态
        else:
            status = "⭐反转" if d_r*p_r < 0 else ("📈上涨" if d_r > 0 else "📉下跌")
            
        summary.append({
            "代码": ticker, "名称": info["name"], "分类": info["cat"], "Tenor": info["tenor"], 
            "最新价": last, "行情日期": eff_date, "价格变动": d_r, "前5日累计": p_r, 
            "状态趋势": status, "国家": info.get("country", "N/A")
        })
    return close_data, pd.DataFrame(summary), bj_now_str, regime

def render_styled_table(df, height="content"):
    existing_cols = df.columns.tolist()
    subset_to_color = [c for c in ["价格变动", "前5日累计"] if c in existing_cols]
    styler = df.style.format({"最新价": "{:.2f}", "价格变动": "{:.2%}", "前5日累计": "{:.2%}"})
    if subset_to_color:
        styler = styler.map(lambda x: 'color: #00ff00' if isinstance(x,float) and x>0 else 'color: #ff4b4b' if isinstance(x,float) and x<0 else '', subset=subset_to_color)
    st.dataframe(styler, width="stretch", height=height, hide_index=True)

# --- 3. UI 主逻辑 ---
try:
    close_data, df_summary, update_time, current_regime = fetch_all_data()
    st.title("🌐 全球宏观资产实时监控")
    st.write(f"最后同步 (北京): `{update_time}`")

    tabs = st.tabs(["📋 全市场汇总", "🧠 跨市场逻辑分析", "📊 板块 ETF", "🛡️ 大宗商品", "🏛️ 全球国债"])

    # --- TAB 0: 汇总 ---
    with tabs[0]:
        st.subheader("🚀 全资产排行榜")
        render_styled_table(df_summary, height=600)

    # --- TAB 1: 跨市场逻辑分析 ---
    with tabs[1]:
        st.info(f"### 🛡️ 当前宏观象限：{current_regime}")
        st.markdown("""
        - **Bull Steepening (牛陡)**：利率全线下行，短端跌更快。**利好黄金、科技股**。
        - **Bull Flattening (牛平)**：利率全线下行，长端跌更快。**利好长债、防御性板块(XLU)**。
        - **Bear Steepening (熊陡)**：利率全线上行，长端涨更快。**利好能源(XLE)、大宗商品**。
        - **Bear Flattening (熊平)**：利率全线上行，短端涨更快。**利空风险资产**。
        """)
        st.divider()
        c1, c2 = st.columns([0.4, 0.6])
        with c1:
            st.markdown("##### 🚀 联动逻辑校验")
            pairs = [("USO", "XLE", "能源共振"), ("TLT", "XLK", "估值共振"), ("GLD", "TLT", "避险共振")]
            for c1_code, c2_code, label in pairs:
                r1 = df_summary[df_summary['代码'] == c1_code]['价格变动'].values[0]
                r2 = df_summary[df_summary['代码'] == c2_code]['价格变动'].values[0]
                aligned = (r1 * r2 > 0)
                st.write(f"**{label}**")
                st.markdown(f"状态: {'✅ 吻合' if aligned else '❌ 背离'} | {c1_code}: {r1:+.2%} | {c2_code}: {r2:+.2%}")
        with c2:
            st.markdown("##### 🌡️ 资产相关性 (30日)")
            corr = close_data[["XLK", "XLE", "TLT", "USO", "GLD", "XSD"]].pct_change().tail(30).corr()
            st.plotly_chart(px.imshow(corr, text_auto=".2f", color_continuous_scale='RdBu_r', aspect="auto").update_layout(template="plotly_dark", height=350, margin=dict(l=10,r=10,t=10,b=10)), use_container_width=True)

    # --- TAB 2: ETF ---
    with tabs[2]:
        st.subheader("📋 ETF 行情汇总")
        render_styled_table(df_summary[df_summary['分类'] == "ETF板块"][["代码", "名称", "最新价", "行情日期", "价格变动", "前5日累计", "状态趋势"]])
        st.divider(); cols = st.columns(4)
        for i, ticker in enumerate(ETFS.keys()):
            with cols[i % 4]:
                data = close_data[ticker].dropna()
                st.plotly_chart(go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#00d4ff', width=1.5))).update_layout(title=f"<b>{ticker}</b> ({ETFS[ticker]})", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5)), use_container_width=True, config={'displayModeBar': False})

    # --- TAB 3: 商品 ---
    with tabs[3]:
        st.subheader("📋 大宗商品汇总")
        render_styled_table(df_summary[df_summary['分类'].str.contains("商品")][["代码", "名称", "分类", "最新价", "行情日期", "价格变动", "前5日累计", "状态趋势"]])
        st.divider()
        for cat, tickers in COMMODITIES.items():
            st.markdown(f"#### {cat}类详情")
            cols = st.columns(4)
            for i, ticker in enumerate(tickers.keys()):
                with cols[i % 4]:
                    data = close_data[ticker].dropna()
                    st.plotly_chart(go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ff9900', width=1.5))).update_layout(title=f"<b>{ticker}</b> ({tickers[ticker]})", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5)), use_container_width=True, config={'displayModeBar': False})

    # --- TAB 4: 国债 ---
    with tabs[4]:
        st.subheader("📊 期限横向大比武")
        tenor = st.selectbox("对比期限：", ["10Y", "30Y", "2Y"])
        bond_comp = df_summary[df_summary['Tenor'] == tenor].sort_values("价格变动", ascending=False)
        # 这里会自动显示判定好的牛陡/熊陡等状态
        render_styled_table(bond_comp[["国家", "代码", "最新价", "行情日期", "价格变动", "前5日累计", "状态趋势"]])
        st.divider(); b_tabs = st.tabs(list(BONDS.keys()))
        for b_tab, (country, tickers_dict) in zip(b_tabs, BONDS.items()):
            with b_tab:
                cols = st.columns(4)
                for i, ticker in enumerate(tickers_dict.keys()):
                    with cols[i % 4]:
                        data = close_data[ticker].dropna()
                        st.plotly_chart(go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ffcc00', width=1.5))).update_layout(title=f"<b>{ticker}</b> ({tickers_dict[ticker][0]})", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5)), use_container_width=True, config={'displayModeBar': False})

    if st.sidebar.checkbox("自动刷新 (60s)", value=True):
        time.sleep(60); st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
