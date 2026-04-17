import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import time

# --- 1. 全资产配置清单 ---
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
    "美国 (USA)": {"^IRX": ("3月期", "Short"), "^FVX": ("5年期", "5Y"), "^TNX": ("10年期", "10Y"), "^TYX": ("30年期", "30Y")},
    "英国 (UK)": {"^GUKG2": ("2年期", "2Y"), "^GUKG5": ("5年期", "5Y"), "^GUKG10": ("10年期", "10Y"), "^GUKG30": ("30年期", "30Y")},
    "德国 (GER)": {"^GDBR2": ("2年期", "2Y"), "^GDBR5": ("5年期", "5Y"), "^GDBR10": ("10年期", "10Y"), "^GDBR30": ("30年期", "30Y")},
    "日本 (JPN)": {"^GJGB2": ("2年期", "2Y"), "^GJGB5": ("5年期", "5Y"), "^GJGB10": ("10年期", "10Y"), "^GJGB30": ("30年期", "30Y")},
    "澳洲 (AUS)": {"^GAUB2": ("2年期", "2Y"), "^GAUB5": ("5年期", "5Y"), "^GAUB10": ("10年期", "10Y"), "^GAUB30": ("30年期", "30Y")},
    "加拿大 (CAN)": {"^GCAN2Y": ("2年期", "2Y"), "^GCAN5Y": ("5年期", "5Y"), "^GCAN10": ("10年期", "10Y"), "^GCAN30": ("30年期", "30Y")}
}

ALL_TICKERS_INFO = {}
for k, v in ETFS.items(): ALL_TICKERS_INFO[k] = {"cat": "ETF", "name": v, "tenor": "N/A"}
for cat, tickers in COMMODITIES.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"商品-{cat}", "name": v, "tenor": "N/A"}
for country, tickers in BONDS.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"国债-{country}", "name": v[0], "tenor": v[1], "country": country}

st.set_page_config(page_title="全球宏观工作站", layout="wide")

# --- 2. 数据引擎 ---
@st.cache_data(ttl=600)
def fetch_all_data():
    all_tickers = list(ALL_TICKERS_INFO.keys())
    df_hist = yf.download(all_tickers, period="1y", progress=False)
    close_data = df_hist['Close'].ffill().bfill()
    df_recent = yf.download(all_tickers, period="2d", interval="1m", progress=False)['Close'].ffill().bfill()
    beijing_now = datetime.utcnow() + timedelta(hours=8)
    bj_now_str = beijing_now.strftime('%Y-%m-%d %H:%M:%S')

    summary = []
    for ticker in all_tickers:
        if ticker not in close_data.columns: continue
        info = ALL_TICKERS_INFO[ticker]
        last, prev, base5 = df_recent[ticker].iloc[-1], close_data[ticker].iloc[-2], close_data[ticker].iloc[-7]
        d_r, p_r = (last/prev)-1, (prev/base5)-1
        status = "⭐反转" if d_r*p_r < 0 else ("📈上涨" if d_r > 0 else "📉下跌")
        summary.append({"代码": ticker, "名称": info["name"], "分类": info["cat"], "Tenor": info["tenor"], 
                        "最新价": last, "昨日涨跌": d_r, "前5日": p_r, "状态": status, "国家": info.get("country", "N/A")})
    return close_data, pd.DataFrame(summary), bj_now_str

def style_table(df):
    return df.style.format({"最新价":"{:.2f}","昨日涨跌":"{:.2%}","前5日":"{:.2%}"})\
             .map(lambda x: 'color: #00ff00' if isinstance(x,float) and x>0 else 'color: #ff4b4b' if isinstance(x,float) and x<0 else '', subset=["昨日涨跌", "前5日"])

# --- 3. UI 布局 ---
try:
    close_data, df_summary, update_time = fetch_all_data()
    st.title("🌐 全球宏观资产监控工作站")
    st.write(f"最后同步 (北京): `{update_time}`")

    # 定义顶级四大标签
    tab_sum, tab_etf, tab_comm, tab_bond = st.tabs(["📋 全市场汇总", "📊 板块 ETF", "🛡️ 大宗商品", "🏛️ 全球国债"])

    # --- TAB 1: 全市场汇总 ---
    with tab_sum:
        st.subheader("🚀 全资产涨跌排行榜")
        st.dataframe(style_table(df_summary), width="stretch", height="content", hide_index=True)

    # --- TAB 2: 板块 ETF ---
    with tab_etf:
        st.subheader("📋 ETF 板块行情快报")
        etf_summary = df_summary[df_summary['分类'] == "ETF"]
        st.dataframe(style_table(etf_summary), width="stretch", height="content", hide_index=True)
        
        st.divider()
        cols = st.columns(4)
        for i, (ticker, name) in enumerate(ETFS.items()):
            with cols[i % 4]:
                data = close_data[ticker].dropna()
                fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#00d4ff', width=1.5)))
                fig.update_layout(title=f"<b>{ticker}</b> ({name})", height=200, template="plotly_dark", showlegend=False, margin=dict(l=10,r=10,t=40,b=10))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # --- TAB 3: 大宗商品 ---
    with tab_comm:
        st.subheader("📋 大宗商品行情快报")
        comm_summary = df_summary[df_summary['分类'].str.contains("商品")]
        st.dataframe(style_table(comm_summary), width="stretch", height="content", hide_index=True)

        st.divider()
        for cat, tickers in COMMODITIES.items():
            st.markdown(f"#### {cat}类详情")
            cols = st.columns(4)
            for i, (ticker, name) in enumerate(tickers.items()):
                with cols[i % 4]:
                    data = close_data[ticker].dropna()
                    fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ff9900', width=1.5)))
                    fig.update_layout(title=f"<b>{ticker}</b> ({name})", height=200, template="plotly_dark", showlegend=False, margin=dict(l=10,r=10,t=40,b=10))
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # --- TAB 4: 全球国债 ---
    with tab_bond:
        st.subheader("📊 期限横向比武 (Relative Value)")
        selected_tenor = st.select_slider("选择期限：", options=["2Y", "5Y", "10Y", "30Y"], value="10Y")
        comp_df = df_summary[df_summary['Tenor'] == selected_tenor].sort_values("最新价", ascending=False)
        st.dataframe(style_table(comp_df[["国家", "代码", "最新价", "昨日涨跌", "前5日", "状态"]]), width="stretch", height="content", hide_index=True)
        
        st.divider()
        st.subheader("📋 国债详细行情快报 (按国家)")
        bond_summary = df_summary[df_summary['分类'].str.contains("国债")].sort_values("国家")
        st.dataframe(style_table(bond_summary), width="stretch", height="content", hide_index=True)

        st.divider()
        b_tabs = st.tabs(list(BONDS.keys()))
        for b_tab, (country, tickers_dict) in zip(b_tabs, BONDS.items()):
            with b_tab:
                cols = st.columns(4)
                for i, (ticker, (name, tenor)) in enumerate(tickers_dict.items()):
                    with cols[i % 4]:
                        data = close_data[ticker].dropna()
                        fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ffcc00', width=1.5)))
                        fig.update_layout(title=f"<b>{ticker}</b> ({name})", height=200, template="plotly_dark", showlegend=False, margin=dict(l=10,r=10,t=40,b=10))
                        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    if st.sidebar.checkbox("自动刷新 (60s)", value=True):
        time.sleep(60); st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
