import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import sqlite3
from datetime import datetime
import io

# ==========================================
# 0. 資料庫初始化設定 (SQLite)
# ==========================================
def init_db():
    conn = sqlite3.connect('givegift_ads.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, ad_type TEXT, budget REAL, 
            audience TEXT, core_message TEXT, ai_proposal TEXT, created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT, content TEXT, created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 1. 基礎設定與系統人設
# ==========================================
st.set_page_config(page_title="Give Gift Boutique Ads, Moon", page_icon="📊", layout="wide")

SYSTEM_PROMPT = """
你現在是『尚禮坊 (Give Gift Boutique)』的首席 Google Ads 數據分析師。
你的任務是提供極度專業、視覺化排版良好（多用 markdown 表格、粗體、條列式、甚至 emoji）的分析報告。
絕對不要廢話，直接給出結論：
1. 【健康評分】：請先給出一個 0-100 的分數。
2. 【最致命問題】：點出目前數據中最浪費錢或成效最差的地方。
3. 【具體行動】：請列出 3 個我們現在登入後台立刻要按下的操作按鈕（例如停用某關鍵字、調降 CPA 等）。
"""

# ==========================================
# 2. 側邊欄：API 設定與模型切換
# ==========================================
st.sidebar.title("💐 Give Gift Boutique Ads, Moon")
api_key = st.sidebar.text_input("🔑 請輸入 Gemini API Key:", type="password")

selected_model = st.sidebar.selectbox(
    "🧠 AI 模型引擎:",
    ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-3.0-pro"],
    index=0
)

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(selected_model, system_instruction=SYSTEM_PROMPT)
else:
    st.sidebar.warning("請輸入 API Key 以啟動系統")

st.sidebar.divider()
page = st.sidebar.radio("切換工作區：", ["📈 廣告健康診斷看板 (Dashboard)", "💡 A/B 測試文案生成器"])

# 輔助函數：嘗試從資料中抓取 KPI
def extract_kpi(df):
    kpi = {"cost": 0.0, "clicks": 0, "conversions": 0}
    
    def clean_num(val):
        if pd.isna(val) or val == '--': return 0.0
        s = str(val).replace('$', '').replace(',', '').replace('%', '').strip()
        try:
            return float(s)
        except:
            return 0.0

    # 排除報表底部的總計行
    df_clean = df[~df.iloc[:, 0].astype(str).str.contains('總計|Total|總和', na=False)].copy()

    for col in df_clean.columns:
        c_lower = str(col).lower().strip()
        
        # 匹配總費用 (排除平均、每單位等指標)
        if ('費用' in c_lower or 'cost' in c_lower) and not any(ex in c_lower for ex in ['平均', '每', 'avg', 'cpc', 'cpm', '率']):
            kpi['cost'] = df_clean[col].apply(clean_num).sum()
            
        # 匹配點擊數
        elif ('點擊' in c_lower or 'clicks' in c_lower) and '率' not in c_lower:
            kpi['clicks'] = int(df_clean[col].apply(clean_num).sum())
            
        # 匹配轉換數
        elif '轉換' in c_lower and not any(ex in c_lower for ex in ['價值', '率', '費用', 'value', 'rate', 'cost']):
            kpi['conversions'] = int(df_clean[col].apply(clean_num).sum())

    return kpi

# ==========================================
# 3. 頁面一：廣告健康診斷看板 (專業版)
# ==========================================
if page == "📈 廣告健康診斷看板 (Dashboard)":
    st.title("📈 廣告健康診斷看板")
    st.write("上傳報表，讓 AI 自動產生洞察報告與優化策略。")
    
    uploaded_file = st.file_uploader("📂 上傳 Google Ads 報表 (CSV/Excel)", type=['csv', 'xlsx'])
    
    if uploaded_file is not None:
        try:
            # --- 強化版檔案讀取邏輯 ---
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file, skiprows=2)
            else:
                # Excel 自動尋找標題行
                test_df = pd.read_excel(uploaded_file, nrows=15, header=None)
                header_row = 0
                for i, row in test_df.iterrows():
                    row_str = "".join(str(x) for x in row.values)
                    if any(key in row_str for key in ["廣告活動", "費用", "點擊", "Clicks", "Cost"]):
                        header_row = i
                        break
                df = pd.read_excel(uploaded_file, header=header_row)
            
            # 清理欄位標題
            df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
            
            st.success("✅ 數據載入成功！")
            
            # --- 功能 1: 視覺化 KPI 看板 ---
            st.subheader("📊 關鍵指標總覽 (KPIs)")
            kpi_data = extract_kpi(df)
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("總花費 (Cost)", f"${kpi_data['cost']:,.2f}")
            with col2:
                st.metric("總點擊 (Clicks)", f"{kpi_data['clicks']:,.0f} 次")
            with col3:
                st.metric("總轉換 (Conversions)", f"{kpi_data['conversions']:,.0f} 筆")
            with col4:
                cpa = kpi_data['cost'] / kpi_data['conversions'] if kpi_data['conversions'] > 0 else 0
                st.metric("每次轉換成本 (CPA)", f"${cpa:,.2f}")
                
            with st.expander("預覽原始數據表"):
                st.dataframe(df.head(10))
                
            st.divider()
            
            # --- 功能 3: 快捷行動按鈕 ---
            st.subheader("🤖 AI 智能分析快捷鍵")
            action_col1, action_col2, action_col3 = st.columns(3)
            selected_action = None
            
            if action_col1.button("🚨 抓出吃預算怪獸 (浪費錢清單)"):
                selected_action = "請分析數據，找出花費高但轉換極低的項目，並給予停用建議。"
            if action_col2.button("🚀 提高轉換率策略"):
                selected_action = "分析點擊率與轉換率，給予 3 個具體提升轉換的行動方案。"
            if action_col3.button("📝 產生老闆/會議週報"):
                selected_action = "總結整體表現評分、亮點、缺點及下週預算建議。"

            if selected_action and api_key:
                with st.spinner("AI 分析中..."):
                    try:
                        contents = [selected_action, f"數據摘要：\n{df.head(50).to_string()}"]
                        response = model.generate_content(contents, stream=True)
                        
                        st.subheader("💡 分析結果")
                        message_placeholder = st.empty()
                        full_response = ""
                        for chunk in response:
                            full_response += chunk.text
                            message_placeholder.markdown(full_response + "▌")
                        message_placeholder.markdown(full_response)
                        
                        st.download_button(
                            label="📥 下載報告 (TXT)",
                            data=full_response,
                            file_name=f"Ads_Report_{datetime.now().strftime('%m%d')}.txt"
                        )
                    except Exception as e:
                        st.error(f"分析失敗：{e}")
                        
        except Exception as e:
            st.error(f"檔案解析失敗：{e}")

    st.divider()
    st.write("💬 手動詢問：")
    user_query = st.chat_input("對這份數據還有什麼疑問？")
    if user_query and api_key:
        st.info(f"提問：{user_query}")

# ==========================================
# 4. 頁面二：A/B 測試文案生成器
# ==========================================
elif page == "💡 A/B 測試文案生成器":
    st.title("💡 A/B 測試文案生成器")
    with st.form("ab_test_form"):
        col1, col2 = st.columns(2)
        with col1:
            campaign_name = st.text_input("🎯 活動名稱")
            target_audience = st.text_input("👥 目標受眾")
        with col2:
            core_message = st.text_input("✨ 核心賣點")
            call_to_action = st.text_input("📣 行動號召")
        submitted = st.form_submit_button("🚀 生成方案")

    if submitted and api_key:
        prompt = f"針對{campaign_name}，受眾為{target_audience}，賣點{core_message}，請生成 A/B 測試方案（理性 vs 感性）。"
        with st.spinner("撰寫中..."):
            try:
                response = model.generate_content(prompt)
                st.markdown(response.text)
            except Exception as e:
                st.error(f"錯誤：{e}")
