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
# 1. 核心設定 (請確認這個 ID 與您瀏覽器網址列一致)
# ==========================================
# 💡 檢查點：網址 https://docs.google.com/spreadsheets/d/ [這一段就是ID] /edit
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs" 

# ==========================================
# 2. 認證與自動修復邏輯
# ==========================================
def get_creds():
    if "gcp_service_account" not in st.secrets: return None
    info = dict(st.secrets["gcp_service_account"])
    info["private_key"] = info["private_key"].replace("\\n", "\n")
    return Credentials.from_service_account_info(info, scopes=[
        'https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'
    ])

# ==========================================
# 3. 側邊欄 UI：診斷與檔案鏈接
# ==========================================
st.set_page_config(page_title="GGB Ads Manager", page_icon="💐", layout="wide")
st.sidebar.title("💐 專案管理中心")

# 診斷燈號
if "api_key" not in st.session_state: st.session_state.api_key = ""
api_key = st.sidebar.text_input("🔑 API Key:", type="password", value=st.session_state.api_key)
st.session_state.api_key = api_key

try:
    creds = get_creds()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(MY_SHEET_ID)
    
    # --- 關鍵功能：顯示 AI 正在連接的檔案 ---
    st.sidebar.success("🟢 雲端連線成功")
    st.sidebar.markdown(f"🔗 [點此打開 AI 正在使用的表格]({sh.url})")
    
    # 初始化工作表
    def get_ws(title, head):
        try: return sh.worksheet(title)
        except: 
            w = sh.add_worksheet(title=title, rows="1000", cols=len(head))
            w.insert_row(head, 1); return w

    ws_p = get_ws("Projects", ["ID", "Name", "Created"])
    ws_c = get_ws("ChatHistory", ["PID", "Role", "Content", "Time"])
    
    # 讀取項目
    projs_data = ws_p.get_all_records()
    p_names = [p['Name'] for p in projs_data]

    with st.sidebar.expander("➕ 建立新項目"):
        new_n = st.text_input("項目名稱")
        if st.button("確認建立") and new_n:
            pid = str(int(datetime.now().timestamp()))
            ws_p.insert_row([pid, new_n, datetime.now().strftime("%Y-%m-%d")], 2)
            st.toast("✅ 資料已同步至 Google Sheets")
            st.rerun()

    if p_names:
        sel_name = st.sidebar.selectbox("📂 選擇項目：", p_names)
        curr_p = next(p for p in projs_data if p['Name'] == sel_name)
    else: curr_p = None

except Exception as e:
    st.sidebar.error(f"🔴 連線失敗: {e}")
    curr_p = None

# ==========================================
# 4. 主畫面：文件分析與對話
# ==========================================
if curr_p:
    st.title(f"📈 項目：{curr_p['Name']}")
    
    # 文件上傳
    with st.expander("📎 上傳分析文件", expanded=False):
        up_f = st.file_uploader("CSV, XLSX, PDF, Image", type=['csv','xlsx','pdf','jpg','png'])
        # (文件處理邏輯省略，維持原樣)

    st.subheader("💬 AI 優化顧問")
    
    # 顯示歷史
    all_chat = ws_c.get_all_records()
    p_chat = [m for m in all_chat if str(m['PID']) == str(curr_p['ID'])]
    for m in p_chat:
        with st.chat_message(m['Role'].lower()): st.markdown(m['Content'])

    # 對話輸入
    u_input = st.chat_input("輸入問題...")
    if u_input and api_key:
        with st.chat_message("user"): st.markdown(u_input)
        # 即時儲存至雲端
        ws_c.insert_row([str(curr_p['ID']), "User", u_input, datetime.now().strftime("%H:%M")], 2)
        
        with st.chat_message("assistant"):
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            res = model.generate_content(u_input)
            st.markdown(res.text)
            # 即時儲存至雲端
            ws_c.insert_row([str(curr_p['ID']), "Assistant", res.text, datetime.now().strftime("%H:%M")], 2)
            st.toast("✅ 對話已存入 Google Sheets")
            st.rerun()
