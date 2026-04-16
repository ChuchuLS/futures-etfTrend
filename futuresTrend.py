import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 资产配置
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

@st.cache_data(ttl=300) # 5分钟刷新一次数据
def fetch_realtime_data():
    all_tickers = list(TICKER_TO_NAME.keys())
    
    # A. 抓取历史数据（用于 Z-Score 和 5日累计）
    df_hist = yf.download(all_tickers, period="1y", interval="1d", progress=False)
    close_data = df_hist['Close'].ffill().bfill()

    # B. 核心校准：抓取最近 2 天的分钟级数据，获取真正的最新成交价
    # 解决 Yahoo 历史数据更新延迟导致的 0.00% 报错
    df_recent = yf.download(all_tickers, period="2d", interval="15m", progress=False)['Close']
    df_recent = df_recent.ffill()

    summary = []
    
    for ticker in all_tickers:
        if ticker not in close_data.columns: continue
        
        # 获取最新实时成交价
        last_price = df_recent[ticker].iloc[-1]
        # 获取昨天正式收盘价
        prev_close = close_data[ticker].iloc[-2]
        # 获取 6 天前的价格（用于计算前 5 日累计）
        base_5d_price = close_data[ticker].iloc[-7]

        # 重新计算涨跌幅
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
            "最新价": last_price,
            "昨日涨跌": d_r,
            "前5日累计": p_r,
            "状态分析": status
        })
            
    return close_data, pd.DataFrame(summary)

# --- UI 展示主程序 ---
st.title("🛡️ 全球商品市场监控看板 (行情校准+全屏版)")

try:
    close_data, summary_df = fetch_realtime_data()

    # 1. 总结表格区域
    st.subheader("📋 实时行情汇总")
    
    selected_cat = st.selectbox("筛选板块：", ["全部显示"] + list(ASSETS.keys()))
    
    display_df = summary_df
    if selected_cat != "全部显示":
        target_tickers = list(ASSETS[selected_cat].keys())
        display_df = summary_df[summary_df['代号'].isin(target_tickers)]

    def color_style(val):
        if isinstance(val, float):
            return 'color: #00ff00' if val > 0.0001 else 'color: #ff4b4b' if val < -0.0001 else 'color: #888888'
        return ''

    st.dataframe(
        display_df.style.format({
            "昨日涨跌": "{:.2%}", 
            "前5日累计": "{:.2%}",
            "最新价": "{:.2f}"
        }).map(color_style, subset=["昨日涨跌", "前5日累计"]),
        width="stretch", 
        height="content", # 满屏平铺，无内部滚动条
        hide_index=True 
    )

    # 2. 详细趋势图区域（这次绝对不漏了！）
    st.divider()
    st.subheader("📉 详细走势与异常检测")
    
    tabs = st.tabs(list(ASSETS.keys()))
    for tab, (cat_name, cat_tickers) in zip(tabs, ASSETS.items()):
        with tab:
            valid_tickers = [t for t in cat_tickers.keys() if t in close_data.columns]
            if not valid_tickers:
                st.write("暂无数据")
                continue
                
            cols_per_row = 4
            rows = (len(valid_tickers) + cols_per_row - 1) // cols_per_row
            
            # 创建绘图网格
            fig = make_subplots(
                rows=rows, cols=cols_per_row,
                subplot_titles=[f"<b>{t}</b><br>{cat_tickers[t]}" for t in valid_tickers],
                vertical_spacing=0.1, 
                horizontal_spacing=0.04
            )

            for i, ticker in enumerate(valid_tickers):
                row, col = (i // cols_per_row) + 1, (i % cols_per_row) + 1
                data = close_data[ticker].dropna()
                
                # 异常检测逻辑
                z = (data - data.rolling(20).mean()) / data.rolling(20).std()
                p_out = data[np.abs(z) > 2.5]
                rets = data.pct_change()
                iqr = rets.quantile(0.75) - rets.quantile(0.25)
                v_out = data.loc[rets[(rets > rets.quantile(0.75) + 1.5*iqr) | (rets < rets.quantile(0.25) - 1.5*iqr)].index]

                # 绘制主价格线
                fig.add_trace(
                    go.Scatter(x=data.index, y=data.values, name=ticker, 
                               line=dict(color='#00d4ff', width=1.2), showlegend=False),
                    row=row, col=col
                )
                
                # 绘制红点（价格异常）
                if not p_out.empty:
                    fig.add_trace(
                        go.Scatter(x=p_out.index, y=p_out.values, mode='markers', 
                                   marker=dict(color='red', size=4), showlegend=False),
                        row=row, col=col
                    )
                
                # 绘制黄叉（波动异常）
                if not v_out.empty:
                    fig.add_trace(
                        go.Scatter(x=v_out.index, y=v_out.values, mode='markers', 
                                   marker=dict(color='yellow', symbol='x', size=4), showlegend=False),
                        row=row, col=col
                    )

            # 图表布局优化
            fig.update_layout(
                height=280 * rows, 
                template="plotly_dark", 
                margin=dict(l=10, r=10, t=50, b=10)
            )
            # 2026 最新适配语法
            st.plotly_chart(fig, width="stretch", config={'responsive': True})

except Exception as e:
    st.error(f"分析出错: {e}")
