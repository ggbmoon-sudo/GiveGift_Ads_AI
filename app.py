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
# 1. 核心設定 (請填寫您的試算表 ID)
# ==========================================
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs" 

# ==========================================
# 2. 系統診斷與初始化
# ==========================================
def get_system_status(api_key, sheet_id):
    health = {"gemini": "🔴", "sheets": "🔴", "drive": "🔴", "all_ok": False}
    try:
        if api_key:
            genai.configure(api_key=api_key)
            genai.list_models()
            health["gemini"] = "🟢"
        
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        
        gc = gspread.authorize(creds)
        if sheet_id:
            gc.open_by_key(sheet_id)
            health["sheets"] = "🟢"
        
        drive = build('drive', 'v3', credentials=creds)
        drive.files().list(pageSize=1).execute()
        health["drive"] = "🟢"
        
        if health["gemini"] == "🟢" and health["sheets"] == "🟢":
            health["all_ok"] = True
    except: pass
    return health

# --- Google Sheets 操作工具 ---
@st.cache_resource
def get_google_clients():
    info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
    return gspread.authorize(creds), build('drive', 'v3', credentials=creds)

# ==========================================
# 3. 側邊欄 UI
# ==========================================
st.set_page_config(page_title="GGB Ads Intelligence", page_icon="📊", layout="wide")
st.sidebar.title("💐 尚禮坊管理中心")

st.sidebar.subheader("📡 系統連線診斷")
api_key = st.sidebar.text_input("🔑 API Key:", type="password")
h = get_system_status(api_key, MY_SHEET_ID)
st.sidebar.write(f"{h['gemini']} AI | {h['sheets']} Sheets | {h['drive']} Drive")

if not h["all_ok"]:
    st.sidebar.warning("⚠️ 請確認 API Key 及 Sheets 共用權限")

st.sidebar.divider()
selected_model = st.sidebar.selectbox("🧠 模型:", ["gemini-2.5-flash", "gemini-2.5-pro"])

# 只有連線成功才載入數據
if h["all_ok"]:
    gc, drive_service = get_google_clients()
    sh = gc.open_by_key(MY_SHEET_ID)
    
    # 確保工作表存在
    def get_ws(title, head):
        try: return sh.worksheet(title)
        except: 
            w = sh.add_worksheet(title=title, rows="1000", cols=len(head))
            w.append_row(head); return w
    
    ws_p = get_ws("Projects", ["ID", "Name", "Drive_ID", "Created"])
    ws_c = get_ws("ChatHistory", ["PID", "Role", "Content", "Time"])

    # 項目管理
    with st.sidebar.expander("➕ 建立新項目"):
        new_p = st.text_input("項目名稱")
        if st.button("確認建立") and new_p:
            pid = str(int(datetime.now().timestamp()))
            ws_p.append_row([pid, new_p, "", datetime.now().strftime("%Y-%m-%d")])
            st.rerun()

    projs = ws_p.get_all_records()
    if projs:
        p_names = [r['Name'] for r in projs]
        sel_name = st.sidebar.selectbox("📂 選擇項目：", p_names)
        curr_p = next(r for r in projs if r['Name'] == sel_name)
    else: curr_p = None
else: curr_p = None

page = st.sidebar.radio("導覽：", ["📈 數據看板", "💡 文案生成"])

# ==========================================
# 4. 數據處理核心
# ==========================================
def process_data(file_content, is_csv=True):
    try:
        df = pd.read_csv(io.BytesIO(file_content), skiprows=2) if is_csv else pd.read_excel(io.BytesIO(file_content))
        df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
        def clean(v): return float(str(v).replace('$', '').replace(',', '').strip()) if not pd.isna(v) and str(v) != '--' else 0.0
        
        res = {"df": df, "cost": 0.0, "clicks": 0, "convs": 0}
        for col in df.columns:
            c = col.lower()
            if '費用' in c and '平均' not in c: res['cost'] = df[col].apply(clean).sum()
            if '點擊' in c and '率' not in c: res['clicks'] = int(df[col].apply(clean).sum())
            if '轉換' in c and not any(ex in c for ex in ['價值','率']): res['convs'] = int(df[col].apply(clean).sum())
        return res
    except: return None

# ==========================================
# 5. 主畫面：數據看板
# ==========================================
if curr_p and h["all_ok"]:
    st.title(f"📈 項目：{curr_p['Name']}")
    
    # 雲端報表
    with st.expander("☁️ 報表管理"):
        up_f = st.file_uploader("上傳報表至 Drive", type=['csv', 'xlsx'])
        if up_f:
            media = MediaIoBaseUpload(io.BytesIO(up_f.getvalue()), mimetype='application/octet-stream')
            f_drive = drive_service.files().create(body={'name': up_f.name}, media_body=media, fields='id').execute()
            # 更新 Sheets
            cell = ws_p.find(str(curr_p['ID']))
            ws_p.update_cell(cell.row, 3, f_drive.get('id'))
            st.success("已備份至雲端"); st.rerun()

    # 顯示數據與對話
    st.divider()
    
    # 快捷鍵
    st.subheader("🤖 AI 快捷指令")
    c1, c2, c3, c4 = st.columns(4)
    q = None
    if c1.button("📊 分析成效"): q = "請分析目前數據的成效亮點與缺點。"
    if c2.button("🚀 提高轉換"): q = "請給予具體策略提升轉換率。"
    if c3.button("🧠 深度診斷"): q = "執行全自動深度診斷，找出預算浪費點。"
    if c4.button("📈 生成圖表"): st.info("圖表生成功能已就緒，請在下方詢問具體圖表需求。")

    # 顯示歷史
    history = ws_c.get_all_records()
    curr_history = [h for h in history if str(h['PID']) == str(curr_p['ID'])]
    for m in curr_history:
        with st.chat_message(m['Role'].lower()): st.markdown(m['Content'])

    # 輸入
    u_input = st.chat_input("詢問顧問...")
    final_q = q if q else u_input

    if final_q and api_key:
        with st.chat_message("user"): st.markdown(final_q)
        ws_c.append_row([curr_p['ID'], "User", final_q, datetime.now().strftime("%H:%M")])
        
        with st.chat_message("assistant"):
            model = genai.GenerativeModel(selected_model)
            res = model.generate_content(f"專案:{curr_p['Name']}\n問題:{final_q}")
            st.markdown(res.text)
            ws_c.append_row([curr_p['ID'], "Assistant", res.text, datetime.now().strftime("%H:%M")])
            st.rerun()
else:
    st.info("請在左側診斷連線並建立項目。")
