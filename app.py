import streamlit as st
import pandas as pd
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import io
import os
from PIL import Image

# ==========================================
# 1. 核心設定
# ==========================================
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs" 

SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告顧問。
你具備分析數據、閱讀文件與審核廣告圖片的能力。
請根據使用者提供的資料（報表、PDF或圖片）給予精準、高端且具執行力的建議。"""

# ==========================================
# 2. 認證與診斷邏輯 (含 PEM 修復)
# ==========================================
def get_service_creds():
    if "gcp_service_account" not in st.secrets: return None
    info = dict(st.secrets["gcp_service_account"])
    if "private_key" in info:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    return Credentials.from_service_account_info(info, scopes=scope)

def check_health(api_key, sheet_id):
    results = {"ai": "🔴", "sheets": "🔴", "drive": "🔴", "error": ""}
    if api_key:
        try:
            genai.configure(api_key=api_key)
            genai.list_models(); results["ai"] = "🟢"
        except Exception as e: results["ai"] = "❌"; results["error"] += f"AI: {str(e)}\n"
    try:
        creds = get_service_creds()
        if creds:
            gc = gspread.authorize(creds)
            gc.open_by_key(sheet_id); results["sheets"] = "🟢"
            build('drive', 'v3', credentials=creds).files().list(pageSize=1).execute(); results["drive"] = "🟢"
    except Exception as e: results["sheets"] = "❌"; results["error"] += f"Google: {str(e)}\n"
    return results

# ==========================================
# 3. 數據解析工具 (Excel, CSV, PDF, Image)
# ==========================================
def process_spreadsheet(file):
    try:
        df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
        df.columns = [str(c).strip() for c in df.columns]
        def clean(v): return float(str(v).replace('$', '').replace(',', '').strip()) if not pd.isna(v) and str(v) != '--' else 0.0
        res = {"cost": 0.0, "clicks": 0, "convs": 0}
        for col in df.columns:
            c = col.lower()
            if '費用' in c and '平均' not in c: res['cost'] = df[col].apply(clean).sum()
            if '點擊' in c and '率' not in c: res['clicks'] = int(df[col].apply(clean).sum())
            if '轉換' in c and not any(ex in c for ex in ['價值','率']): res['convs'] = int(df[col].apply(clean).sum())
        return res, df
    except: return None, None

# ==========================================
# 4. 側邊欄 UI
# ==========================================
st.set_page_config(page_title="GGB Ads Intelligence", page_icon="💐", layout="wide")
st.sidebar.title("💐 專案管理中心")

st.sidebar.subheader("📡 系統連線診斷")
user_api_key = st.sidebar.text_input("🔑 API Key:", type="password")
h = check_health(user_api_key, MY_SHEET_ID)

with st.sidebar.container(border=True):
    st.write(f"{h['ai']} AI | {h['sheets']} Sheets | {h['drive']} Drive")
    if h["error"]:
        with st.sidebar.expander("🔍 錯誤詳情"): st.code(h["error"])

st.sidebar.divider()

if h["sheets"] == "🟢":
    creds = get_service_creds()
    gc = gspread.authorize(creds); sh = gc.open_by_key(MY_SHEET_ID)
    def get_ws(title, head):
        try: return sh.worksheet(title)
        except: 
            w = sh.add_worksheet(title=title, rows="1000", cols=len(head))
            w.insert_row(head, 1); return w
    ws_p = get_ws("Projects", ["ID", "Name", "Created"])
    ws_c = get_ws("ChatHistory", ["PID", "Role", "Content", "Time"])

    with st.sidebar.expander("➕ 建立新項目"):
        new_name = st.text_input("活動名稱")
        if st.button("確認建立") and new_name:
            ws_p.insert_row([str(int(datetime.now().timestamp())), new_name, datetime.now().strftime("%Y-%m-%d")], 2)
            st.rerun()

    projs = ws_p.get_all_records()
    if projs:
        sel_name = st.sidebar.selectbox("📂 選擇項目：", [p['Name'] for p in projs])
        curr_p = next(p for p in projs if p['Name'] == sel_name)
    else: curr_p = None
else:
    curr_p = None

model_v = st.sidebar.selectbox("🧠 模型:", ["gemini-2.5-flash", "gemini-2.5-pro"])

# ==========================================
# 5. 主畫面：文件上傳與對話
# ==========================================
if curr_p:
    st.title(f"📈 項目：{curr_p['Name']}")
    
    # --- 📁 文件上傳區 (Excel, CSV, PDF, JPG) ---
    with st.expander("📎 上傳分析文件 (報表、企劃、廣告圖)", expanded=True):
        uploaded_file = st.file_uploader("支援：XLSX, CSV, PDF, JPG, PNG", type=['csv', 'xlsx', 'pdf', 'jpg', 'png', 'jpeg'])
        file_ctx = ""
        
        if uploaded_file:
            st.toast(f"已讀取文件: {uploaded_file.name}")
            # 1. 處理試算表
            if uploaded_file.name.endswith(('.csv', '.xlsx')):
                kpi, df = process_spreadsheet(uploaded_file)
                if kpi:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("花費", f"${kpi['cost']:,.1f}"); c2.metric("點擊", f"{kpi['clicks']:,}"); c3.metric("轉換", f"{kpi['convs']:,}")
                    file_ctx = f"報表數據: {str(kpi)}\n前5行數據: {df.head(5).to_string()}"
            
            # 2. 處理圖片 (Gemini Vision)
            elif uploaded_file.name.lower().endswith(('.jpg', '.png', '.jpeg')):
                img = Image.open(uploaded_file)
                st.image(img, caption="待分析廣告素材", width=300)
                st.session_state.temp_img = img # 存入 session 供 AI 讀取
                file_ctx = "【使用者上傳了一張圖片，請針對圖片視覺內容給予建議】"

    st.divider()

    # --- 🤖 快捷鍵與對話 ---
    st.subheader("💬 AI 優化顧問")
    c1, c2, c3, c4 = st.columns(4)
    q = None
    if c1.button("📊 成效分析"): q = "請根據目前提供的報表或文件分析成效。"
    if c2.button("🚀 提高轉換"): q = "請給予具體策略，告訴我如何提高轉換率？"
    if c3.button("🧠 深度診斷"): q = "請進行地毯式診斷，找出潛在問題。"
    if c4.button("🎨 審核素材"): q = "請分析我上傳的廣告圖片，從構圖、配色與文案給予改進建議。"

    # 顯示雲端歷史 (從 Sheets 抓取)
    history = ws_c.get_all_records()
    p_history = [m for m in history if str(m['PID']) == str(curr_p['ID'])]
    for m in p_history:
        with st.chat_message(m['Role'].lower()): st.markdown(m['Content'])

    u_input = st.chat_input("輸入問題或針對文件提問...")
    final_q = q if q else u_input

    if final_q and user_api_key:
        with st.chat_message("user"): st.markdown(final_q)
        ws_c.insert_row([str(curr_p['ID']), "User", final_q, datetime.now().strftime("%H:%M")], 2)
        
        with st.chat_message("assistant"):
            genai.configure(api_key=user_api_key)
            model = genai.GenerativeModel(model_v, system_instruction=SYSTEM_PROMPT)
            
            # 準備發送給 AI 的內容
            content_list = [f"專案:{curr_p['Name']}\n{file_ctx}\n問題:{final_q}"]
            if "temp_img" in st.session_state and "🎨" in final_q or "圖片" in final_q:
                content_list.append(st.session_state.temp_img)
            
            res = model.generate_content(content_list)
            st.markdown(res.text)
            ws_c.insert_row([str(curr_p['ID']), "Assistant", res.text, datetime.now().strftime("%H:%M")], 2)
            st.rerun()
else:
    st.info("請在左側診斷連線並建立項目。")
