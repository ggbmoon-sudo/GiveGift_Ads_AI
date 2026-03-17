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
# 1. 核心設定 (已鎖定您的 Sheet ID)
# ==========================================
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs"
DEFAULT_API_KEY = "AIzaSyB9trwKZyd1xNFJejlNs4gOxi8dcolI6Xw"

# 強化版的 System Prompt：強調圖表、清晰度與重點突顯
SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告顧問。
你具備分析廣告數據、策劃行銷活動與審核素材的專業能力。
【重點排版要求】：
1. 表達必須非常清晰、直白，絕不冗長。
2. 關鍵字、重要數據與核心策略必須使用 **粗體** 突顯。
3. 強烈要求：盡可能多使用「表格 (Markdown Tables)」與「條列式 (Bullet points)」來呈現你的建議、參數、排程與數據對比。
4. 所有的廣告活動企劃，必須嚴謹包含：目標對象、投放時間、預算建議、平台選擇、核心文案。"""

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
# 4. 側邊欄 UI：系統連線與設定
# ==========================================
st.set_page_config(page_title="GGB Ads Consultant", page_icon="💐", layout="wide")
st.sidebar.title("💐 專案管理中心")

try:
    creds = get_creds()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(MY_SHEET_ID)
    st.sidebar.success("🟢 雲端記憶已連線")
    st.sidebar.markdown(f"🔗 [點此打開雲端資料庫]({sh.url})")

    # 工作表初始化與欄位修正
    def get_ws(title, head):
        try: return sh.worksheet(title)
        except: 
            w = sh.add_worksheet(title=title, rows="100", cols=len(head))
            w.insert_row(head, 1); return w

    ws_p = get_ws("Projects", ["ID", "Name", "Created"])
    ws_c = get_ws("ChatHistory", ["PID", "Role", "Content", "Time", "Remark"])
    ws_set = get_ws("Settings", ["Key", "Value"])

    # 確保 ChatHistory 有 Remark 欄位 (舊表升級)
    headers = ws_c.row_values(1)
    if len(headers) < 5 or headers[4] != 'Remark':
        ws_c.update_cell(1, 5, "Remark")

    # 自動讀取或寫入 API Key
    set_data = ws_set.get_all_records()
    api_key = next((r['Value'] for r in set_data if r['Key'] == 'API_KEY'), None)
    if not api_key:
        ws_set.insert_row(["API_KEY", DEFAULT_API_KEY], 2)
        api_key = DEFAULT_API_KEY
    st.sidebar.info("🔑 API Key 已自動從雲端載入")

    # 專案列表
    projs = ws_p.get_all_records()
    p_names = [p['Name'] for p in projs]
    
    if p_names:
        sel_name = st.sidebar.selectbox("📂 選擇目前項目：", p_names)
        curr_p = next(p for p in projs if p['Name'] == sel_name)
    else: curr_p = None

    with st.sidebar.expander("➕ 建立新項目"):
        new_n = st.text_input("項目名稱")
        if st.button("確認建立") and new_n:
            ws_p.insert_row([str(int(datetime.now().timestamp())), new_n, datetime.now().strftime("%Y-%m-%d")], 2)
            st.rerun()
            
    # 【新增功能】：刪除當前項目
    if curr_p:
        with st.sidebar.expander("⚙️ 項目設定 (危險區)"):
            if st.button("🗑️ 刪除當前項目", type="primary"):
                cell = ws_p.find(str(curr_p['ID']))
                ws_p.delete_rows(cell.row)
                st.toast("項目已刪除！")
                st.rerun()

except Exception as e:
    st.sidebar.error(f"🔴 連線失敗: {e}")
    curr_p = None; api_key = None

model_v = st.sidebar.selectbox("🧠 模型:", ["gemini-2.5-flash", "gemini-2.5-pro"])

# ==========================================
# 5. 主畫面：文件分析與互動
# ==========================================
if curr_p:
    st.title(f"📈 項目：{curr_p['Name']}")
    
    # 文件上傳
    with st.expander("📎 上傳報表或素材以供 AI 分析", expanded=False):
        up_file = st.file_uploader("支援 CSV, XLSX, PDF, JPG, PNG", type=['csv', 'xlsx', 'pdf', 'jpg', 'png'])
        file_ctx = ""
        
        if up_file:
            if up_file.name.lower().endswith(('.csv', '.xlsx')):
                data_res, df = process_data(up_file)
                if data_res:
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("活動花費", f"${data_res['cost']:,.1f}")
                    k2.metric("總點擊", f"{data_res['clicks']:,}")
                    k3.metric("總轉換", f"{data_res['convs']:,}")
                    cpa = data_res['cost']/data_res['convs'] if data_res['convs']>0 else 0
                    k4.metric("平均 CPA", f"${cpa:,.1f}")
                    file_ctx = f"報表摘要: 花費 {data_res['cost']}, 點擊 {data_res['clicks']}, 轉換 {data_res['convs']}\n數據前10行: {df.head(10).to_string()}"
            elif up_file.name.lower().endswith(('.jpg', '.png', '.jpeg')):
                img = Image.open(up_file)
                st.image(img, caption="上傳的圖片", width=300)
                st.session_state.active_img = img
                file_ctx = "【使用者上傳了一張圖片，請審核】"

    st.divider()

    # --- 🤖 快捷優化指令 (包含新增的廣告生成與總結) ---
    st.subheader("🤖 AI 快捷指令")
    if "btn_query" not in st.session_state: st.session_state.btn_query = None
    
    col1, col2, col3, col4 = st.columns(4)
    if col1.button("📊 成效分析"): st.session_state.btn_query = "請根據提供的數據分析成效，請多用表格呈現數據對比，並用粗體標示優缺點。"
    if col2.button("📝 生成廣告企劃"): st.session_state.btn_query = "請為此專案生成一份完整的廣告活動企劃。必須使用表格詳細列出：1. 目標對象 (Target Audience) 2. 投放時間排程 3. 預算分配 4. 廣告平台 5. 核心文案。重點請粗體突顯。"
    if col3.button("🎨 素材審核"): st.session_state.btn_query = "請審核圖片素材或文案，針對構圖、配色、吸引力給予重點改進建議。"
    if col4.button("📋 總結與最新建議", type="primary"): st.session_state.btn_query = "請回顧我們以上的所有對話與數據，生成一份重點清晰的『專案總結』，並使用條列式給予『最新的下一步優化建議』。"

    st.divider()

    # --- 讀取對話紀錄並加上「備註(Remark)」功能 ---
    all_chat = ws_c.get_all_records()
    p_chat_with_idx = []
    
    # 標記每筆資料在 Google Sheet 中的真實列數 (Row Index)
    for orig_idx, m in enumerate(all_chat):
        if str(m['PID']) == str(curr_p['ID']):
            m['sheet_row'] = orig_idx + 2  # 第一列是 Header
            p_chat_with_idx.append(m)

    # 以時間順序顯示 (由舊到新排列)
    for m in reversed(p_chat_with_idx):
        with st.chat_message(m['Role'].lower()):
            st.markdown(m['Content'])
            
            # 如果已有備註，顯示出來
            if m.get('Remark', ''):
                st.info(f"📌 **您的備註:** {m['Remark']}")
            
            # 讓使用者可以在 AI 的回覆下留備註
            if m['Role'] == 'Assistant':
                with st.expander("📝 編輯/新增備註"):
                    new_rmk = st.text_input("輸入備註內容並按 Enter 儲存", value=m.get('Remark', ''), key=f"rmk_{m['sheet_row']}")
                    if new_rmk != m.get('Remark', ''):
                        ws_c.update_cell(m['sheet_row'], 5, new_rmk)
                        st.toast("✅ 備註已儲存至雲端！")
                        st.rerun()

    # --- 處理輸入與 AI 生成 ---
    u_input = st.chat_input("詢問您的 AI 顧問...")
    final_q = st.session_state.btn_query if st.session_state.btn_query else u_input

    if final_q and api_key:
        with st.chat_message("user"): st.markdown(final_q)
        # 存入雲端，備註欄位留空
        ws_c.insert_row([str(curr_p['ID']), "User", final_q, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ""], 2)
        
        with st.chat_message("assistant"):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(model_v, system_instruction=SYSTEM_PROMPT)
                
                content_payload = [f"專案:{curr_p['Name']}\n{file_ctx}\n問題:{final_q}"]
                if "active_img" in st.session_state and ("圖片" in final_q or "素材" in final_q or "審核" in final_q):
                    content_payload.append(st.session_state.active_img)
                
                res = model.generate_content(content_payload, stream=True)
                full_text = ""
                ph = st.empty()
                for chunk in res:
                    full_text += chunk.text
                    ph.markdown(full_text + "▌")
                ph.markdown(full_text)
                
                ws_c.insert_row([str(curr_p['ID']), "Assistant", full_text, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ""], 2)
                st.session_state.btn_query = None
                st.rerun()
            except Exception as e:
                st.error(f"AI 生成出錯: {e}")
else:
    st.info("請在左側建立項目開始。")
