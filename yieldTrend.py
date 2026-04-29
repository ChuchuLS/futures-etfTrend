import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
import time

# --- 1. 配置清单 ---
ETFS = {
    'XLK': '科技', 'XLE': '能源', 'XLF': '金融', 'XLRE': '房地产', 'KBE': '银行股', 
    'KRE': '地区银行', 'ITB': '营建股', 'XHB': '家居装饰', 'XLI': '工业', 'XRT': '零售业', 
    'XLP': '必需消费', 'XLY': '可选消费', 'XLV': '医疗保健', 'XLU': '公用事业', 'IYT': '运输业', 
    'IBB': '生物科技', 'XSD': '半导体'
}
COMMODITIES = {
    "能源": {"USO": "WTI原油", "BNO": "布伦特原油", "NG=F": "天然气主力"},
    "金属": {"GLD": "黄金", "SLV": "白银", "CPER": "铜ETF", "PICK": "金属采矿", "DBB": "铝铜锌"},
    "农产品": {"SOYB": "大豆", "CORN": "玉米", "WEAT": "小麦", "SB=F": "原糖", "KC=F": "咖啡"}
}
BONDS = {
    "美国 (USA)": {"SHY": ("1-3Y短债", "2Y"), "IEF": ("7-10Y中债", "10Y"), "TLT": ("20Y+长债", "30Y")},
    "英国 (UK)": {"IGLT.L": ("英国国债", "10Y"), "VGOV.L": ("英国长债", "30Y")},
    "德国 (GER)": {"BUNT.DE": ("德国联邦债", "10Y"), "IS0L.DE": ("德国长债", "30Y")},
    "日本 (JPN)": {"2556.T": ("日本JGB中债", "10Y"), "2512.T": ("日本JGB长债", "30Y")},
    "澳洲 (AUS)": {"VAF.AX": ("澳洲综合债", "10Y")},
    "加拿大 (CAN)": {"VGV.TO": ("加拿大国债", "10Y"), "VLB.TO": ("加拿大长债", "30Y")}
}

st.set_page_config(page_title="全球宏观色谱工作站", layout="wide")

# --- 2. 核心数据引擎 ---
@st.cache_data(ttl=900)
def fetch_macro_data():
    # 扩大数据量到 5y 以覆盖完整周期
    curve_tickers = ["^TNX", "^FVX", "^ZT=F"]
    all_tickers = list(ETFS.keys()) + [t for cat in COMMODITIES.values() for t in cat.keys()] + [t for cat in BONDS.values() for t in cat.keys()] + curve_tickers
    
    try:
        # 下载 5 年数据
        df_raw = yf.download(all_tickers, period="5y", interval="1d", progress=False, threads=False)
        close_data = df_raw['Close'].ffill().bfill()
        # 分钟级实时校准
        df_rec = yf.download(all_tickers, period="2d", interval="15m", progress=False, threads=False)['Close'].ffill().bfill()
    except Exception as e:
        return None, None, None, None

    bj_now = datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S')

    # 计算色谱历史 - 使用更稳健的 5Y (^FVX) 作为曲线短端
    s_code = "^FVX" 
    hist_df = close_data[[s_code, "^TNX"]].copy()
    hist_df['Spread'] = (hist_df["^TNX"] - hist_df[s_code]) * 100 
    hist_df['d_s'] = hist_df[s_code].diff()
    hist_df['d_l'] = hist_df["^TNX"].diff()
    hist_df['d_spread'] = hist_df['Spread'].diff()

    def calc_regime(row):
        ds, ds_s, ds_l = row['d_spread'], row['d_s'], row['d_l']
        if ds > 0: 
            if ds_s < 0 and ds_l < 0: return ("Bull Steepener", "#00FF00")
            if ds_s > 0 and ds_l > 0: return ("Bear Steepener", "#FF8C00")
            return ("Steepener Twist", "#FF00FF")
        else:
            if ds_s < 0 and ds_l < 0: return ("Bull Flattener", "#00FFFF")
            if ds_s > 0 and ds_l > 0: return ("Bear Flattener", "#FF0000")
            return ("Flattener Twist", "#FFFF00")

    reg_res = hist_df.apply(calc_regime, axis=1)
    hist_df['Regime'] = [x[0] if x else "N/A" for x in reg_res]
    hist_df['Color'] = [x[1] if x else "gray" for x in reg_res]

    summary = []
    full_list = {**ETFS, **{t:n for c in COMMODITIES.values() for t,n in c.items()}, **{t:n[0] for c in BONDS.values() for t,n in c.items()}}
    for ticker, name in full_list.items():
        if ticker not in close_data.columns: continue
        last, prev, base5 = df_rec[ticker].iloc[-1], close_data[ticker].iloc[-2], close_data[ticker].iloc[-7]
        d_r, date_str = (last / prev) - 1, df_rec.index[-1].strftime('%m-%d')
        if abs(d_r) < 0.00001:
            for i in range(1, 10):
                tr = (close_data[ticker].iloc[-i] / close_data[ticker].iloc[-(i+1)]) - 1
                if abs(tr) > 0.00001: d_r, last, date_str = tr, close_data[ticker].iloc[-i], close_data.index[-i].strftime('%m-%d'); break
        
        summary.append({"代码": ticker, "名称": name, "最新价": last, "行情日期": date_str, "价格变动": d_r, "前5日累计": (prev/base5)-1,
                        "分类": "国债" if ticker in [t for c in BONDS.values() for t in c.keys()] else "其他"})

    return close_data, pd.DataFrame(summary), bj_now, hist_df

