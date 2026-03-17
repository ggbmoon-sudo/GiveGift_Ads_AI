import streamlit as st
import pandas as pd
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import io
from PIL import Image

# ==========================================
# 1. 核心設定 (鎖定您的專屬 Sheet ID)
# ==========================================
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs"

# 核心 Prompt：鎖定尚禮坊專家身份，強制要求表格與粗體排版
SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告顧問。
你具備分析數據、策劃行銷活動與審核素材的專業能力。

【排版規範】：
1. 表達必須精確、清晰，關鍵數據與核心策略必須使用 **粗體** 突顯。
2. 必須大量使用「表格 (Markdown Tables)」與「條列式 (Bullet points)」呈現資訊。
3. 廣告活動企劃必須詳細包含：目標對象、投放時間、預算分配、平台選擇、核心文案。

【品牌定位】：尚禮坊是香港領先的高端禮品與花藝品牌，語氣應專業且具質感。"""

# ==========================================
# 2. 安全認證與表格初始化
# ==========================================
def get_creds():
    if "gcp_service_account" not in st.secrets: return None
    info = dict(st.secrets["gcp_service_account"])
    if "private_key" in info:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    return Credentials.from_service_account_info(info, scopes=[
        'https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'
    ])

# ==========================================
# 3. 側邊欄 UI
# ==========================================
st.set_page_config(page_title="GGB Ads Consultant", page_icon="💐", layout="wide")
st.sidebar.title("💐 專案管理中心")

api_key = None
try:
    creds = get_creds()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(MY_SHEET_ID)
    st.sidebar.success("🟢 雲端記憶已連線")
    st.sidebar.markdown(f"🔗 [點此打開雲端表格]({sh.url})")

    # 動態擴展欄位函數
    def get_ws(title, head):
        try:
            ws = sh.worksheet(title)
            if ws.col_count < len(head): ws.add_cols(len(head) - ws.col_count)
            return ws
        except:
            w = sh.add_worksheet(title=title, rows="1000", cols=len(head))
            w.insert_row(head, 1); return w

    ws_p = get_ws("Projects", ["ID", "Name", "Created"])
    ws_c = get_ws("ChatHistory", ["PID", "Role", "Content", "Time", "Remark"])
    ws_set = get_ws("Settings", ["Key", "Value"])

    # 從 Sheet 安全載入 API Key
    set_data = ws_set.get_all_records()
    api_key_row = next((r for r in set_data if r['Key'] == 'API_KEY'), None)
    if api_key_row and api_key_row['Value']:
        api_key = str(api_key_row['Value']).strip()
        st.sidebar.info("🔑 API Key 已從雲端安全載入")
    else:
        st.sidebar.warning("⚠️ 尚未設定 API Key")
        new_key = st.sidebar.text_input("輸入 API Key 存入雲端:", type="password")
        if st.sidebar.button("💾 儲存金鑰") and new_key:
            ws_set.insert_row(["API_KEY", new_key], 2)
            st.rerun()

    # 項目管理
    projs = ws_p.get_all_records()
    if projs:
        sel_name = st.sidebar.selectbox("📂 選擇項目：", [p['Name'] for p in projs])
        curr_p = next(p for p in projs if p['Name'] == sel_name)
    else: curr_p = None

    with st.sidebar.expander("➕ 建立新項目"):
        n = st.text_input("活動名稱")
        if st.button("確認建立") and n:
            ws_p.insert_row([str(int(datetime.now().timestamp())), n, datetime.now().strftime("%Y-%m-%d")], 2)
            st.rerun()
            
    if curr_p:
        with st.sidebar.expander("⚙️ 項目設定"):
            if st.button("🗑️ 刪除當前項目", type="primary"):
                cell = ws_p.find(str(curr_p['ID']))
                ws_p.delete_rows(cell.row); st.rerun()

except Exception as e:
    st.sidebar.error(f"🔴 連線失敗: {e}"); curr_p = None

# 鎖定模型版本
model_v = st.sidebar.selectbox("🧠 模型版本:", ["gemini-2.5-flash", "gemini-2.5-pro"])

# ==========================================
# 4. 主畫面邏輯
# ==========================================
if curr_p:
    st.title(f"📈 項目：{curr_p['Name']}")
    
    with st.expander("📎 上傳分析文件", expanded=False):
        up_f = st.file_uploader("支援 CSV, XLSX, PDF, Image", type=['csv', 'xlsx', 'pdf', 'jpg', 'png'])
        file_ctx = ""
        if up_f:
            if up_f.name.lower().endswith(('.csv', '.xlsx')):
                df = pd.read_csv(up_f) if up_f.name.endswith('.csv') else pd.read_excel(up_f)
                file_ctx = f"文件數據摘要: {df.head(5).to_string()}\n"
            elif up_f.name.lower().endswith(('.jpg', '.png', '.jpeg')):
                img = Image.open(up_f); st.image(img, width=300)
                st.session_state.active_img = img; file_ctx = "【使用者上傳了圖片素材】"

    st.subheader("🤖 AI 快捷指令")
    if "btn_q" not in st.session_state: st.session_state.btn_q = None
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("📊 成效分析"): st.session_state.btn_q = "請用表格分析數據成效，並用粗體標示重點。"
    if c2.button("📝 生成廣告企劃"): st.session_state.btn_q = "請生成詳細廣告企劃表格，包含對象、時間、預算、平台、文案。"
    if c3.button("🎨 素材審核"): st.session_state.btn_q = "請審核圖片素材，給予配色與構圖建議。"
    if c4.button("📋 總結與建議", type="primary"): st.session_state.btn_q = "請回顧對話，生成專案總結與最新的下一步優化建議。"

    st.divider()

    # 顯示歷史與備註功能
    all_chat = ws_c.get_all_records()
    p_chat = []
    for idx, row in enumerate(all_chat):
        if str(row['PID']) == str(curr_p['ID']):
            row['real_row'] = idx + 2; p_chat.append(row)

    for m in reversed(p_chat):
        with st.chat_message(m['Role'].lower()):
            st.markdown(m['Content'])
            if m.get('Remark'): st.info(f"📌 **備註:** {m['Remark']}")
            if m['Role'] == 'Assistant':
                new_rmk = st.text_input("📝 編輯備註", value=m.get('Remark',''), key=f"r_{m['real_row']}")
                if new_rmk != m.get('Remark',''):
                    ws_c.update_cell(m['real_row'], 5, new_rmk); st.rerun()

    u_input = st.chat_input("詢問顧問...")
    final_q = st.session_state.btn_query if hasattr(st.session_state, 'btn_query') and st.session_state.btn_query else u_input

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
                st.session_state.btn_query = None; st.rerun()
            except Exception as e: st.error(f"生成失敗: {e}")
else:
    st.info("請在左側建立項目開始。")
