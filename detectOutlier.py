import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 基础配置
st.set_page_config(page_title="ETF 市场监控看板", layout="wide")

ETF_DETAILS = {
    'XLE': '能源', 'XLF': '金融', 'XLK': '科技', 'XLRE': '房地产', 
    'KBE': '银行股', 'KRE': '地区银行', 'ITB': '营建股', 'XHB': '家居装饰', 
    'XLI': '工业', 'XRT': '零售业', 'XLP': '必需消费', 'XLY': '可选消费', 
    'XLV': '医疗保健', 'XLU': '公用事业', 'IYT': '运输业', 'IBB': '生物科技', 'XSD': '半导体'
}

# --- 数据抓取与逻辑 ---
@st.cache_data(ttl=3600) # 缓存数据一小时
def fetch_and_analyze():
    tickers = list(ETF_DETAILS.keys())
    # 使用 progress=False 保持日志干净
    df = yf.download(tickers, period="1y", progress=False)
    close_data = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df[['Close']]
    
    # 填充空值防止计算报错
    close_data = close_data.ffill().bfill()
    
    daily_rets = (close_data.iloc[-1] / close_data.iloc[-2]) - 1
    past_5d_rets = (close_data.iloc[-2] / close_data.iloc[-7]) - 1
    
    summary_list = []
    for ticker in tickers:
        d_r, p_r = daily_rets[ticker], past_5d_rets[ticker]
        
        # 状态描述逻辑更新
        if d_r > 0 and p_r < 0: status = "⭐ 由跌转涨"
        elif d_r < 0 and p_r > 0: status = "⚠️ 涨势熄火"
        elif d_r > 0.01 and p_r > 0.02: status = "🔥 强势连涨"
        elif d_r < -0.01 and p_r < -0.02: status = "❄️ 跌势加剧"
        else: status = "📈 维持涨势" if d_r > 0 else "📉 维持跌势"
        
        summary_list.append({
            "代号": ticker,
            "名称": ETF_DETAILS[ticker],
            "昨日涨跌": d_r,
            "前5日累计": p_r,
            "状态分析": status
        })
    
    return close_data, pd.DataFrame(summary_list)

# --- 页面 UI 部分 ---
st.title("📊 ETF 市场趋势监控看板")
st.markdown(f"**数据截至日期:** `{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}` | 提示：红点=价格极端，黄叉=波动极端")

try:
    close_data, summary_df = fetch_and_analyze()

    # 2. 显示总结表格 (修复了 .map 报错问题)
    st.subheader("🚀 市场角色切换与涨跌对比总结")
    
    def color_surprises(val):
        if isinstance(val, float):
            # 采用直观颜色：涨红跌绿
            color = '#ff4b4b' if val < 0 else '#00ff00'
            return f'color: {color}'
        return ''

    # 注意这里：.applymap 已改为 .map
    st.dataframe(
        summary_df.style.format({
            "昨日涨跌": "{:.2%}",
            "前5日累计": "{:.2%}"
        }).map(color_surprises, subset=["昨日涨跌", "前5日累计"]),
        width="stretch", 
        height=400
    )

    # 3. 显示 ETF 交互图表 (每行4个)
    st.divider()
    st.subheader("📈 详细板块走势图")
    
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
        
        # 异常算法
        z = (data - data.rolling(20).mean()) / data.rolling(20).std()
        p_out = data[np.abs(z) > 2.5]
        rets = data.pct_change()
        iqr = rets.quantile(0.75) - rets.quantile(0.25)
        v_out = data.loc[rets[(rets > rets.quantile(0.75) + 1.5*iqr) | (rets < rets.quantile(0.25) - 1.5*iqr)].index]

        # 绘线
        fig.add_trace(go.Scatter(x=data.index, y=data.values, name=ticker, line=dict(color='#00d4ff', width=1.2), showlegend=False), row=row, col=col)
        
        if not p_out.empty:
            fig.add_trace(go.Scatter(x=p_out.index, y=p_out.values, mode='markers', marker=dict(color='red', size=4), showlegend=False, name="价格异常"), row=row, col=col)
        if not v_out.empty:
            fig.add_trace(go.Scatter(x=v_out.index, y=v_out.values, mode='markers', marker=dict(color='yellow', symbol='x', size=4), showlegend=False, name="波动异常"), row=row, col=col)

    # 适配最新 width 语法
    fig.update_layout(height=1200, template="plotly_dark", margin=dict(l=10, r=10, t=60, b=10))
    st.plotly_chart(fig, width="stretch", config={'responsive': True})

except Exception as e:
    st.error(f"分析出错: {e}")
