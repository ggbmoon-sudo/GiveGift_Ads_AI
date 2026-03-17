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
# 1. 核心設定
# ==========================================
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs" 

SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告顧問。
你具備分析廣告數據、閱讀企劃文件與審核廣告圖片的專業能力。
請保持專業且人性化的語氣。如果提供報表，請根據數據給予洞察；
如果提供廣告圖，請從構圖、配色、文案吸引力與品牌高端感進行評析。"""

# ==========================================
# 2. 認證與安全性修復 (PEM 修正)
# ==========================================
def get_creds():
    if "gcp_service_account" not in st.secrets: return None
    info = dict(st.secrets["gcp_service_account"])
    # 強制修正私鑰中的換行符號問題
    if "private_key" in info:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    return Credentials.from_service_account_info(info, scopes=scope)

# ==========================================
# 3. 數據解析工具
# ==========================================
def process_data(file):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
        
        def clean(v):
            s = str(v).replace('$', '').replace(',', '').replace('%', '').strip()
            return float(s) if s not in ['--', '', 'nan'] else 0.0
        
        res = {"cost": 0.0, "clicks": 0, "convs": 0, "cost_col": None, "conv_col": None, "name_col": df.columns[0]}
        # 過濾總計行
        df_clean = df[~df.iloc[:, 0].astype(str).str.contains('總計|Total|總和', na=False)].copy()

        for col in df_clean.columns:
            c_low = col.lower()
            if '廣告活動' in c_low or 'campaign' in c_low: res['name_col'] = col
            if ('費用' in c_low or 'cost' in c_low) and not any(ex in c_low for ex in ['平均','每','avg']):
                res['cost_col'] = col; res['cost'] = df_clean[col].apply(clean).sum()
            if '點擊' in c_low and '率' not in c_low:
                res['clicks'] = int(df_clean[col].apply(clean).sum())
            if '轉換' in c_low and not any(ex in c_low for ex in ['價值','率','費用']):
                res['conv_col'] = col; res['convs'] = int(df_clean[col].apply(clean).sum())
        
        # 準備圖表數據
        chart_df = df_clean[[res['name_col']]].copy()
        if res['cost_col']: chart_df['Cost'] = df_clean[res['cost_col']].apply(clean)
        if res['conv_col']: chart_df['Conversions'] = df_clean[res['conv_col']].apply(clean)
        res['chart_data'] = chart_df.set_index(res['name_col'])
        
        return res, df_clean
    except: return None, None

# ==========================================
# 4. 側邊欄 UI：診斷與雲端管理
# ==========================================
st.set_page_config(page_title="GGB Ads Consultant", page_icon="💐", layout="wide")
st.sidebar.title("💐 專案管理中心")

if "api_key" not in st.session_state: st.session_state.api_key = ""
api_key = st.sidebar.text_input("🔑 API Key:", type="password", value=st.session_state.api_key)
st.session_state.api_key = api_key

try:
    creds = get_creds()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(MY_SHEET_ID)
    st.sidebar.success("🟢 雲端記憶已連線")
    st.sidebar.markdown(f"🔗 [打開目前的雲端表格]({sh.url})")

    def get_ws(title, head):
        try: return sh.worksheet(title)
        except: 
            w = sh.add_worksheet(title=title, rows="1000", cols=len(head))
            w.insert_row(head, 1); return w

    ws_p = get_ws("Projects", ["ID", "Name", "Created"])
    ws_c = get_ws("ChatHistory", ["PID", "Role", "Content", "Time"])
    
    # 專案列表
    projs = ws_p.get_all_records()
    if projs:
        sel_name = st.sidebar.selectbox("📂 選擇目前項目：", [p['Name'] for p in projs])
        curr_p = next(p for p in projs if p['Name'] == sel_name)
    else:
        curr_p = None

    with st.sidebar.expander("➕ 建立新項目"):
        new_n = st.text_input("項目名稱")
        if st.button("確認建立") and new_n:
            ws_p.insert_row([str(int(datetime.now().timestamp())), new_n, datetime.now().strftime("%Y-%m-%d")], 2)
            st.rerun()

except Exception as e:
    st.sidebar.error(f"🔴 連線失敗: {e}")
    curr_p = None

model_v = st.sidebar.selectbox("🧠 模型:", ["gemini-2.5-flash", "gemini-2.5-pro"])

# ==========================================
# 5. 主畫面：文件分析與 KPI 看板
# ==========================================
if curr_p:
    st.title(f"📈 項目：{curr_p['Name']}")
    
    # 文件上傳區
    with st.expander("📎 上傳報表、文件或廣告圖片", expanded=True):
        up_file = st.file_uploader("支援 CSV, XLSX, PDF, JPG, PNG", type=['csv', 'xlsx', 'pdf', 'jpg', 'png'])
        file_ctx = ""
        data_res = None
        
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
                    file_ctx = f"報表數據摘要: {str(data_res)}\n數據前20行: {df.head(20).to_string()}"
            
            elif up_file.name.lower().endswith(('.jpg', '.png', '.jpeg')):
                img = Image.open(up_file)
                st.image(img, caption="待審核廣告素材", width=400)
                st.session_state.active_img = img
                file_ctx = "【使用者上傳了一張圖片，請結合圖片視覺與文案進行分析】"

    st.divider()

    # 快捷指令
    st.subheader("🤖 AI 優化顧問")
    if "btn_query" not in st.session_state: st.session_state.btn_query = None
    
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("📊 成效分析"): st.session_state.btn_query = "請根據目前提供的數據或文件進行成效分析，指出優缺點。"
    if c2.button("🚀 提高轉換"): st.session_state.btn_query = "針對目前的轉換表現，請給予具體的優化建議。"
    if c3.button("🧠 深度診斷"): st.session_state.btn_query = "執行全自動深度診斷，找出潛在的預算浪費與機會。"
    if c4.button("🎨 素材審核"): st.session_state.btn_query = "請針對我上傳的圖片進行廣告視覺與文案審核，給予改進方向。"

    # 圖表顯示 (若有報表數據)
    if data_res and st.button("📈 顯示數據分布圖表"):
        t1, t2 = st.tabs(["費用分布 (Cost)", "轉換表現 (Conversions)"])
        t1.bar_chart(data_res['chart_data']['Cost'])
        t2.bar_chart(data_res['chart_data']['Conversions'])

    st.divider()

    # 顯示雲端歷史紀錄
    history = ws_c.get_all_records()
    p_history = [m for m in history if str(m['PID']) == str(curr_p['ID'])]
    for m in p_history:
        with st.chat_message(m['Role'].lower()): st.markdown(m['Content'])

    # 處理輸入
    u_input = st.chat_input("詢問您的 AI 顧問...")
    final_q = st.session_state.btn_query if st.session_state.btn_query else u_input

    if final_q and api_key:
        with st.chat_message("user"): st.markdown(final_q)
        ws_c.insert_row([str(curr_p['ID']), "User", final_q, datetime.now().strftime("%H:%M")], 2)
        
        with st.chat_message("assistant"):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(model_v, system_instruction=SYSTEM_PROMPT)
                
                # 組合 AI 讀取的內容
                content_payload = [f"專案:{curr_p['Name']}\n{file_ctx}\n問題:{final_q}"]
                if "active_img" in st.session_state and ("圖片" in final_q or "素材" in final_q):
                    content_payload.append(st.session_state.active_img)
                
                res = model.generate_content(content_payload, stream=True)
                full_text = ""
                ph = st.empty()
                for chunk in res:
                    full_text += chunk.text
                    ph.markdown(full_text + "▌")
                ph.markdown(full_text)
                
                ws_c.insert_row([str(curr_p['ID']), "Assistant", full_text, datetime.now().strftime("%H:%M")], 2)
                st.session_state.btn_query = None
                st.rerun()
            except Exception as e:
                st.error(f"AI 生成出錯: {e}")
else:
    st.info("請在左側建立項目並確保連線綠燈。")
