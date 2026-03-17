import streamlit as st
import pandas as pd
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from datetime import datetime
import io
import os

# ==========================================
# 0. Google 雲端連接初始化 (記憶與儲存)
# ==========================================
@st.cache_resource
def init_google_services():
    # 從 Secrets 讀取金鑰
    info = st.secrets["gcp_service_account"]
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_info(info, scopes=scope)
    gs_client = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return gs_client, drive_service

try:
    gc, drive_service = init_google_services()
    
    # 💡 關鍵修正：請在此處填入您剛剛複製的長串 ID
    SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs" 
    sh = gc.open_by_key(SHEET_ID)
    
    # 確保工作表存在 (如果沒有，自動建立)
    def get_or_create_worksheet(title, headers):
        try:
            return sh.worksheet(title)
        except:
            ws = sh.add_worksheet(title=title, rows="1000", cols=str(len(headers)))
            ws.append_row(headers)
            return ws

    ws_projects = get_or_create_worksheet("Projects", ["ID", "Name", "Drive_File_ID", "Created_At"])
    ws_chat = get_or_create_worksheet("ChatHistory", ["Project_ID", "Role", "Content", "Timestamp"])

except Exception as e:
    # 這裡會顯示具體的錯誤，讓我們知道到底發生什麼事
    st.error(f"❌ 連接失敗！錯誤原因：{e}")

# ==========================================
# 1. 核心操作函數
# ==========================================
def get_projects_from_sheet():
    data = ws_projects.get_all_records()
    return pd.DataFrame(data)

def save_new_project(name):
    p_id = str(int(datetime.now().timestamp()))
    ws_projects.append_row([p_id, name, "", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    return p_id

def save_chat_to_sheet(p_id, role, content):
    ws_chat.append_row([p_id, role, content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

def load_chat_from_sheet(p_id):
    all_history = ws_chat.get_all_records()
    return [h for h in all_history if str(h['Project_ID']) == str(p_id)]

def upload_to_drive(file_content, file_name, p_id):
    file_metadata = {'name': file_name}
    media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype='application/octet-stream')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    # 更新 Sheets 裡的檔案 ID
    cell = ws_projects.find(str(p_id))
    ws_projects.update_cell(cell.row, 3, file.get('id'))
    return file.get('id')

def download_from_drive(file_id):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh

# ==========================================
# 2. 介面設定
# ==========================================
st.set_page_config(page_title="GGB Ads Intelligence", page_icon="💐", layout="wide")
st.sidebar.title("💐 尚禮坊活動管理 (雲端版)")

# 專案選擇
with st.sidebar.expander("➕ 建立新項目"):
    new_proj = st.text_input("項目名稱")
    if st.button("確認建立"):
        if new_proj:
            save_new_project(new_proj)
            st.rerun()

df_p = get_projects_from_sheet()
if not df_p.empty:
    sel_proj = st.sidebar.selectbox("📂 選擇項目：", df_p['Name'].tolist())
    curr_data = df_p[df_p['Name'] == sel_proj].iloc[0]
    curr_pid = curr_data['ID']
    curr_fid = curr_data['Drive_File_ID']
else:
    curr_pid = None

# 模型設定
api_key = st.sidebar.text_input("🔑 API Key:", type="password")
model_v = st.sidebar.selectbox("🧠 模型:", ["gemini-2.5-flash", "gemini-2.5-pro"])
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_v)

# ==========================================
# 3. 主頁面邏輯
# ==========================================
if curr_pid:
    st.title(f"📈 項目：{sel_proj}")
    
    # 報表管理
    with st.expander("☁️ 雲端報表管理"):
        up_f = st.file_uploader("上傳報表至 Google Drive", type=['csv', 'xlsx'])
        if up_f:
            with st.spinner("正在同步至 Google Drive..."):
                upload_to_drive(up_f.getvalue(), up_f.name, curr_pid)
                st.success("報表已永久備份！")
                st.rerun()
        
        if curr_fid:
            st.info(f"✅ 已掛鉤雲端報表 (ID: {curr_fid})")
            if st.button("🗑️ 移除連結"):
                cell = ws_projects.find(str(curr_pid))
                ws_projects.update_cell(cell.row, 3, "")
                st.rerun()

    # 讀取並分析數據
    data_res = None
    if curr_fid:
        try:
            raw_data = download_from_drive(curr_fid)
            # 這裡建議套用您之前的 process_data 邏輯來顯示 KPI
            st.write("--- 報表數據已從雲端取回 ---")
        except:
            st.warning("無法從雲端取回報表，請檢查權限。")

    # 對話區域 (永久記憶)
    st.subheader("💬 AI 顧問歷史紀錄 (從 Google Sheets 提取)")
    history = load_chat_from_sheet(curr_pid)
    for h in history:
        with st.chat_message(h['Role']): st.markdown(h['Content'])

    u_input = st.chat_input("詢問 AI 顧問...")
    if u_input and api_key:
        with st.chat_message("user"): st.markdown(u_input)
        save_chat_to_sheet(curr_pid, "user", u_input)
        
        with st.chat_message("assistant"):
            # 記憶注入：將 history 轉化為背景
            context = f"我們正在討論專案：{sel_proj}\n歷史對話：{str(history[-5:])}\n目前問題：{u_input}"
            res = model.generate_content(context)
            st.markdown(res.text)
            save_chat_to_sheet(curr_pid, "assistant", res.text)
            st.rerun()
else:
    st.info("請先在左側建立專案。")
