import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import sqlite3
from datetime import datetime
import io

# ==========================================
# 0. 資料庫初始化 (SQLite)
# ==========================================
def init_db():
    conn = sqlite3.connect('givegift_ads.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS campaigns (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, ad_type TEXT, budget REAL, audience TEXT, core_message TEXT, ai_proposal TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, created_at TEXT)''')
    conn.commit()
    conn.close()
init_db()

# ==========================================
# 1. 介面設定與系統人設
# ==========================================
st.set_page_config(page_title="Give Gift Boutique Ads Center", page_icon="📊", layout="wide")

SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告分析師。
請根據數據提供精簡、專業的診斷。必須包含：
1. 【健康分數】(0-100)
2. 【核心問題】點出最燒錢或不轉換的地方。
3. 【優化動作】具體教使用者在後台怎麼改。"""

# ==========================================
# 2. 側邊欄 (API 與 模型)
# ==========================================
st.sidebar.title("💐 Give Gift Boutique Ads")
api_key = st.sidebar.text_input("🔑 輸入 Gemini API Key:", type="password")
selected_model = st.sidebar.selectbox("🧠 AI 模型選擇:", ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-3.0-pro"])

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(selected_model, system_instruction=SYSTEM_PROMPT)
else:
    st.sidebar.warning("請先輸入 API Key")

st.sidebar.divider()
page = st.sidebar.radio("切換頁面：", ["📈 廣告看板", "💡 A/B 測試生成"])

# ==========================================
# 3. 核心數據處理函數 (針對尚禮坊報表優化)
# ==========================================
def extract_kpi_v2(df):
    kpi = {"cost": 0.0, "clicks": 0, "conversions": 0, "cols_found": {}}
    
    def clean_val(v):
        if pd.isna(v) or str(v).strip() in ['--', '']: return 0.0
        return float(str(v).replace('$', '').replace(',', '').replace('%', '').strip())

    # 1. 找出純數據行 (排除總計行)
    # 檢查第一欄或第二欄是否包含 '總計'
    mask = df.iloc[:, :2].apply(lambda x: x.astype(str).str.contains('總計|Total|總和')).any(axis=1)
    df_clean = df[~mask].copy()

    for col in df_clean.columns:
        c = str(col).strip()
        # A. 抓「費用」: 排除平均費用、每轉換費用
        if c == '費用' or (('費用' in c or 'Cost' in c) and not any(ex in c for ex in ['平均', '每', 'Avg', 'CPC'])):
            kpi['cost'] = df_clean[col].apply(clean_val).sum()
            kpi['cols_found']['cost'] = c
        # B. 抓「點擊次數」: 排除點擊率
        elif '點擊' in c and '率' not in c:
            kpi['clicks'] = int(df_clean[col].apply(clean_val).sum())
            kpi['cols_found']['clicks'] = c
        # C. 抓「轉換」: 排除價值、率、費用
        elif '轉換' in c and not any(ex in c for ex in ['價值', '率', '費用', 'Value', 'Rate']):
            kpi['conversions'] = int(df_clean[col].apply(clean_val).sum())
            kpi['cols_found']['conversions'] = c

    return kpi

# ==========================================
# 4. 頁面：廣告看板 (Dashboard)
# ==========================================
if page == "📈 廣告看板":
    st.title("📊 廣告成效實時診斷")
    f = st.file_uploader("上傳 Google Ads 報表 (CSV 或 Excel)", type=['csv', 'xlsx'])
    
    if f:
        try:
            # --- 智能標題偵測邏輯 ---
            if f.name.endswith('.csv'):
                # 先讀取幾行看看標題在哪
                tmp = pd.read_csv(f, nrows=10, header=None)
                f.seek(0)
                h_row = 0
                for i, row in tmp.iterrows():
                    if any(k in "".join(map(str, row.values)) for k in ["廣告活動", "費用", "點擊"]):
                        h_row = i
                        break
                df = pd.read_csv(f, skiprows=h_row)
            else:
                tmp = pd.read_excel(f, nrows=10, header=None)
                h_row = 0
                for i, row in tmp.iterrows():
                    if any(k in "".join(map(str, row.values)) for k in ["廣告活動", "費用", "點擊"]):
                        h_row = i
                        break
                df = pd.read_excel(f, header=h_row)

            # 清理標題字元
            df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
            
            # 顯示 KPI
            data = extract_kpi_v2(df)
            st.success(f"✅ 已成功解析報表！(定位標題行：{h_row})")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("總花費 (Cost)", f"${data['cost']:,.2f}")
            c2.metric("總點擊 (Clicks)", f"{data['clicks']:,} 次")
            c3.metric("總轉換 (Conv.)", f"{data['conversions']:,} 筆")
            cpa = data['cost']/data['conversions'] if data['conversions'] > 0 else 0
            c4.metric("平均 CPA", f"${cpa:,.2f}")

            with st.expander("🔍 數據定位調試 (Debug)"):
                st.write("AI 抓取的欄位對應表：", data['cols_found'])
                st.dataframe(df.head(5))

            st.divider()
            st.subheader("🤖 AI 一鍵診斷報告")
            a1, a2, a3 = st.columns(3)
            q = None
            if a1.button("🚨 抓出錢坑 (Waste Check)"): q = "找出花費最高但沒轉換的項目。"
            if a2.button("📈 提升轉換率"): q = "分析點擊與轉換，給予 3 個優化建議。"
            if a3.button("📝 生成週報報告"): q = "總結本週表現與下週預算建議。"

            if q and api_key:
                with st.spinner("優化師正在分析..."):
                    res = model.generate_content([q, f"數據摘要:\n{df.head(40).to_string()}"], stream=True)
                    full = ""
                    placeholder = st.empty()
                    for chunk in res:
                        full += chunk.text
                        placeholder.markdown(full + "▌")
                    placeholder.markdown(full)
                    st.download_button("📥 下載分析報告", full, file_name="GiveGift_Report.txt")

        except Exception as e:
            st.error(f"讀取失敗：{e}")

# ==========================================
# 5. 頁面：A/B 測試
# ==========================================
elif page == "💡 A/B 測試生成":
    st.title("💡 廣告文案 A/B 測試")
    with st.form("ab"):
        n = st.text_input("活動名稱")
        m = st.text_area("核心賣點")
        btn = st.form_submit_button("生成對照組")
        if btn and api_key:
            res = model.generate_content(f"為『尚禮坊』的{n}活動寫兩組 A/B 測試文案，賣點是：{m}。請區分理性與感性訴求。")
            st.markdown(res.text)
