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

st.set_page_config(page_title="全球宏观全资产看板", layout="wide")

# --- 2. 数据处理引擎 ---
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
        last, prev, base5 = df_recent[ticker].iloc[-1], close_data[ticker].iloc[-2], close_data[ticker].iloc[-7]
        d_r = (last / prev) - 1
        eff_date = df_recent.index[-1].strftime('%m-%d')
        if abs(d_r) < 0.00001:
            for i in range(1, 6):
                cur_idx, prev_idx = -i, -(i+1)
                temp_r = (close_data[ticker].iloc[cur_idx] / close_data[ticker].iloc[prev_idx]) - 1
                if abs(temp_r) > 0.00001:
                    d_r, last = temp_r, close_data[ticker].iloc[cur_idx]
                    eff_date = close_data.index[cur_idx].strftime('%m-%d')
                    break
        p_r = (prev / base5) - 1
        is_bond = "国债" in info["cat"]
        if is_bond: status = "🟢 价格↑ (收益率↓)" if d_r > 0 else "🔴 价格↓ (收益率↑)"
        else: status = "⭐反转" if d_r*p_r < 0 else ("📈上涨" if d_r > 0 else "📉下跌")
        summary.append({
            "代码": ticker, "名称": info["name"], "分类": info["cat"], "Tenor": info["tenor"], 
            "最新价": last, "日期": eff_date, "价格变动": d_r, "前5日累计": p_r, 
            "状态趋势": status, "国家": info.get("country", "N/A")
        })
    return close_data, pd.DataFrame(summary), bj_now_str

def render_styled_table(df, height="content"):
    existing_cols = df.columns.tolist()
    subset_to_color = [c for c in ["价格变动", "前5日累计"] if c in existing_cols]
    styler = df.style.format({"最新价": "{:.2f}", "价格变动": "{:.2%}", "前5日累计": "{:.2%}"})
    if subset_to_color:
        styler = styler.map(lambda x: 'color: #00ff00' if isinstance(x,float) and x>0 else 'color: #ff4b4b' if isinstance(x,float) and x<0 else '', subset=subset_to_color)
    st.dataframe(styler, width="stretch", height=height, hide_index=True)

