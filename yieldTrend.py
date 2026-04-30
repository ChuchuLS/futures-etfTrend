import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

# --- 1. 配置清单 ---
SPREAD_PAIRS = [
    ("USGG10YR Index", "USGG3M Index", "3M vs 10Y (衰退预警线)"),
    ("USGG10YR Index", "USGG2YR Index", "2Y vs 10Y (经典基准线)"),
    ("USGG30YR Index", "USGG5YR Index", "5Y vs 30Y (长期政策线)"),
    ("USGG30YR Index", "USGG2YR Index", "2Y vs 30Y (全曲线斜率)"),
    ("USGG10YR Index", "USGG5YR Index", "5Y vs 10Y (中段结构线)")
]

# 雅虎与本地 CSV 列名的映射
YF_MAP = {
    "^IRX": "USGG3M Index",
    "^ZT=F": "USGG2YR Index",
    "^FVX": "USGG5YR Index",
    "^TNX": "USGG10YR Index",
    "^TYX": "USGG30YR Index"
}

st.set_page_config(page_title="全球宏观色谱矩阵-智能补全版", layout="wide")

# --- 2. 核心算法 ---
def calc_regime(df, long_col, short_col):
    df = df[[long_col, short_col]].copy()
    df['Spread'] = (df[long_col] - df[short_col]) * 100
    df['d_s'] = df[short_col].diff()
    df['d_l'] = df[long_col].diff()
    df['d_spread'] = df['Spread'].diff()

    def get_color(row):
        ds, ds_s, ds_l = row['d_spread'], row['d_s'], row['d_l']
        if pd.isna(ds): return (None, None)
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

# --- 3. 智能补全引擎 (修复时区比较报错) ---
@st.cache_data(ttl=3600)
def fetch_and_fill_data():
    try:
        h_df = pd.read_csv("history_yields.csv", index_col='Date', parse_dates=True)
        h_df = h_df.sort_index()
        # 强制把 CSV 的索引转为不带时区的格式
        if h_df.index.tz is not None:
            h_df.index = h_df.index.tz_localize(None)
        last_date_in_csv = h_df.index[-1]
    except Exception as e:
        st.error(f"本地数据库读取失败: {e}")
        return None

    # 【关键修复】：获取不带时区的“今天”
    today_naive = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 如果 CSV 还没更新到今天，尝试去抓取
    if last_date_in_csv < today_naive:
        try:
            tickers = list(YF_MAP.keys())
            start_fetch = last_date_in_csv + timedelta(days=1)
            # 抓取实时点位
            new_data_raw = yf.download(tickers, start=start_fetch, progress=False)['Close']
            
            if not new_data_raw.empty:
                if new_data_raw.index.tz is not None:
                    new_data_raw.index = new_data_raw.index.tz_localize(None)
                
                new_data_renamed = new_data_raw.rename(columns=YF_MAP)
                combined_df = pd.concat([h_df, new_data_renamed])
                combined_df = combined_df[~combined_df.index.duplicated(keep='last')].sort_index()
                combined_df = combined_df.ffill()
                return combined_df
        except Exception as yf_err:
            st.warning(f"实时行情补全失败（可能是雅虎限制），目前显示历史缓存数据。")
            return h_df
    
    return h_df

# --- 4. UI 渲染 ---
st.title("🏛️ 全期限收益率曲线色谱矩阵 (智能补全版)")

try:
    df_full = fetch_and_fill_data()
    
    if df_full is not None:
        # 获取北京时间显示
        bj_time = (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
        st.write(f"**数据更新至:** `{df_full.index[-1].strftime('%Y-%m-%d')}` | **同步时间 (北京):** `{bj_time}`")
        st.write("🟢牛陡 | 🟠熊陡 | 💗扭曲陡 | 🔵牛平 | 🔴熊平 | 🟡扭曲平")
        
        for long_end, short_end, title in SPREAD_PAIRS:
            # 确保列名在数据中存在
            if long_end in df_full.columns and short_end in df_full.columns:
                with st.container():
                    st.subheader(f"📊 {title}")
                    
                    # 计算该对的色谱
                    regime_df = calc_regime(df_full, long_end, short_end)
                    
                    fig = go.Figure()
                    # 1. 颜色背景柱
                    fig.add_trace(go.Bar(
                        x=regime_df.index, y=regime_df['Spread'],
                        marker_color=regime_df['Color'],
                        marker_line_width=0, opacity=0.7,
                        customdata=regime_df['Regime'],
                        hovertemplate="日期: %{x}<br>利差: %{y:.1f} bps<br>状态: %{customdata}<extra></extra>"
                    ))
                    # 2. 利差连线
                    fig.add_trace(go.Scatter(
                        x=regime_df.index, y=regime_df['Spread'],
                        line=dict(color='white', width=1.5),
                        hoverinfo='skip'
                    ))
                    
                    fig.update_layout(
                        height=550, template="plotly_dark", showlegend=False,
                        margin=dict(l=10, r=10, t=30, b=30),
                        yaxis=dict(title="Spread (Bps)", zeroline=True, zerolinecolor='gray', autorange=True, fixedrange=False),
                        xaxis=dict(fixedrange=False, range=[regime_df.index[0], regime_df.index[-1]]),
                        uirevision='constant'
                    )
                    st.plotly_chart(fig, width="stretch", config={'responsive': True})
                    st.divider()

except Exception as e:
    st.error(f"分析出错: {e}")
