import streamlit as st
import pandas as pd
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import os

# ==========================================
# 0. 系統狀態檢測函數
# ==========================================
def check_system_health(api_key, sheet_id):
    health = {
        "gemini": ("🔴 未連線", False),
        "sheets": ("🔴 未連線", False),
        "drive": ("🔴 未連線", False)
    }
    
    # 1. 檢測 Gemini
    if api_key:
        try:
            genai.configure(api_key=api_key)
            # 嘗試列出模型來測試金鑰是否有效
            genai.list_models()
            health["gemini"] = ("🟢 運作正常", True)
        except:
            health["gemini"] = ("❌ 金鑰無效", False)
            
    # 2. 檢測 Google 服務
    try:
        info = st.secrets["gcp_service_account"]
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(info, scopes=scope)
        
        # 測試 Sheets
        gs_client = gspread.authorize(creds)
        if sheet_id:
            try:
                gs_client.open_by_key(sheet_id)
                health["sheets"] = ("🟢 運作正常", True)
            except:
                health["sheets"] = ("❌ 找不到表格ID", False)
        
        # 測試 Drive
        drive_service = build('drive', 'v3', credentials=creds)
        drive_service.files().list(pageSize=1).execute()
        health["drive"] = ("🟢 運作正常", True)
    except Exception as e:
        # 如果是 Secrets 格式錯誤
        pass
        
    return health

# ==========================================
# 1. 側邊欄：管理中心與診斷面板
# ==========================================
st.sidebar.title("💐 尚禮坊活動管理中心")

# --- [新增] 連線功能檢測區 ---
st.sidebar.subheader("📡 系統連線診斷")
# 這裡請確保你有定義 SHEET_ID，或者讓使用者輸入
MY_SHEET_ID = "你的試算表ID寫在這裡" # <--- 請務必填入你的真實 ID

api_key = st.sidebar.text_input("🔑 Gemini API Key:", type="password")
status = check_system_health(api_key, MY_SHEET_ID)

with st.sidebar.container(border=True):
    col_a, col_b = st.columns([1, 2])
    col_a.write("**Gemini:**")
    col_b.write(status["gemini"][0])
    
    col_a.write("**Sheets:**")
    col_b.write(status["sheets"][0])
    
    col_a.write("**Drive:**")
    col_b.write(status["drive"][0])

if not all([status[k][1] for k in status]):
    st.sidebar.warning("⚠️ 請修正上述連線問題以確保數據能存入雲端。")
else:
    st.sidebar.success("✅ 所有雲端服務已就緒！")

st.sidebar.divider()

# --- 接下來是原本的建立項目與功能導覽 ---
# (保留原本的 create_project, radio 等邏輯)