def render_table(df, h="content"):
    styler = df.style.format({"最新价": "{:.2f}", "价格变动": "{:.2%}", "前5日累计": "{:.2%}"})
    exist = df.columns.tolist()
    subset = [c for c in ["价格变动", "前5日累计"] if c in exist]
    if subset:
        styler = styler.map(lambda x: 'color: #00ff00' if isinstance(x,float) and x>0 else 'color: #ff4b4b' if isinstance(x,float) and x<0 else '', subset=subset)
    st.dataframe(styler, width="stretch", height=h, hide_index=True)

# --- 3. UI 主逻辑 ---
try:
    # 修复：统一函数名为 fetch_macro_data
    close_data, df_sum, update_time, hist_bond = fetch_macro_data()
    
    if df_sum is not None:
        st.title("🌐 全球宏观色谱分析工作站")
        st.write(f"最后同步 (北京): `{update_time}`")

        tabs = st.tabs(["📋 汇总", "🧠 跨市场色谱分析", "📊 ETF", "🛡️ 商品", "🏛️ 国债"])

        with tabs[1]:
            cur = hist_bond.iloc[-1]
            st.markdown(f"### 🛡️ 当前宏观状态: <span style='color:{cur['Color']}'>{cur['Regime']}</span>", unsafe_allow_html=True)
            
            fig = go.Figure()
            # 颜色背景
            fig.add_trace(go.Bar(x=hist_bond.index, y=hist_bond['Spread'], marker_color=hist_bond['Color'], marker_line_width=0, opacity=0.8, name="Regime", customdata=hist_bond['Regime'], hovertemplate="状态: %{customdata}<extra></extra>"))
            # 白色利差线
            fig.add_trace(go.Scatter(x=hist_bond.index, y=hist_bond['Spread'], line=dict(color='white', width=1.5), name="Spread", hoverinfo='skip'))

            fig.update_layout(height=450, template="plotly_dark", showlegend=False, margin=dict(l=10, r=10, t=30, b=10), 
                              yaxis=dict(title="Spread (Bps)", zeroline=True, zerolinecolor='gray'),
                              xaxis=dict(range=[hist_bond.index[0], hist_bond.index[-1]])) # 强制对齐 5 年时间轴
            st.plotly_chart(fig, width="stretch", config={'responsive': True})

            c = st.columns(6)
            c[0].markdown("🟢**牛陡**"); c[1].markdown("🟠**熊陡**"); c[2].markdown("💗**扭曲陡**"); c[3].markdown("🔵**牛平**"); c[4].markdown("🔴**熊平**"); c[5].markdown("🟡**扭曲平**")

        with tabs[0]: render_table(df_sum, h=600)
        
        with tabs[2]:
            render_table(df_sum[df_sum['分类']=="其他"])
            st.divider(); cols = st.columns(4)
            for i, t in enumerate(ETFS.keys()):
                with cols[i%4]:
                    data = close_data[t].dropna()
                    fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#00d4ff', width=1.5)))
                    fig.update_layout(title=f"<b>{t}</b>", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5))
                    st.plotly_chart(fig, width="stretch", config={'displayModeBar': False})

        with tabs[3]:
            render_table(df_sum[df_sum['分类'].str.contains("商品")])
            st.divider(); cols = st.columns(4); all_c = [t for cat in COMMODITIES.values() for t in cat.keys()]
            for i, t in enumerate(all_c):
                with cols[i%4]:
                    data = close_data[t].dropna()
                    fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ff9900', width=1.5)))
                    fig.update_layout(title=f"<b>{t}</b>", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5))
                    st.plotly_chart(fig, width="stretch", config={'displayModeBar': False})

        with tabs[4]:
            render_table(df_sum[df_sum['分类']=="国债"])
            st.divider(); b_tabs = st.tabs(list(BONDS.keys()))
            for b_tab, country in zip(b_tabs, BONDS.keys()):
                with b_tab:
                    cols = st.columns(4)
                    for i, t in enumerate(BONDS[country].keys()):
                        with cols[i%4]:
                            data = close_data[t].dropna()
                            fig = go.Figure(go.Scatter(x=data.index, y=data.values, line=dict(color='#ffcc00', width=1.5)))
                            fig.update_layout(title=f"<b>{t}</b>", height=180, template="plotly_dark", showlegend=False, margin=dict(l=5,r=5,t=30,b=5))
                            st.plotly_chart(fig, width="stretch", config={'displayModeBar': False})

        if st.sidebar.checkbox("自动刷新", value=True):
            time.sleep(60); st.rerun()

except Exception as e:
    st.error(f"分析出错: {e}")
