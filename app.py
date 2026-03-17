import streamlit as st
import pandas as pd
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import os

# ==========================================
# 1. 核心設定 (請填寫您的試算表 ID)
# ==========================================
# 💡 這裡填入您 Google Sheet 網址中 /d/ 之後的那串亂碼
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs" 

# ==========================================
# 2. 系統診斷函數 (燈號邏輯)
# ==========================================
def get_health_status(api_key, sheet_id):
    health = {"gemini": "🔴", "sheets": "🔴", "drive": "🔴"}
    
    # 檢查 Gemini
    if api_key:
        try:
            genai.configure(api_key=api_key)
            genai.list_models()
            health["gemini"] = "🟢"
        except: health["gemini"] = "❌"
            
    # 檢查 Google 服務
    try:
        info = st.secrets["gcp_service_account"]
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(info, scopes=scope)
        
        # 測試 Sheets
        gc = gspread.authorize(creds)
        if sheet_id:
            try:
                gc.open_by_key(sheet_id)
                health["sheets"] = "🟢"
            except: health["sheets"] = "❌ ID錯"
        
        # 測試 Drive
        drive = build('drive', 'v3', credentials=creds)
        drive.files().list(pageSize=1).execute()
        health["drive"] = "🟢"
    except: pass
        
    return health

# ==========================================
# 3. 側邊欄 UI：診斷燈號就在這！
# ==========================================
st.sidebar.title("💐 尚禮坊活動管理中心")

# 顯示診斷燈號
st.sidebar.subheader("📡 系統連線診斷")
api_key = st.sidebar.text_input("🔑 API Key:", type="password")
h_status = get_health_status(api_key, MY_SHEET_ID)

# 用精簡的排版顯示燈號
with st.sidebar.container():
    st.write(f"{h_status['gemini']} **AI** | {h_status['sheets']} **Sheets** | {h_status['drive']} **Drive**")
    if "❌" in h_status.values() or "🔴" in h_status.values():
        st.sidebar.caption("提示：請檢查 Secrets 格式或 Sheets 共用權限")
    else:
        st.sidebar.caption("✅ 所有連線已就緒")

st.sidebar.divider()

# --- 原有的項目管理功能 ---
with st.sidebar.expander("➕ 建立新項目"):
    n = st.text_input("項目名稱")
    if st.button("確認建立"):
        if n:
            # 這裡暫時先跑本地測試，確認燈號亮了我們再串雲端儲存
            st.success(f"已建立項目：{n}")
            st.rerun()

# 模擬項目列表 (之後會從 Sheets 抓取)
st.sidebar.selectbox("📂 選擇目前操作項目：", ["測試專案_001"])
st.sidebar.radio("導覽：", ["📈 數據分析看板", "💡 文案生成器"])

# ==========================================
# 4. 主畫面內容
# ==========================================
st.title("🚀 尚禮坊 AI 工作站")
st.write("請觀察左側邊欄的燈號狀態。")

if h_status["sheets"] == "🟢":
    st.balloons()
    st.success("太棒了！您的 Google Sheets 連線成功！現在可以開始永久儲存了。")
else:
    st.info("等待 Google Sheets 連線成功中... (請確保已將 Service Account 加入共用)")
