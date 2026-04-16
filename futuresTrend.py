import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# 1. 资产配置：新增美国国债模块
ASSETS = {
    "美国国债 (Treasury)": {
        "^IRX": "13周国债收益率", "^FVX": "5年期国债收益率", "^TNX": "10年期国债收益率", 
        "^TYX": "30年期国债收益率", "SHY": "1-3年国债ETF", "IEF": "7-10年国债ETF", 
        "TLT": "20年期+国债ETF", "AGG": "综合债券指数"
    },
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

st.set_page_config(page_title="全球市场实时监控看板", layout="wide")

# --- 侧边栏控制 ---
with st.sidebar:
    st.header("系统设置")
    auto_refresh = st.checkbox("开启自动刷新 (60秒)", value=True)
    st.info("提示：国债收益率(^开头)显示的是百分比点数")

# --- 数据抓取与逻辑 ---
def fetch_and_analyze():
    tickers = list(TICKER_TO_NAME.keys())
    
    # 抓取历史数据
    df_hist = yf.download(tickers, period="1y", progress=False)
    close_data = df_hist['Close'] if isinstance(df_hist.columns, pd.MultiIndex) else df_hist[['Close']]
    
    # 抓取实时分钟数据
    df_recent = yf.download(tickers, period="1d", interval="1m", progress=False)['Close']
    
    # 填充空值
    close_data = close_data.ffill().bfill()
    df_recent = df_recent.ffill()

    # 计算北京时间
    beijing_now = datetime.utcnow() + timedelta(hours=8)
    bj_now_str = beijing_now.strftime('%Y-%m-%d %H:%M:%S')

    daily_rets = (df_recent.iloc[-1] / close_data.iloc[-2]) - 1
    past_5d_rets = (close_data.iloc[-2] / close_data.iloc[-7]) - 1
    
    summary_list = []
    for ticker in tickers:
        d_r, p_r = daily_rets[ticker], past_5d_rets[ticker]
        last_price = df_recent[ticker].iloc[-1]
        
        # 转换行情时间
        raw_time = df_recent.index[-1]
        bj_data_time = (raw_time + timedelta(hours=8)).strftime('%H:%M:%S')

        # 状态描述逻辑 (针对国债做了优化)
        if d_r > 0.0001 and p_r < -0.0001: status = "⭐ 趋势反转 (向上)"
        elif d_r < -0.0001 and p_r > 0.0001: status = "⚠️ 趋势反转 (向下)"
        elif abs(d_r) > 0.02: status = "⚡ 剧烈波动"
        else: status = "📈 维持涨势" if d_r > 0 else "📉 维持跌势"
        
        summary_list.append({
            "代号": ticker,
            "资产名称": TICKER_TO_NAME[ticker],
            "最新价/收益点": last_price,
            "昨日涨跌": d_r,
            "前5日累计": p_r,
            "状态分析": status,
            "行情时间": bj_data_time
        })
    
    return close_data, pd.DataFrame(summary_list), bj_now_str

# --- 页面 UI 部分 ---
st.title("🛡️ 全球资产 & 美国国债监控看板")

try:
    close_data, summary_df, update_time = fetch_and_analyze()

    st.markdown(f"**系统同步时间 (北京):** `{update_time}` | 红色点=价格/收益率异常 | 黄色叉=波动异常")

    # 1. 总结表格
    st.subheader("📋 跨市场行情快报")
    selected_cat = st.selectbox("筛选板块：", ["全部显示"] + list(ASSETS.keys()))
    
    display_df = summary_df
    if selected_cat != "全部显示":
        target_tickers = list(ASSETS[selected_cat].keys())
        display_df = summary_df[summary_df['代号'].isin(target_tickers)]

    def color_surprises(val):
        if isinstance(val, float):
            return 'color: #00ff00' if val > 0 else 'color: #ff4b4b'
        return ''

    st.dataframe(
        display_df.style.format({
            "最新价/收益点": "{:.2f}",
            "昨日涨跌": "{:.2%}",
            "前5日累计": "{:.2%}"
        }).map(color_surprises, subset=["昨日涨跌", "前5日累计"]),
        width="stretch", 
        height="content",
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
            
            fig = make_subplots(
                rows=rows, cols=cols_per_row,
                subplot_titles=[f"<b>{t}</b><br>{cat_tickers[t]}" for t in valid_tickers],
                vertical_spacing=0.1, horizontal_spacing=0.04
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

                fig.add_trace(go.Scatter(x=data.index, y=data.values, name=ticker, line=dict(color='#00d4ff', width=1.5), showlegend=False), row=row, col=col)
                if not p_out.empty:
                    fig.add_trace(go.Scatter(x=p_out.index, y=p_out.values, mode='markers', marker=dict(color='red', size=4), showlegend=False), row=row, col=col)
                if not v_out.empty:
                    fig.add_trace(go.Scatter(x=v_out.index, y=v_out.values, mode='markers', marker=dict(color='yellow', symbol='x', size=4), showlegend=False), row=row, col=col)

            fig.update_layout(height=280 * rows, template="plotly_dark", margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, width="stretch", config={'responsive': True})

    # 自动刷新
    if auto_refresh:
        time.sleep(60)
        st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
