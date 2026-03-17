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
# 1. 核心設定
# ==========================================
# 💡 請填入您試算表網址中 /d/ 之後的那串長亂碼
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs" 

SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告顧問。
請保持專業且人性化的語氣。如果提供報表，請根據數據分析；
如果沒有報表，請根據尚禮坊的高端花藝與禮品品牌定位給予策略建議。"""

# ==========================================
# 2. 核心連線邏輯 (含 PEM 格式修復)
# ==========================================
def get_service_creds():
    """從 Secrets 讀取並修正 PEM 格式錯誤"""
    if "gcp_service_account" not in st.secrets:
        return None
    
    # 將 Secrets 轉為字典並強制修復私鑰中的換行符
    info = dict(st.secrets["gcp_service_account"])
    if "private_key" in info:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    return Credentials.from_service_account_info(info, scopes=scope)

def check_system_health(api_key, sheet_id):
    """診斷各項服務連線狀態"""
    health = {"ai": "🔴", "sheets": "🔴", "drive": "🔴", "error": ""}
    
    # 測試 Gemini
    if api_key:
        try:
            genai.configure(api_key=api_key)
            genai.list_models()
            health["ai"] = "🟢"
        except Exception as e:
            health["ai"] = "❌"; health["error"] += f"AI: {str(e)}\n"

    # 測試 Google 服務
    try:
        creds = get_service_creds()
        if not creds:
            health["sheets"] = "❓ Secrets未設定"
        else:
            # Sheets 測試
            try:
                gc = gspread.authorize(creds)
                gc.open_by_key(sheet_id)
                health["sheets"] = "🟢"
            except Exception as e:
                health["sheets"] = "❌"; health["error"] += f"Sheets: {str(e)}\n"
            # Drive 測試
            try:
                build('drive', 'v3', credentials=creds).files().list(pageSize=1).execute()
                health["drive"] = "🟢"
            except Exception as e:
                health["drive"] = "❌"; health["error"] += f"Drive: {str(e)}\n"
    except Exception as e:
        health["error"] += f"系統認證錯誤: {str(e)}"
    return health

# ==========================================
# 3. 側邊欄：診斷燈號與項目管理
# ==========================================
st.set_page_config(page_title="GGB Ads Consultant", page_icon="💐", layout="wide")
st.sidebar.title("💐 專案管理中心")

# --- 📡 連線診斷區 ---
st.sidebar.subheader("📡 系統連線診斷")
user_api_key = st.sidebar.text_input("🔑 Gemini API Key:", type="password")
h = check_system_health(user_api_key, MY_SHEET_ID)

with st.sidebar.container(border=True):
    st.write(f"{h['ai']} **AI** | {h['sheets']} **Sheets** | {h['drive']} **Drive**")
    if h["error"]:
        with st.sidebar.expander("🔍 查看詳細錯誤"):
            st.code(h["error"])
    elif h["sheets"] == "🟢":
        st.sidebar.success("✅ 雲端記憶已就緒")

st.sidebar.divider()

# --- 📂 雲端項目與對話邏輯 ---
if h["sheets"] == "🟢":
    creds = get_service_creds()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(MY_SHEET_ID)

    def get_ws(title, headers):
        try: return sh.worksheet(title)
        except: 
            w = sh.add_worksheet(title=title, rows="1000", cols=len(headers))
            w.append_row(headers); return w

    ws_p = get_ws("Projects", ["ID", "Name", "Created_At"])
    ws_c = get_ws("ChatHistory", ["PID", "Role", "Content", "Time"])

    # 取得項目列表
    projects = ws_p.get_all_records()
    p_names = [p['Name'] for p in projects]

    with st.sidebar.expander("➕ 建立新項目"):
        new_name = st.text_input("輸入活動名稱")
        if st.button("確認建立") and new_name:
            ws_p.append_row([str(int(datetime.now().timestamp())), new_name, datetime.now().strftime("%Y-%m-%d")])
            st.rerun()

    if p_names:
        sel_p_name = st.sidebar.selectbox("📂 選擇目前項目：", p_names)
        curr_p = next(p for p in projects if p['Name'] == sel_p_name)
    else: curr_p = None
else:
    st.sidebar.warning("請先修正 Google 連線問題")
    curr_p = None

model_choice = st.sidebar.selectbox("🧠 AI 模型:", ["gemini-2.5-flash", "gemini-2.5-pro"])

# ==========================================
# 4. 主畫面：數據看板與對話
# ==========================================
if curr_p:
    st.title(f"📈 項目：{curr_p['Name']}")
    
    # 快捷指令
    if "chat_query" not in st.session_state: st.session_state.chat_query = None

    st.subheader("🤖 快捷優化指令")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("📊 成效分析"): st.session_state.chat_query = "請分析此廣告活動成效。"
    if c2.button("🚀 提高轉換"): st.session_state.chat_query = "有什麼策略能提高轉換率？"
    if c3.button("🧠 深度診斷"): st.session_state.chat_query = "執行全自動深度診斷。"
    if c4.button("📈 生成圖表"): st.session_state.chat_query = "請根據目前數據生成可視化圖表分析。"

    st.divider()

    # 顯示雲端對話歷史
    history_records = ws_c.get_all_records()
    p_history = [m for m in history_records if str(m['PID']) == str(curr_p['ID'])]
    
    for m in p_history:
        with st.chat_message(m['Role'].lower()):
            st.markdown(m['Content'])

    # 處理輸入
    u_input = st.chat_input("詢問 AI 顧問...")
    final_q = st.session_state.chat_query if st.session_state.chat_query else u_input

    if final_q and user_api_key:
        with st.chat_message("user"):
            st.markdown(final_q)
        # 存入 Google Sheets
        ws_c.append_row([str(curr_p['ID']), "User", final_q, datetime.now().strftime("%H:%M")])
        
        with st.chat_message("assistant"):
            try:
                genai.configure(api_key=user_api_key)
                model = genai.GenerativeModel(model_choice, system_instruction=SYSTEM_PROMPT)
                # 注入上下文
                ctx = f"正在討論項目: {curr_p['Name']}\n問題: {final_q}"
                res = model.generate_content(ctx)
                st.markdown(res.text)
                # 存入 Google Sheets
                ws_c.append_row([str(curr_p['ID']), "Assistant", res.text, datetime.now().strftime("%H:%M")])
            except Exception as e:
                st.error(f"AI 生成失敗: {e}")
        
        st.session_state.chat_query = None
        st.rerun()
else:
    st.info("請在左側診斷連線並建立或選擇一個項目開始。")
