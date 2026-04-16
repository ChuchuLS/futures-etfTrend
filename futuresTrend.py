import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 资产配置：替换了失效的 NI=F，改用更稳定的行业 ETF (PICK)
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

st.set_page_config(page_title="全球商品市场监控", layout="wide")

@st.cache_data(ttl=1800)
def fetch_data():
    all_tickers = list(TICKER_TO_NAME.keys())
    # 下载数据，不显示下载进度条以保持界面整洁
    df = yf.download(all_tickers, period="1y", threads=False, progress=False)
    
    if isinstance(df.columns, pd.MultiIndex):
        close_data = df['Close']
    else:
        close_data = df[['Close']]
    
    # 使用最新的填充语法
    close_data = close_data.ffill().bfill()
    
    daily_rets = (close_data.iloc[-1] / close_data.iloc[-2]) - 1
    past_5d_rets = (close_data.iloc[-2] / close_data.iloc[-7]) - 1
    
    summary = []
    # 仅处理成功获取到数据的代号
    available_tickers = [t for t in all_tickers if t in close_data.columns]
    
    for ticker in available_tickers:
        d_r, p_r = daily_rets[ticker], past_5d_rets[ticker]
        
        # 状态分析：明确显示 涨/跌
        if d_r > 0 and p_r < 0: 
            status = "⭐ 跌转涨 (反弹)"
        elif d_r < 0 and p_r > 0: 
            status = "⚠️ 涨转跌 (回调)"
        elif d_r > 0.01 and p_r > 0.02: 
            status = "🔥 加速上涨"
        elif d_r < -0.01 and p_r < -0.02: 
            status = "❄️ 加速下跌"
        elif d_r > 0: 
            status = "📈 维持上涨趋势"
        elif d_r < 0: 
            status = "📉 维持下跌趋势"
        else: 
            status = "➖ 横盘震荡"
        
        summary.append({
            "代号": ticker,
            "资产全称": TICKER_TO_NAME[ticker],
            "昨日涨跌": d_r,
            "前5日累计": p_r,
            "状态分析": status
        })
            
    return close_data, pd.DataFrame(summary)

# --- UI 展示 ---
st.title("🛡️ 全球商品市场监控看板")

try:
    close_data, summary_df = fetch_data()

    # 1. 总结表格 - 适配最新 width 语法
    st.subheader("📋 行情总结与趋势分析")
    selected_cat = st.selectbox("筛选板块：", ["全部显示"] + list(ASSETS.keys()))
    
    display_df = summary_df
    if selected_cat != "全部显示":
        target_tickers = list(ASSETS[selected_cat].keys())
        display_df = summary_df[summary_df['代号'].isin(target_tickers)]

    def color_style(val):
        if isinstance(val, float):
            return 'color: #00ff00' if val > 0 else 'color: #ff4b4b'
        return ''

    # 修复：将 use_container_width=True 替换为 width="stretch"
    st.dataframe(
        display_df.style.format({"昨日涨跌": "{:.2%}", "前5日累计": "{:.2%}"})
        .map(color_style, subset=["昨日涨跌", "前5日累计"]),
        width="stretch", 
        height=450
    )

    # 2. 趋势图
    st.divider()
    tabs = st.tabs(list(ASSETS.keys()))
    for tab, (cat_name, cat_tickers) in zip(tabs, ASSETS.items()):
        with tab:
            # 过滤掉下载失败的代号
            valid_tickers = [t for t in cat_tickers.keys() if t in close_data.columns]
            if not valid_tickers:
                st.warning("该板块暂无有效数据")
                continue
                
            cols_per_row = 4
            rows = (len(valid_tickers) + cols_per_row - 1) // cols_per_row
            fig = make_subplots(rows=rows, cols=cols_per_row, subplot_titles=[f"{t}\n{cat_tickers[t]}" for t in valid_tickers],
                                vertical_spacing=0.1, horizontal_spacing=0.04)

            for i, ticker in enumerate(valid_tickers):
                row, col = (i // cols_per_row) + 1, (i % cols_per_row) + 1
                data = close_data[ticker].dropna()
                
                # 异常检测
                z = (data - data.rolling(20).mean()) / data.rolling(20).std()
                p_out = data[np.abs(z) > 2.5]
                rets = data.pct_change()
                iqr = rets.quantile(0.75) - rets.quantile(0.25)
                v_out = data.loc[rets[(rets > rets.quantile(0.75) + 1.5*iqr) | (rets < rets.quantile(0.25) - 1.5*iqr)].index]

                fig.add_trace(go.Scatter(x=data.index, y=data.values, name=ticker, line=dict(color='#00d4ff', width=1.2), showlegend=False), row=row, col=col)
                if not p_out.empty:
                    fig.add_trace(go.Scatter(x=p_out.index, y=p_out.values, mode='markers', marker=dict(color='red', size=4), showlegend=False), row=row, col=col)
                if not v_out.empty:
                    fig.add_trace(go.Scatter(x=v_out.index, y=v_out.values, mode='markers', marker=dict(color='yellow', symbol='x', size=4), showlegend=False), row=row, col=col)

            # 修复：将 use_container_width=True 替换为 width="stretch"
            fig.update_layout(height=280 * rows, template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, theme="streamlit", config={'responsive': True})

except Exception as e:
    st.error(f"发生错误: {e}")