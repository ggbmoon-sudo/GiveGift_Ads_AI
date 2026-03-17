import streamlit as st
import pandas as pd
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import io

# ==========================================
# 1. 核心設定
# ==========================================
# ⚠️ 請確保這裡填入的是正確的 ID（網址中 /d/ 之後的那串）
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs" 

# ==========================================
# 2. 強健的連線診斷 (保證不崩潰)
# ==========================================
def safe_check_health(api_key, sheet_id):
    health = {"ai": "🔴", "sheets": "🔴", "drive": "🔴", "details": ""}
    
    # 檢查 Gemini
    if api_key:
        try:
            genai.configure(api_key=api_key)
            genai.list_models()
            health["ai"] = "🟢"
        except Exception as e:
            health["ai"] = "❌"
            health["details"] += f"AI Error: {str(e)}\n"
            
    # 檢查 Google 服務
    try:
        if "gcp_service_account" not in st.secrets:
            health["sheets"] = "⚠️ Secrets未設定"
        else:
            info = st.secrets["gcp_service_account"]
            creds = Credentials.from_service_account_info(info, scopes=[
                'https://www.googleapis.com/auth/spreadsheets', 
                'https://www.googleapis.com/auth/drive'
            ])
            
            # 測試 Sheets
            try:
                gc = gspread.authorize(creds)
                if sheet_id:
                    gc.open_by_key(sheet_id)
                    health["sheets"] = "🟢"
                else:
                    health["sheets"] = "❓無ID"
            except Exception as e:
                health["sheets"] = "❌"
                health["details"] += f"Sheets Error: {str(e)}\n"

            # 測試 Drive
            try:
                drive = build('drive', 'v3', credentials=creds)
                drive.files().list(pageSize=1).execute()
                health["drive"] = "🟢"
            except Exception as e:
                health["drive"] = "❌"
                health["details"] += f"Drive Error: {str(e)}\n"
    except Exception as e:
        health["details"] += f"Global Error: {str(e)}"
        
    return health

# ==========================================
# 3. 側邊欄 UI (強制渲染)
# ==========================================
st.set_page_config(page_title="GGB Ads Manager", page_icon="📊", layout="wide")
st.sidebar.title("💐 尚禮坊管理中心")

st.sidebar.subheader("📡 系統連線診斷")
user_api_key = st.sidebar.text_input("🔑 API Key:", type="password")

# 呼叫診斷
h = safe_check_health(user_api_key, MY_SHEET_ID)

# 顯示燈號
with st.sidebar.container(border=True):
    st.write(f"{h['ai']} AI | {h['sheets']} Sheets | {h['drive']} Drive")
    if h["details"]:
        with st.sidebar.expander("查看錯誤詳情"):
            st.code(h["details"])

st.sidebar.divider()

# --- 即使連線失敗，也要顯示原本的功能按鈕與選單 ---
page = st.sidebar.radio("導覽：", ["📈 數據看板", "💡 文案生成"])

# ==========================================
# 4. 主畫面邏輯
# ==========================================
st.title("🚀 尚禮坊 AI 工作站")

if h["sheets"] == "🟢":
    st.success("✅ 雲端記憶已連線，數據將自動儲存至 Google Sheets。")
    # 這裡放原本那一百多行數據分析與對話邏輯...
    # (為了排錯，我先確認你能看到燈號，若看到綠燈，我們就把原本的功能塞回這裏)
    st.info("連線成功！請告知我，我將為您補回完整的分析與圖表代碼。")
else:
    st.error("❌ 雲端連線未就緒。")
    st.write("請檢查左側『查看錯誤詳情』，如果是 **403 Forbidden**，代表您的公司帳號擋住了外部存取。")

st.divider()
st.subheader("💡 排除故障指南")
st.write("1. **確認共用**：是否有將服務帳戶 Email 加為試算表『編輯者』？")
st.write("2. **確認 ID**：`MY_SHEET_ID` 是否正確？")
st.write("3. **查看日誌**：請點擊網頁右下角 **Manage app -> Logs**，截圖裡面的紅字給我。")
