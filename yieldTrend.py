import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import time

# 1. 资产配置：按国家和期限双向索引
# 这里不仅保留了国家分类，还增加了期限（Tenor）的标签
ASSETS = {
    "美国 (USA)": {
        "^IRX": ("3月期", "Short"), "^FVX": ("5年期", "5Y"), "^TNX": ("10年期", "10Y"), "^TYX": ("30年期", "30Y")
    },
    "英国 (UK)": {
        "^GUKG2": ("2年期", "2Y"), "^GUKG5": ("5年期", "5Y"), "^GUKG10": ("10年期", "10Y"), "^GUKG30": ("30年期", "30Y")
    },
    "德国 (Germany)": {
        "^GDBR2": ("2年期", "2Y"), "^GDBR5": ("5年期", "5Y"), "^GDBR10": ("10年期", "10Y"), "^GDBR30": ("30年期", "30Y")
    },
    "日本 (Japan)": {
        "^GJGB2": ("2年期", "2Y"), "^GJGB5": ("5年期", "5Y"), "^GJGB10": ("10年期", "10Y"), "^GJGB30": ("30年期", "30Y")
    },
    "加拿大 (Canada)": {
        "^GCAN2Y": ("2年期", "2Y"), "^GCAN5Y": ("5年期", "5Y"), "^GCAN10": ("10年期", "10Y"), "^GCAN30": ("30年期", "30Y")
    },
    "澳大利亚 (Australia)": {
        "^GAUB2": ("2年期", "2Y"), "^GAUB5": ("5年期", "5Y"), "^GAUB10": ("10年期", "10Y"), "^GAUB30": ("30年期", "30Y")
    }
}

# 辅助映射
TICKER_INFO = {}
for country, tickers in ASSETS.items():
    for symbol, (name, tenor) in tickers.items():
        TICKER_INFO[symbol] = {"country": country, "name": name, "tenor": tenor}

st.set_page_config(page_title="全球国债横向监控看板", layout="wide")

@st.cache_data(ttl=600)
def fetch_global_yields():
    tickers = list(TICKER_INFO.keys())
    # 抓取数据
    df_hist = yf.download(tickers, period="1y", progress=False)
    close_data = df_hist['Close'] if isinstance(df_hist.columns, pd.MultiIndex) else df_hist[['Close']]
    
    # 强力补洞
    close_data = close_data.ffill().bfill()
    
    # 实时校准
    df_recent = yf.download(tickers, period="2d", interval="1m", progress=False)['Close']
    df_recent = df_recent.ffill().bfill()

    beijing_now = datetime.utcnow() + timedelta(hours=8)
    bj_now_str = beijing_now.strftime('%Y-%m-%d %H:%M:%S')

    summary_list = []
    for ticker in tickers:
        if ticker not in close_data.columns: continue
        
        info = TICKER_INFO[ticker]
        last_val = df_recent[ticker].iloc[-1]
        prev_close = close_data[ticker].iloc[-2]
        base_5d_price = close_data[ticker].iloc[-7]

        d_r = (last_val / prev_close) - 1
        p_r = (prev_close / base_5d_price) - 1
        
        raw_time = df_recent.index[-1]
        bj_data_time = (raw_time + timedelta(hours=8)).strftime('%H:%M:%S')

        if d_r > 0.005 and p_r < -0.005: status = "⭐ 触底反弹"
        elif d_r < -0.005 and p_r > 0.005: status = "⚠️ 冲高回落"
        elif abs(d_r) > 0.03: status = "⚡ 大幅波动"
        else: status = "📈 收益率上扬" if d_r > 0 else "📉 收益率走低"
        
        summary_list.append({
            "国家": info["country"], "代码": ticker, "期限": info["name"], "Tenor": info["tenor"],
            "当前收益率": last_val, "今日变动": d_r, "过去5日": p_r, 
            "状态分析": status, "更新时间": bj_data_time
        })
    return close_data, pd.DataFrame(summary_list), bj_now_str

# --- UI 展示 ---
st.title("🏛️ 全球收益率横向比较看板")

try:
    close_data, df_all, update_time = fetch_global_yields()
    
    # --- 新增：横向比较筛选器 ---
    st.subheader("📊 期限横向大比武 (相同期限，不同国家对比)")
    all_tenors = ["2Y", "5Y", "10Y", "30Y"]
    selected_tenor = st.select_slider("请滑动选择要比较的期限：", options=all_tenors, value="10Y")
    
    # 过滤出该期限的所有国家数据
    comp_df = df_all[df_all['Tenor'] == selected_tenor].sort_values("当前收益率", ascending=False)
    
    col_table, col_chart = st.columns([0.6, 0.4])
    
    with col_table:
        def color_rets(val):
            return 'color: #00ff00' if isinstance(val, float) and val > 0 else 'color: #ff4b4b' if isinstance(val, float) and val < 0 else ''
        
        st.dataframe(
            comp_df[["国家", "当前收益率", "今日变动", "过去5日", "状态分析"]].style.format({
                "当前收益率": "{:.3f}", "今日变动": "{:.2%}", "过去5日": "{:.2%}"
            }).map(color_rets, subset=["今日变动", "过去5日"]),
            width="stretch", height="content", hide_index=True
        )
    
    with col_chart:
        # 绘制简单的横向对比柱状图
        fig_bar = px.bar(comp_df, x="当前收益率", y="国家", orientation='h', 
                         title=f"全球 {selected_tenor} 收益率水平对比",
                         text_auto='.3f', color="当前收益率",
                         color_continuous_scale="RdYlGn_r") # 收益率越高颜色越深
        fig_bar.update_layout(template="plotly_dark", height=300, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_bar, use_container_width=True)

    # --- 原有的国家分类看板 ---
    st.divider()
    st.subheader(f"🏠 国家分类监控 (同步时间: {update_time})")
    tabs = st.tabs(list(ASSETS.keys()))
    for tab, (country, tickers_dict) in zip(tabs, ASSETS.items()):
        with tab:
            valid_tickers = [t for t in tickers_dict.keys() if t in close_data.columns]
            cols = st.columns(4)
            for i, ticker in enumerate(valid_tickers):
                with cols[i % 4]:
                    data = close_data[ticker].dropna()
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=data.index, y=data.values, line=dict(color='#ffcc00', width=1.5)))
                    fig.update_layout(
                        title=f"<b>{ticker}</b> ({tickers_dict[ticker][0]})",
                        height=230, template="plotly_dark", showlegend=False,
                        margin=dict(l=10, r=10, t=40, b=10),
                        xaxis=dict(tickfont=dict(size=8)), yaxis=dict(tickfont=dict(size=8))
                    )
                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # 自动刷新
    if st.sidebar.checkbox("开启自动刷新 (60秒)", value=True):
        time.sleep(60)
        st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
