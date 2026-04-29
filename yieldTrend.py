import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
import time

# --- 1. 资产配置 ---
ETFS = {'XLK': '科技', 'XLE': '能源', 'XLF': '金融', 'XLRE': '房地产', 'KBE': '银行股', 'KRE': '地区银行', 'ITB': '营建股', 'XHB': '家居装饰', 'XLI': '工业', 'XRT': '零售业', 'XLP': '必需消费', 'XLY': '可选消费', 'XLV': '医疗保健', 'XLU': '公用事业', 'IYT': '运输业', 'IBB': '生物科技', 'XSD': '半导体'}
COMMODITIES = {"能源": {"USO": "WTI原油", "BNO": "布伦特原油", "NG=F": "天然气主力"}, "金属": {"GLD": "黄金", "SLV": "白银", "CPER": "铜ETF", "PICK": "金属采矿", "DBB": "铝铜锌"}, "农产品": {"SOYB": "大豆", "CORN": "玉米", "WEAT": "小麦", "SB=F": "原糖", "KC=F": "咖啡"}}
BONDS = {"美国": {"SHY": ("1-3Y短债", "2Y"), "IEF": ("7-10Y中债", "10Y"), "TLT": ("20Y+长债", "30Y")}, "英国": {"IGLT.L": ("国债", "10Y")}, "德国": {"BUNT.DE": ("国债", "10Y")}, "日本": {"2556.T": ("JGB中债", "10Y")}}

st.set_page_config(page_title="全球宏观色谱工作站", layout="wide")

# --- 2. 核心逻辑：Regime 计算 ---
def get_regime(ds, d2, d10):
    if ds > 0: # Steepening
        if d2 < 0 and d10 < 0: return ("Bull Steepener", "#00FF00")
        if d2 > 0 and d10 > 0: return ("Bear Steepener", "#FF8C00")
        return ("Steepener Twist", "#FF00FF")
    else: # Flattening
        if d2 < 0 and d10 < 0: return ("Bull Flattener", "#00FFFF")
        if d2 > 0 and d10 > 0: return ("Bear Flattener", "#FF0000")
        return ("Flattener Twist", "#FFFF00")

@st.cache_data(ttl=600)
def fetch_data():
    # A. 读取 GitHub 里的“数据库”文件
    try:
        h_df = pd.read_csv("history_yields.csv", index_col='Date', parse_dates=True)
        h_df = h_df.sort_index()
    except:
        st.error("请先上传 history_yields.csv 到仓库！")
        return None, None, None

    # B. 抓取实时点 (2Y 和 10Y) 用于缝合
    live = yf.download(["^ZT=F", "^TNX"], period="2d", interval="15m", progress=False)['Close'].ffill()
    
    # C. 缝合数据并计算色谱
    # 注意：这里我们把 2Y 和 10Y 从你的数据库列名映射出来
    curve_df = pd.DataFrame({
        '2Y': h_df['USGG2YR Index'], 
        '10Y': h_df['USGG10YR Index']
    })
    
    # 加上今天最新的那一口价
    today = pd.Timestamp(datetime.now().date())
    curve_df.loc[today] = [live["^ZT=F"].iloc[-1], live["^TNX"].iloc[-1]]
    curve_df = curve_df.ffill()
    
    curve_df['Spread'] = (curve_df['10Y'] - curve_df['2Y']) * 100
    curve_df['ds'], curve_df['d2'], curve_df['d10'] = curve_df['Spread'].diff(), curve_df['2Y'].diff(), curve_df['10Y'].diff()
    
    res = curve_df.apply(lambda r: get_regime(r['ds'], r['d2'], r['d10']), axis=1)
    curve_df['Regime'], curve_df['Color'] = [x[0] for x in res], [x[1] for x in res]
    
    # D. 其他资产汇总 (略，逻辑同前)
    bj_now = datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S')
    return curve_df, bj_now

# --- 3. UI 渲染 ---
try:
    hist_bond, update_time = fetch_data()
    if hist_bond is not None:
        st.title("🌐 全球宏观色谱分析")
        st.write(f"最后同步: `{update_time}`")
        
        tabs = st.tabs(["🧠 跨市场色谱", "📊 详细行情"])
        
        with tabs[0]:
            cur = hist_bond.iloc[-1]
            st.markdown(f"### 当前状态: <span style='color:{cur['Color']}'>{cur['Regime']}</span>", unsafe_allow_html=True)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=hist_bond.index, y=hist_bond['Spread'], marker_color=hist_bond['Color'], opacity=0.8))
            fig.add_trace(go.Scatter(x=hist_bond.index, y=hist_bond['Spread'], line=dict(color='white', width=1)))
            fig.update_layout(height=500, template="plotly_dark", yaxis_title="2s10s Spread (Bps)")
            st.plotly_chart(fig, width="stretch")
            st.write("🟢牛陡 | 🟠熊陡 | 💗扭曲陡 | 🔵牛平 | 🔴熊平 | 🟡扭曲平")

    if st.sidebar.checkbox("自动刷新", True):
        time.sleep(60); st.rerun()
except Exception as e:
    st.error(f"初始化中... {e}")
