import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# 1. 资产配置：全球 6 大经济体国债收益率主力代码
# ^ 开头的代码在 Yahoo Finance 中代表收益率百分比
ASSETS = {
    "美国 (USA)": {
        "^IRX": "13周/3月期", "^FVX": "5年期", "^TNX": "10年期", "^TYX": "30年期"
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

TICKER_TO_NAME = {ticker: name for cat in ASSETS.values() for ticker, name in cat.items()}

# 设置页面布局
st.set_page_config(page_title="全球国债收益率监控看板", layout="wide")

# --- 侧边栏控制 ---
with st.sidebar:
    st.header("系统设置")
    auto_refresh = st.checkbox("开启自动刷新 (60秒)", value=True)
    st.info("💡 收益率说明：\n数据通常显示为基点(BP)或百分比。例如 4.25 代表 4.25%。")

# --- 数据抓取与逻辑 ---
@st.cache_data(ttl=600)
def fetch_and_analyze():
    tickers = list(TICKER_TO_NAME.keys())
    # 抓取历史数据（1年）
    df_hist = yf.download(tickers, period="1y", progress=False)
    close_data = df_hist['Close'] if isinstance(df_hist.columns, pd.MultiIndex) else df_hist[['Close']]
    
    # 抓取实时分钟数据（校准当日波动）
    df_recent = yf.download(tickers, period="1d", interval="1m", progress=False)['Close']
    
    # 填充缺失值
    close_data = close_data.ffill().bfill()
    df_recent = df_recent.ffill()

    # 统一北京时间
    beijing_now = datetime.utcnow() + timedelta(hours=8)
    bj_now_str = beijing_now.strftime('%Y-%m-%d %H:%M:%S')

    # 计算涨跌表现（收益率的变动）
    daily_rets = (df_recent.iloc[-1] / close_data.iloc[-2]) - 1
    past_5d_rets = (close_data.iloc[-2] / close_data.iloc[-7]) - 1
    
    summary_list = []
    for ticker in tickers:
        if ticker not in close_data.columns: continue
        
        d_r = daily_rets[ticker]
        p_r = past_5d_rets[ticker]
        last_val = df_recent[ticker].iloc[-1]
        raw_time = df_recent.index[-1]
        bj_data_time = (raw_time + timedelta(hours=8)).strftime('%H:%M:%S')

        # 状态描述逻辑
        if d_r > 0.005 and p_r < -0.005: status = "⭐ 收益率触底反弹"
        elif d_r < -0.005 and p_r > 0.005: status = "⚠️ 收益率冲高回落"
        elif abs(d_r) > 0.03: status = "⚡ 收益率大幅波动"
        else: status = "📈 收益率上行" if d_r > 0 else "📉 收益率下行"
        
        summary_list.append({
            "代码": ticker, 
            "期限名称": TICKER_TO_NAME[ticker],
            "当前收益率": last_val, 
            "今日变动": d_r,
            "过去5日变动": p_r, 
            "状态分析": status, 
            "更新时间": bj_data_time
        })
    return close_data, pd.DataFrame(summary_list), bj_now_str

# --- UI 展示部分 ---
st.title("🏛️ 全球主权国家收益率 (Bonds Yield) 监控")

try:
    close_data, summary_df, update_time = fetch_and_analyze()
    st.write(f"**最后同步 (北京):** `{update_time}` | 手机端请横屏或滑动查看表格")

    # 1. 总结表格
    st.dataframe(
        summary_df.style.format({"当前收益率": "{:.3f}", "今日变动": "{:.2%}", "过去5日变动": "{:.2%}"})
        .map(lambda x: 'color: #00ff00' if isinstance(x, float) and x > 0 else 'color: #ff4b4b' if isinstance(x, float) and x < 0 else '', 
             subset=["今日变动", "过去5日变动"]),
        width="stretch", height=450, hide_index=True
    )

    # 2. 分类图表展示
    st.divider()
    tabs = st.tabs(list(ASSETS.keys()))
    
    for tab, (country, tickers_dict) in zip(tabs, ASSETS.items()):
        with tab:
            cols = st.columns(4) 
            valid_tickers = [t for t in tickers_dict.keys() if t in close_data.columns]
            
            for i, ticker in enumerate(valid_tickers):
                with cols[i % 4]:
                    data = close_data[ticker].dropna()
                    
                    # 统计异常检测（收益率暴涨暴跌检测）
                    z = (data - data.rolling(20).mean()) / data.rolling(20).std()
                    p_out = data[np.abs(z) > 2.5]
                    rets = data.pct_change()
                    iqr = rets.quantile(0.75) - rets.quantile(0.25)
                    v_out = data.loc[rets[(rets > rets.quantile(0.75) + 1.5*iqr) | 
                                          (rets < rets.quantile(0.25) - 1.5*iqr)].index]

                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=data.index, y=data.values, name=ticker, 
                                           line=dict(color='#ffcc00', width=1.5))) # 使用金色线代表债券
                    
                    if not p_out.empty:
                        fig.add_trace(go.Scatter(x=p_out.index, y=p_out.values, mode='markers', 
                                               marker=dict(color='red', size=6)))
                    if not v_out.empty:
                        fig.add_trace(go.Scatter(x=v_out.index, y=v_out.values, mode='markers', 
                                               marker=dict(color='cyan', symbol='x', size=6)))

                    fig.update_layout(
                        title=dict(text=f"<b>{ticker}</b><br>{tickers_dict[ticker]}", font=dict(size=14)),
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