# --- 3. UI 主逻辑 ---
try:
    close_data, df_summary, update_time = fetch_all_data()
    st.title("🌐 全球宏观资产实时监控")
    st.write(f"最后同步 (北京): `{update_time}`")

    # --- 新增跨市场分析分页 ---
    tabs = st.tabs(["📋 全市场汇总", "📊 跨市场关联分析", "📊 板块 ETF", "🛡️ 大宗商品", "🏛️ 全球国债"])

    # --- TAB 1: 全市场汇总 ---
    with tabs[0]:
        st.subheader("🚀 全资产排行榜")
        render_styled_table(df_summary, height=600)

    # --- TAB 2: 跨市场关联分析 (核心新逻辑) ---
    with tabs[1]:
        st.subheader("🧠 宏观逻辑联动引擎")
        
        # 定义需要校验的核心逻辑对
        logic_pairs = [
            ("USO (原油)", "XLE (能源)", "能源共振: 油价与能源股正相关"),
            ("TLT (长债)", "XLK (科技)", "估值共振: 利率跌(债涨)利好科技股"),
            ("TLT (长债)", "XLU (公用)", "避险共振: 利率跌(债涨)利好高股息防御"),
            ("GLD (黄金)", "TLT (长债)", "通胀/避险共振: 黄金与长债联动")
        ]

        c1, c2 = st.columns([0.4, 0.6])
        
        with c1:
            st.markdown("##### 🚀 逻辑校验状态")
            for asset1_code, asset2_code, desc in logic_pairs:
                # 获取涨跌
                r1 = df_summary[df_summary['代码'] == asset1_code.split(' ')[0]]['价格变动'].values[0]
                r2 = df_summary[df_summary['代码'] == asset2_code.split(' ')[0]]['价格变动'].values[0]
                
                # 校验逻辑：同向为吻合，反向为背离
                is_aligned = (r1 * r2 > 0)
                icon = "✅ 吻合" if is_aligned else "❌ 背离"
                color = "green" if is_aligned else "orange"
                
                st.write(f"**{desc}**")
                st.markdown(f"状态: :{color}[{icon}] | {asset1_code}: {r1:+.2%} | {asset2_code}: {r2:+.2%}")
                st.divider()

        with c2:
            st.markdown("##### 🌡️ 核心资产关联热力图 (30日滚动)")
            # 计算 30 天相关性
            core_tickers = ["XLK", "XLE", "TLT", "USO", "GLD", "CPER", "XLF"]
            corr_df = close_data[core_tickers].pct_change().tail(30).corr()
            fig_heat = px.imshow(corr_df, text_auto=".2f", color_continuous_scale='RdBu_r', aspect="auto")
            fig_heat.update_layout(template="plotly_dark", height=400, margin=dict(l=10,r=10,t=10,b=10))
            st.plotly_chart(fig_heat, use_container_width=True)

        st.info("💡 逻辑指南：\n1. **吻合** 代表市场当前处于正常定价模式。\n2. **背离** 往往是信号：例如油涨但能源ETF不涨，可能预示能源股已超买或市场担心需求见顶。")

    # --- 后续分页保持不变 (TAB 2-4 -> TABS 2-4) ---
    with tabs[2]:
        st.subheader("📋 ETF 行情汇总")
        etf_df = df_summary[df_summary['分类'] == "ETF板块"][["代码", "名称", "最新价", "日期", "价格变动", "前5日累计", "状态趋势"]]
        render_styled_table(etf_df)
        st.divider()
        cols = st.columns(4)
        for i, ticker in enumerate(ETFS.keys()):
            with cols[i % 4]:
                data = close_data[ticker].dropna()
                fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#00d4ff', width=1.5)))
                fig.update_layout(title=f"<b>{ticker}</b> ({ETFS[ticker]})", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    with tabs[3]:
        st.subheader("📋 大宗商品汇总")
        comm_df = df_summary[df_summary['分类'].str.contains("商品")][["代码", "名称", "分类", "最新价", "日期", "价格变动", "前5日累计", "状态趋势"]]
        render_styled_table(comm_df)
        st.divider()
        for cat, tickers in COMMODITIES.items():
            st.markdown(f"#### {cat}类详情")
            cols = st.columns(4)
            for i, ticker in enumerate(tickers.keys()):
                with cols[i % 4]:
                    data = close_data[ticker].dropna()
                    fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ff9900', width=1.5)))
                    fig.update_layout(title=f"<b>{ticker}</b> ({tickers[ticker]})", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5))
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    with tabs[4]:
        st.subheader("📊 期限横向大比武")
        selected_tenor = st.selectbox("选择对比期限：", ["10Y", "30Y", "2Y"])
        bond_comp = df_summary[df_summary['Tenor'] == selected_tenor].sort_values("价格变动", ascending=False)
        render_styled_table(bond_comp[["国家", "代码", "最新价", "日期", "价格变动", "前5日累计", "状态趋势"]], height="content")
        st.divider()
        b_tabs = st.tabs(list(BONDS.keys()))
        for b_tab, (country, tickers_dict) in zip(b_tabs, BONDS.items()):
            with b_tab:
                cols = st.columns(4)
                for i, ticker in enumerate(tickers_dict.keys()):
                    with cols[i % 4]:
                        data = close_data[ticker].dropna()
                        fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ffcc00', width=1.5)))
                        fig.update_layout(title=f"<b>{ticker}</b> ({tickers_dict[ticker][0]})", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5))
                        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    if st.sidebar.checkbox("自动刷新 (60s)", value=True):
        time.sleep(60); st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
