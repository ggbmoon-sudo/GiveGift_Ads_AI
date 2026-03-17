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
st.set_page_config(page_title="Give Gift Boutique Ads,Moon", page_icon="📊", layout="wide")

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
st.sidebar.title("💐 Give Gift Boutique Ads,Moon")
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
    kpi = {"cost": 0, "clicks": 0, "conversions": 0}
    cols = [c.lower() for c in df.columns]
    
    # 簡單的關鍵字模糊比對來抓取總和
    for orig_col, lower_col in zip(df.columns, cols):
        if any(x in lower_col for x in ['cost', '花費', '費用']):
            kpi['cost'] = pd.to_numeric(df[orig_col], errors='coerce').sum()
        if any(x in lower_col for x in ['click', '點擊']):
            kpi['clicks'] = pd.to_numeric(df[orig_col], errors='coerce').sum()
        if any(x in lower_col for x in ['conversion', '轉換']):
            kpi['conversions'] = pd.to_numeric(df[orig_col], errors='coerce').sum()
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
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file, skiprows=2)
            else:
                df = pd.read_excel(uploaded_file)
            
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
                # 避免除以 0 錯誤
                cpa = kpi_data['cost'] / kpi_data['conversions'] if kpi_data['conversions'] > 0 else 0
                st.metric("每次轉換成本 (CPA)", f"${cpa:,.2f}")
                
            with st.expander("預覽原始數據表"):
                st.dataframe(df.head(10))
                
            st.divider()
            
            # --- 功能 3: 快捷行動按鈕 (一鍵分析) ---
            st.subheader("🤖 AI 智能分析快捷鍵")
            st.write("請選擇您想執行的分析任務：")
            
            action_col1, action_col2, action_col3 = st.columns(3)
            selected_action = None
            
            if action_col1.button("🚨 抓出吃預算怪獸 (浪費錢清單)"):
                selected_action = "請幫我分析這份數據，找出『花費高但轉換次數極低（或為0）』的關鍵字或廣告活動，並告訴我該如何處理。"
            if action_col2.button("🚀 提高轉換率策略"):
                selected_action = "請幫我分析這份數據的『點擊率』與『轉換率』，並給出 3 個能立刻提升轉換率的具體優化建議。"
            if action_col3.button("📝 產生老闆/會議週報"):
                selected_action = "請將這份數據總結成一份給老闆看的高階報告。包含：整體表現評分、亮點、最致命的缺點、以及下週的優化預算分配建議。"

            if selected_action and api_key:
                with st.spinner("AI 首席優化師正在深度運算中..."):
                    try:
                        contents = [selected_action, f"數據資料：\n{df.head(30).to_string()}"]
                        response = model.generate_content(contents, stream=True)
                        
                        st.subheader("💡 分析結果")
                        message_placeholder = st.empty()
                        full_response = ""
                        for chunk in response:
                            full_response += chunk.text
                            message_placeholder.markdown(full_response + "▌")
                        message_placeholder.markdown(full_response)
                        
                        # --- 功能 4: 報告匯出功能 ---
                        st.download_button(
                            label="📥 下載此分析報告 (TXT)",
                            data=full_response,
                            file_name=f"Google_Ads_Report_{datetime.now().strftime('%Y%m%d')}.txt",
                            mime="text/plain"
                        )
                        
                    except Exception as e:
                        st.error(f"發生錯誤：{e} (提示：若為 429 錯誤請切換至 Flash 模型)")
                        
        except Exception as e:
            st.warning("檔案讀取發生格式異常，但您可以直接使用對話框發問。")

    st.divider()
    st.write("💬 手動對話區 (如果您有特定問題)：")
    user_query = st.chat_input("請輸入您自訂的問題...")
    if user_query and api_key:
        st.info(f"您的提問：{user_query} (此處功能保留供臨時查詢使用)")

# ==========================================
# 4. 頁面二：A/B 測試文案生成器 (專業版)
# ==========================================
elif page == "💡 A/B 測試文案生成器":
    st.title("💡 A/B 測試廣告文案生成器")
    st.write("專業的優化必須經過測試。輸入活動資訊，AI 將自動為您產出兩組不同心理學訴求的廣告對照組。")
    
    with st.form("ab_test_form"):
        col1, col2 = st.columns(2)
        with col1:
            campaign_name = st.text_input("🎯 活動名稱", placeholder="例如：尚禮坊中秋頂級果籃")
            target_audience = st.text_input("👥 目標受眾", placeholder="例如：需要送禮給大客戶的企業秘書")
        with col2:
            core_message = st.text_input("✨ 核心賣點", placeholder="例如：法國進口水果、精美皮盒包裝、專車直送")
            call_to_action = st.text_input("📣 行動號召 (CTA)", placeholder="例如：立即預訂享早鳥 85 折")
            
        submitted = st.form_submit_button("🚀 生成 A/B 測試企劃")

    if submitted:
        if not api_key:
            st.error("請先輸入 API Key！")
        else:
            prompt = f"""
            你現在是尚禮坊的高級廣告文案指導。請根據以下資訊，幫我產出一個 Google 搜尋廣告的 A/B 測試方案：
            活動：{campaign_name}
            受眾：{target_audience}
            賣點：{core_message}
            行動號召：{call_to_action}
            
            請產出：
            1. 【版本 A：理性/規格訴求】：強調產品優勢、折扣、性價比、速度。
               - 包含 3 個標題 (不多於30字元)
               - 包含 2 個說明 (不多於90字元)
            2. 【版本 B：感性/痛點訴求】：強調送禮的面子、尊榮感、解決對方的煩惱。
               - 包含 3 個標題 (不多於30字元)
               - 包含 2 個說明 (不多於90字元)
            3. 【A/B 測試建議】：告訴我這次測試的重點觀察指標 (例如點擊率還是轉化率？)
            
            請用專業的 Markdown 格式排版。
            """
            
            with st.spinner("正在為您撰寫極具說服力的 A/B 測試方案..."):
                try:
                    response = model.generate_content(prompt)
                    st.success("✅ A/B 測試方案已生成！")
                    st.markdown(response.text)
                    
                    # 匯出 A/B 測試企劃
                    st.download_button(
                        label="📥 下載 A/B 測試企劃 (TXT)",
                        data=response.text,
                        file_name=f"AB_Test_Plan_{campaign_name}.txt",
                        mime="text/plain"
                    )
                except Exception as e:
                    st.error(f"發生錯誤：{e}")
