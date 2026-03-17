import streamlit as st
import pandas as pd
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import io
import os
from PIL import Image

# ==========================================
# 1. 核心設定 (請確認 ID)
# ==========================================
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs"

SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告顧問。
你具備分析廣告數據、策劃行銷活動與審核素材的專業能力。
【重點排版要求】：
1. 表達必須清晰、直白。
2. 關鍵字、重要數據與策略必須使用 **粗體** 突顯。
3. 盡多使用「表格 (Markdown Tables)」與「條列式」呈現。
4. 廣告活動企劃必須包含：目標對象、投放時間、預算建議、平台選擇、核心文案。"""

# ==========================================
# 2. 認證與修復邏輯
# ==========================================
def get_creds():
    if "gcp_service_account" not in st.secrets: return None
    info = dict(st.secrets["gcp_service_account"])
    if "private_key" in info:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    return Credentials.from_service_account_info(info, scopes=scope)

# ==========================================
# 3. 數據解析工具
# ==========================================
def process_data(file):
    try:
        df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
        df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
        def clean(v):
            s = str(v).replace('$', '').replace(',', '').replace('%', '').strip()
            return float(s) if s not in ['--', '', 'nan'] else 0.0
        res = {"cost": 0.0, "clicks": 0, "convs": 0}
        df_clean = df[~df.iloc[:, 0].astype(str).str.contains('總計|Total|總和', na=False)].copy()
        for col in df_clean.columns:
            c_low = col.lower()
            if ('費用' in c_low or 'cost' in c_low) and not any(ex in c_low for ex in ['平均','每','avg']):
                res['cost'] = df_clean[col].apply(clean).sum()
            if '點擊' in c_low and '率' not in c_low: res['clicks'] = int(df_clean[col].apply(clean).sum())
            if '轉換' in c_low and not any(ex in c_low for ex in ['價值','率','費用']): res['convs'] = int(df_clean[col].apply(clean).sum())
        return res, df_clean
    except: return None, None

# ==========================================
# 4. 側邊欄 UI
# ==========================================
st.set_page_config(page_title="GGB Ads Consultant", page_icon="💐", layout="wide")
st.sidebar.title("💐 專案管理中心")

api_key = None

try:
    creds = get_creds()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(MY_SHEET_ID)
    st.sidebar.success("🟢 雲端記憶已連線")
    st.sidebar.markdown(f"🔗 [打開雲端表格]({sh.url})")

    # 【核心修正】：自動檢查並擴展欄位數量的函數
    def get_ws(title, head):
        try:
            ws = sh.worksheet(title)
            # 檢查欄位數是否足夠存放 header
            if ws.col_count < len(head):
                ws.add_cols(len(head) - ws.col_count)
            # 檢查第一列是否與 header 一致
            current_head = ws.row_values(1)
            if current_head != head:
                for i, h_val in enumerate(head):
                    ws.update_cell(1, i + 1, h_val)
            return ws
        except: 
            w = sh.add_worksheet(title=title, rows="1000", cols=len(head))
            w.insert_row(head, 1)
            return w

    ws_p = get_ws("Projects", ["ID", "Name", "Created"])
    ws_c = get_ws("ChatHistory", ["PID", "Role", "Content", "Time", "Remark"])
    ws_set = get_ws("Settings", ["Key", "Value"])

    # 安全載入 API Key
    set_data = ws_set.get_all_records()
    api_key_row = next((r for r in set_data if r['Key'] == 'API_KEY'), None)

    if api_key_row and api_key_row['Value']:
        api_key = str(api_key_row['Value']).strip()
        st.sidebar.info("🔑 API Key 已安全載入")
    else:
        st.sidebar.warning("⚠️ 尚未設定 API Key")
        new_key = st.sidebar.text_input("輸入全新的 API Key:", type="password")
        if st.sidebar.button("💾 儲存至雲端") and new_key:
            ws_set.insert_row(["API_KEY", new_key], 2)
            st.rerun()

    # 專案列表
    projs = ws_p.get_all_records()
    p_names = [p['Name'] for p in projs]
    if p_names:
        sel_name = st.sidebar.selectbox("📂 選擇項目：", p_names)
        curr_p = next(p for p in projs if p['Name'] == sel_name)
    else: curr_p = None

    with st.sidebar.expander("➕ 建立新項目"):
        new_n = st.text_input("項目名稱")
        if st.button("確認建立") and new_n:
            ws_p.insert_row([str(int(datetime.now().timestamp())), new_n, datetime.now().strftime("%Y-%m-%d")], 2)
            st.rerun()
            
    if curr_p:
        with st.sidebar.expander("⚙️ 項目設定"):
            if st.button("🗑️ 刪除項目", type="primary"):
                cell = ws_p.find(str(curr_p['ID']))
                ws_p.delete_rows(cell.row)
                st.rerun()

except Exception as e:
    st.sidebar.error(f"🔴 連線失敗: {e}")
    curr_p = None

model_v = st.sidebar.selectbox("🧠 模型:", ["gemini-2.0-flash", "gemini-2.0-pro"])

# ==========================================
# 5. 主畫面功能
# ==========================================
if curr_p:
    st.title(f"📈 項目：{curr_p['Name']}")
    
    with st.expander("📎 上傳分析文件", expanded=False):
        up_file = st.file_uploader("支援 CSV, XLSX, PDF, Image", type=['csv', 'xlsx', 'pdf', 'jpg', 'png'])
        file_ctx = ""
        if up_file:
            if up_file.name.lower().endswith(('.csv', '.xlsx')):
                data_res, df = process_data(up_file)
                if data_res:
                    k1, k2, k3 = st.columns(3)
                    k1.metric("花費", f"${data_res['cost']:,.1f}")
                    k2.metric("點擊", f"{data_res['clicks']:,}")
                    k3.metric("轉換", f"{data_res['convs']:,}")
                    file_ctx = f"報表數據摘要: {str(data_res)}\n"
            elif up_file.name.lower().endswith(('.jpg', '.png', '.jpeg')):
                img = Image.open(up_file)
                st.image(img, caption="素材預覽", width=300)
                st.session_state.active_img = img
                file_ctx = "【使用者上傳了圖片素材】"

    st.subheader("🤖 AI 快捷指令")
    if "btn_query" not in st.session_state: st.session_state.btn_query = None
    
    col1, col2, col3, col4 = st.columns(4)
    if col1.button("📊 成效分析"): st.session_state.btn_query = "請分析目前數據成效，重點粗體，多用表格。"
    if col2.button("📝 生成廣告企劃"): st.session_state.btn_query = "請生成詳細廣告企劃表格，包含對象、時間、預算、平台、文案。"
    if col3.button("🎨 素材審核"): st.session_state.btn_query = "請審核圖片素材，針對配色構圖給予建議。"
    if col4.button("📋 總結與建議", type="primary"): st.session_state.btn_query = "總結當前專案狀況並給予最新建議。"

    st.divider()

    # 讀取並顯示歷史與備註
    all_chat = ws_c.get_all_records()
    p_chat = [m for m in all_chat if str(m['PID']) == str(curr_p['ID'])]
    # 獲取 row index 以便更新備註
    p_chat_rows = []
    for idx, row in enumerate(all_chat):
        if str(row['PID']) == str(curr_p['ID']):
            row['real_row'] = idx + 2
            p_chat_rows.append(row)

    for m in reversed(p_chat_rows):
        with st.chat_message(m['Role'].lower()):
            st.markdown(m['Content'])
            if m.get('Remark'): st.info(f"📌 **備註:** {m['Remark']}")
            if m['Role'] == 'Assistant':
                new_rmk = st.text_input("📝 備註", value=m.get('Remark',''), key=f"r_{m['real_row']}")
                if new_rmk != m.get('Remark',''):
                    ws_c.update_cell(m['real_row'], 5, new_rmk)
                    st.rerun()

    u_input = st.chat_input("詢問顧問...")
    final_q = st.session_state.btn_query if st.session_state.btn_query else u_input

    if final_q and api_key:
        with st.chat_message("user"): st.markdown(final_q)
        ws_c.insert_row([str(curr_p['ID']), "User", final_q, datetime.now().strftime("%H:%M"), ""], 2)
        with st.chat_message("assistant"):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(model_v, system_instruction=SYSTEM_PROMPT)
                payload = [f"專案:{curr_p['Name']}\n{file_ctx}\n問題:{final_q}"]
                if "active_img" in st.session_state: payload.append(st.session_state.active_img)
                res = model.generate_content(payload)
                st.markdown(res.text)
                ws_c.insert_row([str(curr_p['ID']), "Assistant", res.text, datetime.now().strftime("%H:%M"), ""], 2)
                st.session_state.btn_query = None
                st.rerun()
            except Exception as e: st.error(f"生成失敗: {e}")
else:
    st.info("請在左側選擇項目開始。")
