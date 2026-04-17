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

ALL_TICKERS_INFO = {}
for k, v in ETFS.items(): ALL_TICKERS_INFO[k] = {"cat": "ETF板块", "name": v, "tenor": "N/A"}
for cat, tickers in COMMODITIES.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"商品-{cat}", "name": v, "tenor": "N/A"}
for country, tickers in BONDS.items():
    for k, v in tickers.items(): ALL_TICKERS_INFO[k] = {"cat": f"国债-{country}", "name": v[0], "tenor": v[1], "country": country}

st.set_page_config(page_title="全球宏观实时看板", layout="wide")

# --- 2. 数据引擎 ---
@st.cache_data(ttl=300)
def fetch_all_data():
    all_tickers = list(ALL_TICKERS_INFO.keys())
    df_hist = yf.download(all_tickers, period="1y", interval="1d", progress=False, threads=True)
    close_data = df_hist['Close'].ffill().bfill()
    df_recent = yf.download(all_tickers, period="2d", interval="5m", progress=False)['Close'].ffill().bfill()
    
    beijing_now = datetime.utcnow() + timedelta(hours=8)
    bj_now_str = beijing_now.strftime('%Y-%m-%d %H:%M:%S')

    summary = []
    for ticker in all_tickers:
        if ticker not in close_data.columns: continue
        info = ALL_TICKERS_INFO[ticker]
        
        last = df_recent[ticker].iloc[-1]
        prev = close_data[ticker].iloc[-2]
        d_r = (last / prev) - 1
        eff_date = df_recent.index[-1].strftime('%m-%d')
        
        # 零值回溯
        if abs(d_r) < 0.00001:
            for i in range(1, 6):
                cur_idx, prev_idx = -i, -(i+1)
                temp_r = (close_data[ticker].iloc[cur_idx] / close_data[ticker].iloc[prev_idx]) - 1
                if abs(temp_r) > 0.00001:
                    d_r, last = temp_r, close_data[ticker].iloc[cur_idx]
                    eff_date = close_data.index[cur_idx].strftime('%m-%d')
                    break

        base5 = close_data[ticker].iloc[-7]
        p_r = (prev / base5) - 1
        
        # --- 核心修改：国债收益率负相关显示逻辑 ---
        if "国债" in info["cat"]:
            # 价格涨(d_r > 0) -> 收益率跌
            status = "🟢 价格↑ (收益率↓)" if d_r > 0 else "🔴 价格↓ (收益率↑)"
        else:
            status = "⭐反转" if d_r*p_r < 0 else ("📈上涨" if d_r > 0 else "📉下跌")
            
        summary.append({
            "代码": ticker, "名称": info["name"], "分类": info["cat"], "Tenor": info["tenor"], 
            "最新价": last, "行情日期": eff_date, "变动幅度": d_r, "前5日累计": p_r, 
            "状态/收益率趋势": status, "国家": info.get("country", "N/A")
        })
    return close_data, pd.DataFrame(summary), bj_now_str

def style_table(df):
    existing_cols = df.columns.tolist()
    # 修改列名显示，增加辨识度
    rename_dict = {"变动幅度": "价格变动(%)"}
    df = df.rename(columns=rename_dict)
    
    target_col = "价格变动(%)"
    styler = df.style.format({"最新价": "{:.2f}", target_col: "{:.2%}", "前5日累计": "{:.2%}"})
    
    # 颜色逻辑保持对价格变动的反应
    styler = styler.map(lambda x: 'color: #00ff00' if isinstance(x,float) and x>0 else 'color: #ff4b4b' if isinstance(x,float) and x<0 else '', 
                        subset=[target_col, "前5日累计"])
    return styler

# --- 3. UI 布局 ---
try:
    close_data, df_summary, update_time = fetch_all_data()
    st.title("🌐 全球宏观资产实时看板")
    st.write(f"最后同步 (北京): `{update_time}` | 💡 提示：国债采用 ETF 价格行情，**价格涨(绿色) = 收益率跌**。")

    tab_sum, tab_etf, tab_comm, tab_bond = st.tabs(["📋 全市场汇总", "📊 板块 ETF", "🛡️ 大宗商品", "🏛️ 全球国债"])
    TABLE_HEIGHT = 800

    with tab_sum:
        st.subheader("🚀 全资产排行榜")
        st.dataframe(style_table(df_summary), width="stretch", height=TABLE_HEIGHT, hide_index=True)

    with tab_etf:
        st.subheader("📋 ETF 板块汇总")
        etf_display = df_summary[df_summary['分类'] == "ETF板块"][["代码", "名称", "最新价", "行情日期", "变动幅度", "前5日累计", "状态/收益率趋势"]]
        st.dataframe(style_table(etf_display), width="stretch", height=TABLE_HEIGHT, hide_index=True)
        st.divider()
        cols = st.columns(4)
        for i, ticker in enumerate(ETFS.keys()):
            with cols[i % 4]:
                data = close_data[ticker].dropna()
                fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#00d4ff', width=1.5)))
                fig.update_layout(title=f"<b>{ticker}</b> ({ETFS[ticker]})", height=200, template="plotly_dark", showlegend=False, margin=dict(l=10,r=10,t=40,b=10))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    with tab_comm:
        st.subheader("📋 大宗商品汇总")
        comm_display = df_summary[df_summary['分类'].str.contains("商品")][["代码", "名称", "分类", "最新价", "行情日期", "变动幅度", "前5日累计", "状态/收益率趋势"]]
        st.dataframe(style_table(comm_display), width="stretch", height=TABLE_HEIGHT, hide_index=True)
        st.divider()
        for cat, tickers in COMMODITIES.items():
            st.markdown(f"#### {cat}类")
            cols = st.columns(4)
            for i, ticker in enumerate(tickers.keys()):
                with cols[i % 4]:
                    data = close_data[ticker].dropna()
                    fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ff9900', width=1.5)))
                    fig.update_layout(title=f"<b>{ticker}</b> ({tickers[ticker]})", height=200, template="plotly_dark", showlegend=False, margin=dict(l=10,r=10,t=40,b=10))
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    with tab_bond:
        st.subheader("📊 全球国债价格横向大比武 (Price Comparison)")
        selected_tenor = st.selectbox("选择对比期限：", ["10Y", "30Y", "2Y"])
        comp_df = df_summary[df_summary['Tenor'] == selected_tenor].sort_values("变动幅度", ascending=False)
        # 针对国债页面，明确列名
        bond_comp_display = comp_df[["国家", "代码", "最新价", "行情日期", "变动幅度", "前5日累计", "状态/收益率趋势"]]
        st.dataframe(style_table(bond_comp_display), width="stretch", height=TABLE_HEIGHT, hide_index=True)
        
        st.divider()
        b_tabs = st.tabs(list(BONDS.keys()))
        for b_tab, (country, tickers_dict) in zip(b_tabs, BONDS.items()):
            with b_tab:
                cols = st.columns(4)
                for i, ticker in enumerate(tickers_dict.keys()):
                    with cols[i % 4]:
                        data = close_data[ticker].dropna()
                        fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ffcc00', width=1.5)))
                        fig.update_layout(title=f"<b>{ticker}</b> ({tickers_dict[ticker][0]})", height=200, template="plotly_dark", showlegend=False, margin=dict(l=10,r=10,t=40,b=10))
                        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    if st.sidebar.checkbox("自动刷新 (60s)", value=True):
        time.sleep(60); st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
