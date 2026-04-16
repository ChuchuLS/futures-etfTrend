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

@st.cache_data(ttl=1800)
def fetch_data():
    all_tickers = list(TICKER_TO_NAME.keys())
    # 强制下载更长一点的数据，确保 ffill 有足够参考值
    df = yf.download(all_tickers, period="1y", threads=False, progress=False)
    
    if isinstance(df.columns, pd.MultiIndex):
        close_data = df['Close']
    else:
        close_data = df[['Close']]
    
    # --- 强力补洞逻辑 ---
    # 先向前填充（拿昨天补今天），再向后填充（拿明天补昨天），最后补0
    close_data = close_data.ffill().bfill().fillna(0)
    
    daily_rets = (close_data.iloc[-1] / close_data.iloc[-2]) - 1
    past_5d_rets = (close_data.iloc[-2] / close_data.iloc[-7]) - 1
    
    summary = []
    available_tickers = [t for t in all_tickers if t in close_data.columns]
    
    for ticker in available_tickers:
        d_r, p_r = daily_rets[ticker], past_5d_rets[ticker]
        
        # 状态分析
        if d_r > 0 and p_r < 0: status = "⭐ 跌转涨 (反弹)"
        elif d_r < 0 and p_r > 0: status = "⚠️ 涨转跌 (回调)"
        elif d_r > 0.01 and p_r > 0.02: status = "🔥 加速上涨"
        elif d_r < -0.01 and p_r < -0.02: status = "❄️ 加速下跌"
        elif d_r > 0: status = "📈 维持上扬"
        elif d_r < 0: status = "📉 维持走弱"
        else: status = "➖ 横盘震荡"
        
        summary.append({
            "代号": ticker,
            "资产名称": TICKER_TO_NAME[ticker],
            "昨日涨跌": d_r,
            "前5日累计": p_r,
            "状态分析": status
        })
            
    return close_data, pd.DataFrame(summary)

st.title("🛡️ 全球商品市场监控看板")

try:
    close_data, summary_df = fetch_data()

    # 1. 总结表格区域
    st.subheader("📋 行情总结与实时查询")
    
    # 如果你想查询“所有”，只需在下拉框选“全部显示”
    selected_cat = st.selectbox("选择分类 (全屏状态下可点击右侧搜索图标查询)：", ["全部显示"] + list(ASSETS.keys()))
    
    display_df = summary_df
    if selected_cat != "全部显示":
        target_tickers = list(ASSETS[selected_cat].keys())
        display_df = summary_df[summary_df['代号'].isin(target_tickers)]

    # 渲染颜色
    def color_style(val):
        if isinstance(val, float):
            return 'color: #00ff00' if val > 0 else 'color: #ff4b4b'
        return ''

    # --- 这里是查询功能的关键 ---
    st.dataframe(
        display_df.style.format({"昨日涨跌": "{:.2%}", "前5日累计": "{:.2%}"})
        .map(color_style, subset=["昨日涨跌", "前5日累计"]),
        width="stretch", 
        height=None,    # 设置为 None，表格就会根据合约数量自动撑开，不再有内部小滚动条
        hide_index=True 
    )

    # 2. 详细趋势图
    st.divider()
    tabs = st.tabs(list(ASSETS.keys()))
    for tab, (cat_name, cat_tickers) in zip(tabs, ASSETS.items()):
        with tab:
            valid_tickers = [t for t in cat_tickers.keys() if t in close_data.columns]
            cols_per_row = 4
            rows = (len(valid_tickers) + cols_per_row - 1) // cols_per_row
            fig = make_subplots(rows=rows, cols=cols_per_row, subplot_titles=[f"{t}\n{cat_tickers[t]}" for t in valid_tickers],
                                vertical_spacing=0.1, horizontal_spacing=0.04)

            for i, ticker in enumerate(valid_tickers):
                row, col = (i // cols_per_row) + 1, (i % cols_per_row) + 1
                data = close_data[ticker].dropna()
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

            fig.update_layout(height=280 * rows, template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, width="stretch", config={'responsive': True})

except Exception as e:
    st.error(f"发生错误: {e}")
