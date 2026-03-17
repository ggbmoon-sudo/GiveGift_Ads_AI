import streamlit as st
import pandas as pd
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import io
import os

# ==========================================
# 1. 核心設定 (請填寫您的試算表 ID)
# ==========================================
# 💡 ID 就在網址 https://docs.google.com/spreadsheets/d/ [這一段亂碼] /edit 之中
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs" 

# ==========================================
# 2. 系統狀態檢測 (確保不崩潰)
# ==========================================
def check_connection(api_key, sheet_id):
    results = {"ai": "🔴", "sheets": "🔴", "drive": "🔴", "error": ""}
    
    # 測試 Gemini
    if api_key:
        try:
            genai.configure(api_key=api_key)
            genai.list_models()
            results["ai"] = "🟢"
        except Exception as e:
            results["ai"] = "❌"; results["error"] += f"AI: {str(e)}\n"

    # 測試 Google
    try:
        if "gcp_service_account" not in st.secrets:
            results["sheets"] = "⚠️ Secret未設定"
        else:
            info = st.secrets["gcp_service_account"]
            creds = Credentials.from_service_account_info(info, scopes=[
                'https://www.googleapis.com/auth/spreadsheets', 
                'https://www.googleapis.com/auth/drive'
            ])
            # Sheets 測試
            try:
                gc = gspread.authorize(creds)
                gc.open_by_key(sheet_id)
                results["sheets"] = "🟢"
            except Exception as e:
                results["sheets"] = "❌"; results["error"] += f"Sheets: {str(e)}\n"
            # Drive 測試
            try:
                build('drive', 'v3', credentials=creds).files().list(pageSize=1).execute()
                results["drive"] = "🟢"
            except Exception as e:
                results["drive"] = "❌"; results["error"] += f"Drive: {str(e)}\n"
    except Exception as e:
        results["error"] += f"系統錯誤: {str(e)}"
    return results

# ==========================================
# 3. 側邊欄 UI (強制渲染燈號)
# ==========================================
st.set_page_config(page_title="GGB Ads Manager", page_icon="💐", layout="wide")
st.sidebar.title("💐 專案管理中心")

# --- 診斷燈號區 ---
st.sidebar.subheader("📡 系統連線診斷")
user_api_key = st.sidebar.text_input("🔑 API Key:", type="password")
h = check_connection(user_api_key, MY_SHEET_ID)

with st.sidebar.container(border=True):
    st.write(f"{h['ai']} **AI** | {h['sheets']} **Sheets** | {h['drive']} **Drive**")
    if h["error"]:
        with st.sidebar.expander("🔍 查看詳細錯誤"):
            st.code(h["error"])
    elif h["sheets"] == "🟢":
        st.sidebar.success("✅ 雲端連線正常")

st.sidebar.divider()

# ==========================================
# 4. 雲端記憶邏輯 (僅在 Sheets 🟢 時運作)
# ==========================================
if h["sheets"] == "🟢":
    info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(MY_SHEET_ID)

    # 取得或建立分頁
    def get_ws(title, headers):
        try: return sh.worksheet(title)
        except: 
            w = sh.add_worksheet(title=title, rows="1000", cols=len(headers))
            w.append_row(headers); return w

    ws_p = get_ws("Projects", ["ID", "Name", "Created_At"])
    ws_c = get_ws("ChatHistory", ["PID", "Role", "Content", "Time"])

    # 專案列表
    projects = ws_p.get_all_records()
    p_names = [p['Name'] for p in projects]

    with st.sidebar.expander("➕ 建立新項目"):
        new_name = st.text_input("輸入名稱")
        if st.button("確認建立") and new_name:
            ws_p.append_row([str(int(datetime.now().timestamp())), new_name, datetime.now().strftime("%Y-%m-%d")])
            st.rerun()

    if p_names:
        sel_p = st.sidebar.selectbox("📂 選擇項目：", p_names)
        curr_p = next(p for p in projects if p['Name'] == sel_p)
    else: curr_p = None
else:
    st.sidebar.warning("請先修正 Google Sheets 連線")
    curr_p = None

st.sidebar.selectbox("🧠 模型:", ["gemini-2.5-flash", "gemini-2.5-pro"])

# ==========================================
# 5. 主頁面：數據與對話
# ==========================================
if curr_p:
    st.title(f"📈 項目：{curr_p['Name']}")
    
    # 快捷按鈕與對話 (Session State 防止沒反應)
    if "chat_query" not in st.session_state: st.session_state.chat_query = None

    st.subheader("🤖 快捷優化指令")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("📊 成效分析"): st.session_state.chat_query = "分析此活動成效"
    if c2.button("🚀 提高轉換"): st.session_state.chat_query = "如何提高轉換？"
    if c3.button("🧠 自動深度分析"): st.session_state.chat_query = "深度診斷數據"
    if c4.button("📈 生成視覺化圖表"): st.session_state.chat_query = "生成圖表分析"

    st.divider()

    # 顯示歷史紀錄
    history = ws_c.get_all_records()
    p_history = [m for m in history if str(m['PID']) == str(curr_p['ID'])]
    for m in p_history:
        with st.chat_message(m['Role'].lower()): st.markdown(m['Content'])

    u_input = st.chat_input("詢問 AI...")
    final_q = st.session_state.chat_query if st.session_state.chat_query else u_input

    if final_q and user_api_key:
        with st.chat_message("user"): st.markdown(final_q)
        ws_c.append_row([str(curr_p['ID']), "User", final_q, datetime.now().strftime("%H:%M")])
        
        with st.chat_message("assistant"):
            genai.configure(api_key=user_api_key)
            model = genai.GenerativeModel("gemini-1.5-flash") # 暫時固定測試
            res = model.generate_content(final_q)
            st.markdown(res.text)
            ws_c.append_row([str(curr_p['ID']), "Assistant", res.text, datetime.now().strftime("%H:%M")])
        
        st.session_state.chat_query = None
        st.rerun()
else:
    st.info("請先修正左側診斷問題並選擇項目。")
