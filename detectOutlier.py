import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# 1. 基础配置
st.set_page_config(page_title="ETF 市场监控看板", layout="wide")

ETF_DETAILS = {
    'XLE': '能源', 'XLF': '金融', 'XLK': '科技', 'XLRE': '房地产', 
    'KBE': '银行股', 'KRE': '地区银行', 'ITB': '营建股', 'XHB': '家居装饰', 
    'XLI': '工业', 'XRT': '零售业', 'XLP': '必需消费', 'XLY': '可选消费', 
    'XLV': '医疗保健', 'XLU': '公用事业', 'IYT': '运输业', 'IBB': '生物科技', 'XSD': '半导体'
}

# --- 侧边栏控制 ---
with st.sidebar:
    st.header("系统设置")
    auto_refresh = st.checkbox("开启自动刷新 (60秒)", value=True)

# --- 数据抓取与逻辑 ---
def fetch_and_analyze():
    tickers = list(ETF_DETAILS.keys())
    
    # 获取历史数据用于绘图和计算前5日累计
    df_hist = yf.download(tickers, period="1y", progress=False)
    close_data = df_hist['Close'].ffill().bfill()
    
    # 获取最新分钟级数据用于校准“最新价”和“行情时间”
    # 使用 period="1d", interval="1m" 抓取此时此刻的变动
    df_recent = yf.download(tickers, period="1d", interval="1m", progress=False)['Close']
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
        
        # 获取该行情点的时间并转为北京时间
        raw_time = df_recent.index[-1]
        bj_data_time = (raw_time + timedelta(hours=8)).strftime('%H:%M:%S')

        # 状态描述逻辑
        if d_r > 0 and p_r < 0: status = "⭐ 由跌转涨"
        elif d_r < 0 and p_r > 0: status = "⚠️ 涨势熄火"
        elif d_r > 0.01 and p_r > 0.02: status = "🔥 强势连涨"
        elif d_r < -0.01 and p_r < -0.02: status = "❄️ 跌势加剧"
        else: status = "📈 维持涨势" if d_r > 0 else "📉 维持跌势"
        
        summary_list.append({
            "代号": ticker,
            "名称": ETF_DETAILS[ticker],
            "最新价": last_price,
            "昨日涨跌": d_r,
            "前5日累计": p_r,
            "状态分析": status,
            "行情时间": bj_data_time
        })
    
    return close_data, pd.DataFrame(summary_list), bj_now_str

# --- 页面 UI 部分 ---
st.title("📊 ETF 市场趋势监控看板 (北京时间校准版)")

try:
    close_data, summary_df, update_time = fetch_and_analyze()

    st.markdown(f"**系统同步时间 (北京):** `{update_time}` | 提示：红点=价格极端，黄叉=波动极端")

    # 2. 显示总结表格
    st.subheader("🚀 市场角色切换与涨跌对比总结")
    
    def color_surprises(val):
        if isinstance(val, float):
            color = '#ff4b4b' if val < 0 else '#00ff00'
            return f'color: {color}'
        return ''

    st.dataframe(
        summary_df.style.format({
            "最新价": "{:.2f}",
            "昨日涨跌": "{:.2%}",
            "前5日累计": "{:.2%}"
        }).map(color_surprises, subset=["昨日涨跌", "前5日累计"]),
        width="stretch", 
        height="content",
        hide_index=True
    )

    # 3. 显示 ETF 交互图表
    st.divider()
    st.subheader("📈 详细板块走势图 (历史数据)")
    
    tickers = list(ETF_DETAILS.keys())
    cols_per_row = 4
    rows = (len(tickers) + cols_per_row - 1) // cols_per_row
    
    fig = make_subplots(
        rows=rows, cols=cols_per_row,
        subplot_titles=[f"<b>{t}</b><br>{ETF_DETAILS[t]}" for t in tickers],
        vertical_spacing=0.06,
        horizontal_spacing=0.03
    )

    for i, ticker in enumerate(tickers):
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

    fig.update_layout(height=1200, template="plotly_dark", margin=dict(l=10, r=10, t=60, b=10))
    st.plotly_chart(fig, width="stretch", config={'responsive': True})

    # 自动刷新逻辑
    if auto_refresh:
        time.sleep(60)
        st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
