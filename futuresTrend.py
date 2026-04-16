import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# 资产配置保持不变
ASSETS = {
    "能源板块 (Energy)": {
        "USO": "WTI原油ETF", "BNO": "布伦特原油ETF", "NG=F": "天然气主力", 
        "HO=F": "取暖油主力", "RB=F": "汽油主力", "XLE": "标普能源行业"
    },
    "基本金属 (Metals)": {
        "CPER": "铜ETF", "PICK": "全球金属采矿ETF", "ALI=F": "铝主力合约", 
        "DBB": "铝铜锌综合", "SLX": "钢铁行业ETF"
    },
    "贵金属 (Precious)": {
        "GLD": "黄金ETF", "SLV": "白银ETF", "PL=F": "铂金主力", "PA=F": "钯金主力"
    },
    "农产品 (Agriculture)": {
        "SOYB": "大豆ETF", "CORN": "玉米ETF", "WEAT": "小麦ETF", 
        "SB=F": "原糖主力", "KC=F": "咖啡主力", "CT=F": "棉花主力"
    },
    "畜牧/软商品 (Others)": {
        "COW": "畜牧业ETF", "CC=F": "可可主力", "WOOD": "木材ETF"
    }
}

TICKER_TO_NAME = {ticker: name for cat in ASSETS.values() for ticker, name in cat.items()}

st.set_page_config(page_title="全球商品监控看板", layout="wide")

@st.cache_data(ttl=300) # 缩短缓存时间到5分钟，保证行情刷新
def fetch_realtime_data():
    all_tickers = list(TICKER_TO_NAME.keys())
    
    # 1. 抓取历史数据（用于 Z-Score 和 5日累计）
    df_hist = yf.download(all_tickers, period="1y", interval="1d", progress=False)
    close_data = df_hist['Close'].ffill().bfill()

    # 2. 核心补救逻辑：单独抓取最近 2 天的分钟级数据，强制获取“此时此刻”的真实价格
    # 这能解决 Yahoo 历史数据更新慢导致 0.00% 的问题
    print("正在校准实时价格...")
    df_recent = yf.download(all_tickers, period="2d", interval="15m", progress=False)['Close']
    df_recent = df_recent.ffill()

    summary = []
    
    for ticker in all_tickers:
        # 获取历史序列
        hist_series = close_data[ticker].dropna()
        
        # 获取最新真实成交价
        last_price = df_recent[ticker].iloc[-1]
        # 获取昨日收盘价
        prev_close = close_data[ticker].iloc[-2]
        # 获取 6 天前的价格（用于计算前5日累计）
        base_5d_price = close_data[ticker].iloc[-7]

        # 重新计算涨跌幅 (不再依赖历史表的最后一行)
        d_r = (last_price / prev_close) - 1
        p_r = (prev_close / base_5d_price) - 1
        
        # 状态分析逻辑
        if d_r > 0.0001 and p_r < -0.0001: status = "⭐ 跌转涨 (反弹)"
        elif d_r < -0.0001 and p_r > 0.0001: status = "⚠️ 涨转跌 (回调)"
        elif d_r > 0.01 and p_r > 0.02: status = "🔥 加速上涨"
        elif d_r < -0.01 and p_r < -0.02: status = "❄️ 加速下跌"
        elif d_r > 0.0001: status = "📈 维持上扬"
        elif d_r < -0.0001: status = "📉 维持走弱"
        else: status = "➖ 横盘震荡"
        
        summary.append({
            "代号": ticker,
            "资产名称": TICKER_TO_NAME[ticker],
            "昨日涨跌": d_r,
            "前5日累计": p_r,
            "状态分析": status,
            "最新价": last_price
        })
            
    return close_data, pd.DataFrame(summary)

st.title("🛡️ 全球商品市场监控看板 (行情校准版)")

try:
    close_data, summary_df = fetch_realtime_data()

    st.subheader("📋 行情总结与实时查询")
    
    # 渲染带颜色的表格
    def color_style(val):
        if isinstance(val, float):
            return 'color: #00ff00' if val > 0.0001 else 'color: #ff4b4b' if val < -0.0001 else 'color: #888888'
        return ''

    st.dataframe(
        summary_df.style.format({
            "昨日涨跌": "{:.2%}", 
            "前5日累计": "{:.2%}",
            "最新价": "{:.2f}"
        }).map(color_style, subset=["昨日涨跌", "前5日累计"]),
        width="stretch", 
        height="content",
        hide_index=True 
    )

    # 趋势图部分保持不变...
    st.divider()
    # (此处省略之前的绘图代码，保持一致即可)

except Exception as e:
    st.error(f"发生错误: {e}")
