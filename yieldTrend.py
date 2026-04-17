import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# 1. 资产配置：全球 6 大经济体国债收益率
ASSETS = {
    "美国 (USA)": {
        "^IRX": "3月期", "^FVX": "5年期", "^TNX": "10年期", "^TYX": "30年期"
    },
    "英国 (UK)": {
        "^GUKG2": "2年期", "^GUKG5": "5年期", "^GUKG10": "10年期", "^GUKG30": "30年期"
    },
    "德国 (Germany)": {
        "^GDBR2": "2年期", "^GDBR5": "5年期", "^GDBR10": "10年期", "^GDBR30": "30年期"
    },
    "日本 (Japan)": {
        "^GJGB2": "2年期", "^GJGB5": "5年期", "^GJGB10": "10年期", "^GJGB30": "30年期"
    },
    "加拿大 (Canada)": {
        "^GCAN2Y": "2年期", "^GCAN5Y": "5年期", "^GCAN10": "10年期", "^GCAN30": "30年期"
    },
    "澳大利亚 (Australia)": {
        "^GAUB2": "2年期", "^GAUB5": "5年期", "^GAUB10": "10年期", "^GAUB30": "30年期"
    }
}

# 辅助字典：用于快速查询代号对应的国家和名称
TICKER_INFO = {}
for country, tickers in ASSETS.items():
    for symbol, name in tickers.items():
        TICKER_INFO[symbol] = {"country": country, "name": name}

st.set_page_config(page_title="全球国债收益率看板", layout="wide")

with st.sidebar:
    st.header("系统设置")
    auto_refresh = st.checkbox("开启自动刷新 (60秒)", value=True)

@st.cache_data(ttl=600)
def fetch_and_analyze():
    tickers = list(TICKER_INFO.keys())
    # 抓取数据
    df_hist = yf.download(tickers, period="1y", progress=False)
    close_data = df_hist['Close'] if isinstance(df_hist.columns, pd.MultiIndex) else df_hist[['Close']]
    
    # --- 强力修复 None 问题 ---
    # 先向前填充，再向后填充，确保数据连续
    close_data = close_data.ffill().bfill()
    
    # 抓取实时分钟数据（用于校准最新点）
    df_recent = yf.download(tickers, period="2d", interval="1m", progress=False)['Close']
    df_recent = df_recent.ffill().bfill()

    beijing_now = datetime.utcnow() + timedelta(hours=8)
    bj_now_str = beijing_now.strftime('%Y-%m-%d %H:%M:%S')

    summary_list = []
    for ticker in tickers:
        if ticker not in close_data.columns: continue
        
        # 获取基础信息
        country_name = TICKER_INFO[ticker]["country"]
        expiry_name = TICKER_INFO[ticker]["name"]
        
        # 数据计算
        last_val = df_recent[ticker].iloc[-1]
        prev_close = close_data[ticker].iloc[-2]
        base_5d_price = close_data[ticker].iloc[-7]

        d_r = (last_val / prev_close) - 1
        p_r = (prev_close / base_5d_price) - 1
        
        # 时间转换
        raw_time = df_recent.index[-1]
        bj_data_time = (raw_time + timedelta(hours=8)).strftime('%H:%M:%S')

        # 状态分析
        if d_r > 0.005 and p_r < -0.005: status = "⭐ 触底反弹"
        elif d_r < -0.005 and p_r > 0.005: status = "⚠️ 冲高回落"
        elif abs(d_r) > 0.03: status = "⚡ 大幅波动"
        else: status = "📈 收益率上行" if d_r > 0 else "📉 收益率下行"
        
        summary_list.append({
            "国家": country_name,
            "代码": ticker, 
            "期限": expiry_name,
            "当前收益率": last_val, 
            "今日变动": d_r,
            "过去5日": p_r, 
            "状态分析": status, 
            "更新时间": bj_data_time
        })
    return close_data, pd.DataFrame(summary_list), bj_now_str

# --- UI 展示 ---
st.title("🏛️ 全球主权收益率监控看板 (国家分类版)")

try:
    close_data, summary_df, update_time = fetch_and_analyze()
    st.write(f"**同步时间 (北京):** `{update_time}`")

    # 1. 总结表格
    def color_style(val):
        if isinstance(val, float):
            return 'color: #00ff00' if val > 0 else 'color: #ff4b4b'
        return ''

    st.dataframe(
        summary_df.style.format({"当前收益率": "{:.3f}", "今日变动": "{:.2%}", "过去5日": "{:.2%}"})
        .map(color_style, subset=["今日变动", "过去5日"]),
        width="stretch", height="content", hide_index=True
    )

    # 2. 分类图表
    st.divider()
    tabs = st.tabs(list(ASSETS.keys()))
    for tab, (country, tickers_dict) in zip(tabs, ASSETS.items()):
        with tab:
            cols = st.columns(4)
            valid_tickers = [t for t in tickers_dict.keys() if t in close_data.columns]
            for i, ticker in enumerate(valid_tickers):
                with cols[i % 4]:
                    data = close_data[ticker].dropna()
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=data.index, y=data.values, line=dict(color='#ffcc00', width=1.5)))
                    fig.update_layout(
                        title=f"<b>{ticker}</b> ({tickers_dict[ticker]})",
                        height=230, template="plotly_dark", showlegend=False,
                        margin=dict(l=10, r=10, t=40, b=10),
                        xaxis=dict(tickfont=dict(size=8)), yaxis=dict(tickfont=dict(size=8))
                    )
                    st.plotly_chart(fig, width="stretch", config={'displayModeBar': False})

    if auto_refresh:
        time.sleep(60)
        st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
