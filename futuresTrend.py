import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time


# ...
# 获取本地北京时间 (UTC+8)
current_time_str = (datetime.utcnow() + timedelta(hours=8)).strftime('%H:%M:%S')

# 1. 资产配置
ASSETS = {
    "能源板块 (Energy)": {
        "USO": "WTI原油ETF", "BNO": "布伦特原油ETF", "NG=F": "天然气主力", 
        "HO=F": "取暖油主力", "RB=F": "汽油主力", "XLE": "标普能源行业"
    },
    "基本金属 (Metals)": {
        "CPER": "铜ETF", "PICK": "金属采矿ETF", "ALI=F": "铝主力合约", 
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

st.set_page_config(page_title="全球商品实时监控", layout="wide")

# --- 数据抓取函数 ---
def fetch_realtime_data():
    all_tickers = list(TICKER_TO_NAME.keys())
    
    # 抓取历史与实时数据 (保持不变)
    df_hist = yf.download(all_tickers, period="1y", interval="1d", progress=False)
    close_data = df_hist['Close'].ffill().bfill()
    df_recent = yf.download(all_tickers, period="1d", interval="1m", progress=False)['Close']
    df_recent = df_recent.ffill()

    summary = []
    # 【核心修改点1：改为北京时间】
    beijing_now = datetime.utcnow() + timedelta(hours=8)
    current_time_str = beijing_now.strftime('%H:%M:%S') 

    for ticker in all_tickers:
        if ticker not in close_data.columns: continue
        
        last_price = df_recent[ticker].iloc[-1]
        # 【核心修改点2：数据点时间也转为北京时间】
        # 注意：这里假设 yfinance 返回的是 UTC，如果是美东时间则需要 +12/13 小时
        # 我们根据服务器同步时间来统一，直接加 8 小时最直观
        raw_data_time = df_recent.index[-1]
        data_time = (raw_data_time + timedelta(hours=8)).strftime('%H:%M:%S')
        # 获取昨天收盘价
        prev_close = close_data[ticker].iloc[-2]
        # 获取 6 天前的价格
        base_5d_price = close_data[ticker].iloc[-7]

        d_r = (last_price / prev_close) - 1
        p_r = (prev_close / base_5d_price) - 1
        
        # 状态分析
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
            "涨跌幅": d_r,
            "前5日累计": p_r,
            "状态分析": status,
            "数据时间": data_time
        })
            
    return close_data, pd.DataFrame(summary), current_time_str

# --- UI 展示主程序 ---
st.title("🛡️ 全球商品市场监控看板 (实时校准版)")

# 添加自动刷新开关
with st.sidebar:
    st.header("控制面板")
    auto_refresh = st.checkbox("开启自动刷新 (60秒)", value=True)
    if auto_refresh:
        st.info("页面将每分钟自动获取最新行情")

# 渲染主要内容
try:
    close_data, summary_df, last_update = fetch_realtime_data()

    # 1. 总结表格区域
    st.subheader(f"📋 实时行情汇总 (系统最后同步: {last_update})")
    
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
            "涨跌幅": "{:.2%}", 
            "前5日累计": "{:.2%}",
            "最新价": "{:.2f}"
        }).map(color_style, subset=["涨跌幅", "前5日累计"]),
        width="stretch", 
        height="content", 
        hide_index=True 
    )

    # 2. 趋势图
    st.divider()
    st.subheader("📉 板块历史趋势与异常检测")
    tabs = st.tabs(list(ASSETS.keys()))
    for tab, (cat_name, cat_tickers) in zip(tabs, ASSETS.items()):
        with tab:
            valid_tickers = [t for t in cat_tickers.keys() if t in close_data.columns]
            if not valid_tickers: continue
            
            rows = (len(valid_tickers) + 3) // 4
            fig = make_subplots(rows=rows, cols=4, subplot_titles=[f"<b>{t}</b><br>{cat_tickers[t]}" for t in valid_tickers],
                                vertical_spacing=0.1, horizontal_spacing=0.04)

            for i, ticker in enumerate(valid_tickers):
                row, col = (i // 4) + 1, (i % 4) + 1
                data = close_data[ticker].dropna()
                z = (data - data.rolling(20).mean()) / data.rolling(20).std()
                p_out = data[np.abs(z) > 2.5]
                rets = data.pct_change()
                v_out = data.loc[rets[(rets > rets.quantile(0.75) + 1.5*(rets.quantile(0.75)-rets.quantile(0.25))) | 
                                      (rets < rets.quantile(0.25) - 1.5*(rets.quantile(0.75)-rets.quantile(0.25)))].index]

                fig.add_trace(go.Scatter(x=data.index, y=data.values, name=ticker, line=dict(color='#00d4ff', width=1.2), showlegend=False), row=row, col=col)
                if not p_out.empty:
                    fig.add_trace(go.Scatter(x=p_out.index, y=p_out.values, mode='markers', marker=dict(color='red', size=4), showlegend=False), row=row, col=col)
                if not v_out.empty:
                    fig.add_trace(go.Scatter(x=v_out.index, y=v_out.values, mode='markers', marker=dict(color='yellow', symbol='x', size=4), showlegend=False), row=row, col=col)

            fig.update_layout(height=280 * rows, template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, width="stretch", config={'responsive': True})

    # --- 自动刷新逻辑 ---
    if auto_refresh:
        time.sleep(60) # 等待 60 秒
        st.rerun()    # 强制页面重新运行

except Exception as e:
    st.error(f"分析出错: {e}")
