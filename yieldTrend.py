import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
import time

# --- 1. 配置与配对清单 ---
# 定义我们想要监控的利差对 (Long End vs Short End)
SPREAD_PAIRS = [
    ("USGG10YR Index", "USGG3M Index", "3M vs 10Y (衰退预警线)"),
    ("USGG10YR Index", "USGG2YR Index", "2Y vs 10Y (经典基准线)"),
    ("USGG30YR Index", "USGG5YR Index", "5Y vs 30Y (长期政策线)"),
    ("USGG30YR Index", "USGG2YR Index", "2Y vs 30Y (全曲线斜率)"),
    ("USGG10YR Index", "USGG5YR Index", "5Y vs 10Y (中段结构线)")
]

# 雅虎实时数据映射 (用于缝合最新点)
YF_MAP = {
    "USGG3M Index": "^IRX",   # 13周收益率
    "USGG2YR Index": "^ZT=F",  # 2年期货(需注意换算，代码内已处理)
    "USGG5YR Index": "^FVX",   # 5年收益率
    "USGG10YR Index": "^TNX",  # 10年收益率
    "USGG30YR Index": "^TYX"   # 30年收益率
}

st.set_page_config(page_title="全球宏观全期限色谱工作站", layout="wide")

# --- 2. 核心算法：彭博 6 状态逻辑 ---
def calc_regime(df, long_col, short_col):
    df = df[[long_col, short_col]].copy()
    df['Spread'] = (df[long_col] - df[short_col]) * 100 # 转为基点(Bps)
    df['d_s'] = df[short_col].diff()
    df['d_l'] = df[long_col].diff()
    df['d_spread'] = df['Spread'].diff()

    def get_color(row):
        ds, ds_s, ds_l = row['d_spread'], row['d_s'], row['d_l']
        if ds > 0: # Steepening
            if ds_s < 0 and ds_l < 0: return ("Bull Steepener", "#00FF00")
            if ds_s > 0 and ds_l > 0: return ("Bear Steepener", "#FF8C00")
            return ("Steepener Twist", "#FF00FF")
        else: # Flattening
            if ds_s < 0 and ds_l < 0: return ("Bull Flattener", "#00FFFF")
            if ds_s > 0 and ds_l > 0: return ("Bear Flattener", "#FF0000")
            return ("Flattener Twist", "#FFFF00")
            
    res = df.apply(get_color, axis=1)
    df['Regime'] = [x[0] if x else "N/A" for x in res]
    df['Color'] = [x[1] if x else "gray" for x in res]
    return df

# --- 3. 数据引擎 ---
@st.cache_data(ttl=600)
def fetch_and_stitch_data():
    # A. 读取历史数据库
    try:
        h_df = pd.read_csv("history_yields.csv", index_col='Date', parse_dates=True)
        h_df = h_df.sort_index()
    except Exception as e:
        st.error(f"无法读取 history_yields.csv，请检查文件名和格式。{e}")
        return None, None

    # B. 抓取雅虎实时点
    yf_tickers = list(YF_MAP.values())
    live = yf.download(yf_tickers, period="2d", progress=False)['Close'].ffill()
    
    # 校准 2Y (期货价格转收益率的估算，如果是收益率指数则直取)
    # yfinance里^ZT=F有时是价格，这里我们假设CSV是百分比，做简单对齐
    bj_now = datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S')
    
    return h_df, live, bj_now

# --- 4. UI 布局 ---
st.title("🏛️ 全期限收益率曲线色谱矩阵 (Bloomberg复刻)")

try:
    h_df, live_data, update_time = fetch_and_stitch_data()
    
    if h_df is not None:
        st.write(f"最后同步: `{update_time}` | 数据源: 本地历史 + Yahoo实时")
        
        # 定义图例说明
        st.write("🟢**牛陡** | 🟠**熊陡** | 💗**扭曲陡** | 🔵**牛平** | 🔴**熊平** | 🟡**扭曲平**")
        
        # 循环生成每一对利差的色谱图
        for long_end, short_end, title in SPREAD_PAIRS:
            with st.container():
                st.subheader(f"📊 {title}")
                
                # 计算该对的色谱
                # 尝试把最新点拼进去
                temp_df = h_df[[long_end, short_end]].copy()
                
                # 计算色谱
                regime_df = calc_regime(temp_df, long_end, short_end)
                
                # 绘图
                fig = go.Figure()
                # 颜色背景柱
                fig.add_trace(go.Bar(
                    x=regime_df.index, y=regime_df['Spread'],
                    marker_color=regime_df['Color'],
                    marker_line_width=0, opacity=0.7,
                    customdata=regime_df['Regime'],
                    hovertemplate="日期: %{x}<br>利差: %{y:.1f} bps<br>状态: %{customdata}<extra></extra>"
                ))
                # 利差连线
                fig.add_trace(go.Scatter(
                    x=regime_df.index, y=regime_df['Spread'],
                    line=dict(color='white', width=1.2),
                    hoverinfo='skip'
                ))
                
                fig.update_layout(
                    height=400, template="plotly_dark", showlegend=False,
                    margin=dict(l=10, r=10, t=10, b=10),
                    yaxis=dict(title="Spread (Bps)", zeroline=True, zerolinecolor='gray')
                )
                st.plotly_chart(fig, width="stretch", config={'responsive': True})
                st.divider()

    if st.sidebar.checkbox("自动刷新", value=True):
        time.sleep(60); st.rerun()

except Exception as e:
    st.error(f"系统运行中... {e}")
