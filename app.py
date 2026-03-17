import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import sqlite3
from datetime import datetime

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

def save_chat(role, content):
    conn = sqlite3.connect('givegift_ads.db')
    c = conn.cursor()
    c.execute("INSERT INTO chat_history (role, content, created_at) VALUES (?, ?, ?)", 
              (role, str(content), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def load_chats():
    conn = sqlite3.connect('givegift_ads.db')
    df = pd.read_sql_query("SELECT role, content FROM chat_history ORDER BY id ASC", conn)
    conn.close()
    return df.to_dict('records')

def save_campaign(name, ad_type, budget, audience, core_message, ai_proposal):
    conn = sqlite3.connect('givegift_ads.db')
    c = conn.cursor()
    c.execute('''INSERT INTO campaigns 
                 (name, ad_type, budget, audience, core_message, ai_proposal, created_at) 
                 VALUES (?, ?, ?, ?, ?, ?, ?)''', 
              (name, ad_type, budget, audience, core_message, ai_proposal, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# ==========================================
# 1. 基礎設定與系統人設
# ==========================================
st.set_page_config(page_title="尚禮坊 AI 廣告優化師", page_icon="💐", layout="wide")

SYSTEM_PROMPT = """
你現在是『尚禮坊 (Give Gift Boutique, https://www.givegift.com.hk/)』內部的 Google Ads 資深優化師。
你擁有 10 年經驗，經手過百萬預算。尚禮坊是香港首屈一指的花店與禮品店，專營花束、果籃、美食禮盒與企業節日送禮。

你的核心任務與行為準則：
1. 深入理解尚禮坊的高端品牌形象與受眾。
2. 分析數據時，必須敏銳察覺節日季節性對數據的影響。
3. 提供具體、可執行的優化建議。
4. 【重要】身為專業顧問，如果使用者提供的資訊（例如受眾、預算、活動目的、歷史數據）不夠清楚，請「主動反問使用者」索取更多資料。不要在資訊不足的情況下給出空泛的結論。
5. 生成廣告時，文案必須符合香港本地用語，極度專業且具備強烈吸引力。
"""

# ==========================================
# 2. 側邊欄：API 設定、模型選擇與導覽
# ==========================================
st.sidebar.title("💐 尚禮坊廣告中控台")
api_key = st.sidebar.text_input("🔑 請輸入 Gemini API Key:", type="password")

# --- 新增：讓使用者自由選擇模型版本 ---
selected_model = st.sidebar.selectbox(
    "🧠 請選擇 AI 模型版本:",
    [
        "gemini-1.5-flash", 
        "gemini-1.5-pro", 
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-3.0-pro"
    ],
    index=0, # 預設選擇第一個 (1.5-flash 最穩定且額度最高)
    help="Flash 版本速度快、免費額度高（推薦日常使用）；Pro 版本較聰明，但免費額度極低（容易報錯 429）。"
)

if api_key:
    genai.configure(api_key=api_key)
    # 這裡會動態套用您在側邊欄選擇的模型
    model = genai.GenerativeModel(selected_model, system_instruction=SYSTEM_PROMPT)
else:
    st.sidebar.warning("請輸入 API Key 以啟動 AI 助理")

st.sidebar.divider()
page = st.sidebar.radio("請選擇功能頁面：", ["📊 頁面一：成效分析與紀錄", "💡 頁面二：廣告企劃生成"])

# ==========================================
# 3. 頁面一：成效分析與對話
# ==========================================
if page == "📊 頁面一：成效分析與紀錄":
    st.title("📊 廣告成效分析與歷史紀錄")
    
    st.header("📌 已儲存的廣告活動企劃")
    conn = sqlite3.connect('givegift_ads.db')
    campaigns_df = pd.read_sql_query("SELECT id, name, ad_type, budget, created_at FROM campaigns ORDER BY id DESC", conn)
    
    if not campaigns_df.empty:
        st.dataframe(campaigns_df, use_container_width=True, hide_index=True)
        selected_id = st.selectbox("查看企劃詳細內容 (選擇 ID):", campaigns_df['id'].tolist())
        if selected_id:
            detail_df = pd.read_sql_query(f"SELECT ai_proposal FROM campaigns WHERE id={selected_id}", conn)
            with st.expander("📄 展開 AI 企劃內容", expanded=False):
                st.markdown(detail_df.iloc[0]['ai_proposal'])
    else:
        st.info("目前還沒有儲存的廣告企劃。請至「頁面二」生成並儲存！")
    conn.close()
    
    st.divider()
    st.header("💬 AI 數據診斷與諮詢")
    uploaded_file = st.file_uploader("📂 上傳 Google Ads 數據報表 (CSV/Excel) 或 截圖 (JPG/PNG)", type=['csv', 'xlsx', 'png', 'jpg', 'jpeg'])
    
    chat_history = load_chats()
    for msg in chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    user_query = st.chat_input("請輸入您的問題，例如：幫我分析上個月的廣告表現...")
    
    if user_query and api_key:
        with st.chat_message("user"):
            st.markdown(user_query)
        save_chat("user", user_query) 
        
        contents = [user_query]
        if uploaded_file is not None:
            if uploaded_file.name.endswith(('.png', '.jpg', '.jpeg')):
                image = Image.open(uploaded_file)
                st.image(image, caption="已上傳圖片", width=300)
                contents.append(image)
            elif uploaded_file.name.endswith('.csv'):
                try:
                    df = pd.read_csv(uploaded_file, skiprows=2)
                except Exception:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, on_bad_lines='skip')
                contents.append(f"數據資料：\n{df.head(20).to_string()}")
            elif uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
                contents.append(f"數據資料：\n{df.head(20).to_string()}")
                
        with st.chat_message("assistant"):
            try:
                history_text = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history[-5:]])
                if history_text:
                    contents.insert(0, f"【過去的對話紀錄】:\n{history_text}\n---")
                    
                response = model.generate_content(contents, stream=True)
                
                message_placeholder = st.empty()
                full_response = ""
                
                for chunk in response:
                    full_response += chunk.text
                    message_placeholder.markdown(full_response + "▌")
                
                message_placeholder.markdown(full_response)
                save_chat("assistant", full_response)
            except Exception as e:
                st.error(f"發生錯誤：{e}")

# ==========================================
# 4. 頁面二：廣告企劃生成
# ==========================================
elif page == "💡 頁面二：廣告企劃生成":
    st.title("💡 高效廣告企劃生成器")
    
    with st.form("campaign_form"):
        col1, col2 = st.columns(2)
        with col1:
            campaign_name = st.text_input("🎯 活動名稱", placeholder="例如：2026 企業中秋果籃")
            daily_budget = st.number_input("💰 每日預算限制 (HKD)", min_value=100, value=500, step=100)
        with col2:
            ad_type = st.selectbox("📣 建議廣告類型", ["搜尋廣告 (Search)", "最高成效廣告 (PMax)", "多媒體廣告 (Display)"])
            target_audience = st.text_input("👥 目標受眾", placeholder="例如：各大企業HR、行政秘書")
            
        core_message = st.text_area("✨ 核心賣點/優惠內容", placeholder="例如：滿 $1500 免費送貨至多個地點。")
        submitted = st.form_submit_button("🚀 生成專業廣告企劃")

    if "temp_proposal" not in st.session_state:
        st.session_state.temp_proposal = ""

    if submitted:
        if not api_key:
            st.error("請先輸入 API Key！")
        else:
            prompt = f"""
            請為尚禮坊規劃 Google Ads 企劃。
            活動：{campaign_name} | 類型：{ad_type} | 預算：${daily_budget} HKD | 受眾：{target_audience} | 賣點：{core_message}
            請產出：1. 策略建議 2. 關鍵字清單(10個) 3. 廣告文案(3標題/2說明) 4. 額外資訊建議
            """
            
            st.write("撰寫中...")
            try:
                response = model.generate_content(prompt, stream=True)
                message_placeholder = st.empty()
                full_response = ""
                
                for chunk in response:
                    full_response += chunk.text
                    message_placeholder.markdown(full_response + "▌")
                
                message_placeholder.markdown(full_response)
                st.session_state.temp_proposal = full_response
            except Exception as e:
                st.error(f"發生錯誤：{e}")

    if st.session_state.temp_proposal:
        st.success("企劃生成完成！👇 檢視內容並儲存")
        if st.button("💾 採用並儲存到「頁面一」的紀錄中"):
            save_campaign(campaign_name, ad_type, daily_budget, target_audience, core_message, st.session_state.temp_proposal)
            st.toast('✅ 企劃已成功儲存！請至「頁面一」查看。')
            st.session_state.temp_proposal = ""
