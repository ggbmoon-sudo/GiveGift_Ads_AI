import streamlit as st
import pandas as pd
import google.generativeai as genai
import sqlite3
from datetime import datetime
import io
import os

# ==========================================
# 1. 本地資料庫初始化
# ==========================================
DB_FILE = "ggb_local_memory.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS projects 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, 
                  role TEXT, content TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 資料庫操作函數 ---
def save_chat(pid, role, content):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO chat_history (project_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                 (pid, role, content, datetime.now().strftime("%H:%M")))
    conn.commit(); conn.close()

def load_chats(pid):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(f"SELECT role, content FROM chat_history WHERE project_id={pid}", conn)
    conn.close()
    return df.to_dict('records')

# ==========================================
# 2. 介面設定
# ==========================================
st.set_page_config(page_title="GGB Ads Consultant", page_icon="💐", layout="wide")

# --- 側邊欄：專案管理 ---
st.sidebar.title("💐 尚禮坊管理中心")

# 備份與還原區 (解決雲端重啟遺失問題)
with st.sidebar.expander("💾 數據備份與還原"):
    # 導出
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as f:
            st.download_button("📥 下載目前備份 (.db)", f, file_name=f"ggb_backup_{datetime.now().strftime('%m%d')}.db")
    
    # 導入
    uploaded_db = st.file_uploader("📤 上傳備份檔還原", type="db")
    if uploaded_db:
        with open(DB_FILE, "wb") as f:
            f.write(uploaded_db.getbuffer())
        st.success("數據還原成功！請重新整理頁面。")
        st.rerun()

st.sidebar.divider()

# 項目選擇
with st.sidebar.expander("➕ 建立新項目"):
    new_p = st.text_input("項目名稱")
    if st.button("確認建立") and new_p:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("INSERT INTO projects (name, created_at) VALUES (?, ?)", (new_p, datetime.now().strftime("%Y-%m-%d")))
        conn.commit(); conn.close(); st.rerun()

conn = sqlite3.connect(DB_FILE)
projects = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
conn.close()

if not projects.empty:
    sel_name = st.sidebar.selectbox("📂 選擇項目：", projects['name'].tolist())
    curr_p = projects[projects['name'] == sel_name].iloc[0]
else:
    curr_p = None

st.sidebar.divider()
api_key = st.sidebar.text_input("🔑 API Key:", type="password")
selected_model = st.sidebar.selectbox("🧠 模型:", ["gemini-2.5-flash", "gemini-2.5-pro"])

# ==========================================
# 3. 數據分析邏輯
# ==========================================
def analyze_df(df):
    try:
        df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
        def clean(v): return float(str(v).replace('$', '').replace(',', '').strip()) if not pd.isna(v) and str(v) != '--' else 0.0
        res = {"cost": 0.0, "clicks": 0, "convs": 0}
        for col in df.columns:
            c = col.lower()
            if '費用' in c and '平均' not in c: res['cost'] = df[col].apply(clean).sum()
            if '點擊' in c and '率' not in c: res['clicks'] = int(df[col].apply(clean).sum())
            if '轉換' in c and not any(ex in c for ex in ['價值','率']): res['convs'] = int(df[col].apply(clean).sum())
        return res
    except: return None

# ==========================================
# 4. 主畫面
# ==========================================
if curr_p:
    st.title(f"📈 項目：{curr_p['name']}")
    
    # 報表上傳 (暫存在 Session)
    with st.expander("📊 報表臨時掛鉤"):
        up_f = st.file_uploader("上傳 Google Ads 報表 (CSV/XLSX)", type=['csv', 'xlsx'])
        if up_f:
            df = pd.read_csv(up_f) if up_f.name.endswith('.csv') else pd.read_excel(up_f)
            st.session_state.current_df = df
            st.success("報表已載入。")

    # 快捷按鈕
    st.subheader("🤖 AI 快捷分析")
    c1, c2, c3, c4 = st.columns(4)
    q = None
    if c1.button("📊 分析成效"): q = "請分析目前數據的成效。"
    if c2.button("🚀 提高轉換"): q = "如何提高此活動的轉換率？"
    if c3.button("🧠 深度診斷"): q = "執行自動診斷，找出浪費預算的地方。"
    if c4.button("📈 生成圖表"): st.info("請在對話框輸入『幫我畫費用分布圖』")

    st.divider()

    # 對話紀錄顯示
    history = load_chats(curr_p['id'])
    for m in history:
        with st.chat_message(m['role']): st.markdown(m['content'])

    # 處理輸入
    u_input = st.chat_input("詢問 AI 顧問...")
    final_q = q if q else u_input

    if final_q and api_key:
        with st.chat_message("user"): st.markdown(final_q)
        save_chat(curr_p['id'], "user", final_q)
        
        with st.chat_message("assistant"):
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(selected_model)
            
            # 組合數據摘要
            data_context = ""
            if "current_df" in st.session_state:
                res = analyze_df(st.session_state.current_df)
                data_context = f"數據摘要: 花費${res['cost']}, 點擊{res['clicks']}, 轉換{res['convs']}\n"
            
            response = model.generate_content(f"{data_context}問題: {final_q}")
            st.markdown(response.text)
            save_chat(curr_p['id'], "assistant", response.text)
            st.rerun()
else:
    st.info("請在左側『建立新項目』開始。下班前記得點擊側邊欄『下載備份』以保存紀錄！")
