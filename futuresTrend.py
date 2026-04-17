import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# 1. 资产配置（已移除国债板块）
ASSETS = {
    "能源板块 (Energy)": {
        "USO": "WTI原油ETF", "BNO": "布伦特原油ETF", "NG=F": "天然气主力", 
        "HO=F": "柴油主力", "RB=F": "汽油主力", "XLE": "标普能源行业"
    },
    "基本金属 (Metals)": {
        "CPER": "铜ETF", "PICK": "金属采矿ETF", "ALI=F": "铝主力", 
        "DBB": "铝铜锌综合", "SLX": "钢铁行业ETF"
    },
    "贵金属 (Precious)": {
        "GLD": "黄金ETF", "SLV": "白银ETF", "PL=F": "铂金主力", "PA=F": "钯金主力"
    },
    "农产品 (Agriculture)": {
        "SOYB": "大豆ETF", "CORN": "玉米ETF", "WEAT": "小麦ETF", 
        "SB=F": "原糖主力", "KC=F": "咖啡主力", "CT=F": "棉花主力"
    }
}

TICKER_TO_NAME = {ticker: name for cat in ASSETS.values() for ticker, name in cat.items()}

# 设置页面布局：响应式排版
st.set_page_config(page_title="全球市场实时监控看板", layout="wide")

# --- 侧边栏控制 ---
with st.sidebar:
    st.header("系统设置")
    auto_refresh = st.checkbox("开启自动刷新 (60秒)", value=True)
    st.info("提示：手机端查看时，图表会自动垂直排列。")

# --- 数据抓取与逻辑 ---
@st.cache_data(ttl=600)
def fetch_and_analyze():
    tickers = list(TICKER_TO_NAME.keys())
    # 抓取历史数据
    df_hist = yf.download(tickers, period="1y", progress=False)
    close_data = df_hist['Close'].ffill().bfill()
    # 抓取实时分钟数据
    df_recent = yf.download(tickers, period="1d", interval="1m", progress=False)['Close']
    df_recent = df_recent.ffill()

    # 统一北京时间
    beijing_now = datetime.utcnow() + timedelta(hours=8)
    bj_now_str = beijing_now.strftime('%Y-%m-%d %H:%M:%S')

    daily_rets = (df_recent.iloc[-1] / close_data.iloc[-2]) - 1
    past_5d_rets = (close_data.iloc[-2] / close_data.iloc[-7]) - 1
    
    summary_list = []
    for ticker in tickers:
        d_r = daily_rets[ticker]
        p_r = past_5d_rets[ticker]
        last_price = df_recent[ticker].iloc[-1]
        raw_time = df_recent.index[-1]
        bj_data_time = (raw_time + timedelta(hours=8)).strftime('%H:%M:%S')

        if d_r > 0 and p_r < 0: status = "⭐ 跌转涨"
        elif d_r < 0 and p_r > 0: status = "⚠️ 涨转跌"
        elif abs(d_r) > 0.02: status = "⚡ 剧烈波动"
        else: status = "📈 维持涨势" if d_r > 0 else "📉 维持跌势"
        
        summary_list.append({
            "代号": ticker, "资产名称": TICKER_TO_NAME[ticker],
            "最新价": last_price, "昨日涨跌": d_r,
            "前5日累计": p_r, "状态分析": status, "时间": bj_data_time
        })
    return close_data, pd.DataFrame(summary_list), bj_now_str

# --- UI 展示部分 ---
st.title("🛡️ 全球资产实时监控 (移动适配版)")

try:
    close_data, summary_df, update_time = fetch_and_analyze()
    st.write(f"**同步时间 (北京):** `{update_time}`")

    # 1. 总结表格
    st.dataframe(
        summary_df.style.format({"最新价": "{:.2f}", "昨日涨跌": "{:.2%}", "前5日累计": "{:.2%}"})
        .map(lambda x: 'color: #00ff00' if isinstance(x, float) and x > 0 else 'color: #ff4b4b' if isinstance(x, float) and x < 0 else '', 
             subset=["昨日涨跌", "前5日累计"]),
        width="stretch", height=400, hide_index=True
    )

    # 2. 分类图表展示
    st.divider()
    tabs = st.tabs(list(ASSETS.keys()))
    
    for tab, (cat_name, cat_tickers) in zip(tabs, ASSETS.items()):
        with tab:
            cols = st.columns(4) 
            valid_tickers = [t for t in cat_tickers.keys() if t in close_data.columns]
            
            for i, ticker in enumerate(valid_tickers):
                with cols[i % 4]:
                    data = close_data[ticker].dropna()
                    
                    # 异常检测
                    z = (data - data.rolling(20).mean()) / data.rolling(20).std()
                    p_out = data[np.abs(z) > 2.5]
                    rets = data.pct_change()
                    iqr = rets.quantile(0.75) - rets.quantile(0.25)
                    v_out = data.loc[rets[(rets > rets.quantile(0.75) + 1.5*iqr) | 
                                          (rets < rets.quantile(0.25) - 1.5*iqr)].index]

                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=data.index, y=data.values, line=dict(color='#00d4ff', width=1.5)))
                    
                    if not p_out.empty:
                        fig.add_trace(go.Scatter(x=p_out.index, y=p_out.values, mode='markers', marker=dict(color='red', size=6)))
                    if not v_out.empty:
                        fig.add_trace(go.Scatter(x=v_out.index, y=v_out.values, mode='markers', marker=dict(color='yellow', symbol='x', size=6)))

                    fig.update_layout(
                        title=dict(text=f"<b>{ticker}</b><br>{cat_tickers[ticker]}", font=dict(size=14)),
                        height=250, 
                        margin=dict(l=10, r=10, t=40, b=10),
                        template="plotly_dark",
                        showlegend=False,
                        xaxis=dict(showgrid=False, tickfont=dict(size=8)),
                        yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', tickfont=dict(size=8))
                    )
                    
                    st.plotly_chart(fig, width="stretch", config={'displayModeBar': False})

    if auto_refresh:
        time.sleep(60)
        st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
