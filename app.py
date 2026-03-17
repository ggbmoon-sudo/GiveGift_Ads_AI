import streamlit as st
import pandas as pd
import google.generativeai as genai
import sqlite3
import os
from datetime import datetime

# ==========================================
# 0. 資料庫初始化 (新增 report_path 欄位)
# ==========================================
def init_db():
    conn = sqlite3.connect('givegift_ads_v3.db')
    c = conn.cursor()
    # 專案列表：儲存名稱、建立時間、以及關聯的報表路徑
    c.execute('''CREATE TABLE IF NOT EXISTS projects 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  name TEXT, 
                  report_path TEXT, 
                  created_at TEXT)''')
    # 對話紀錄
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  project_id INTEGER, 
                  role TEXT, 
                  content TEXT, 
                  created_at TEXT)''')
    conn.commit()
    conn.close()
    
    # 建立報表儲存目錄
    if not os.path.exists("saved_reports"):
        os.makedirs("saved_reports")

init_db()

# --- 資料庫操作函數 ---
def get_projects():
    conn = sqlite3.connect('givegift_ads_v3.db')
    df = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    conn.close()
    return df

def update_project_report(pid, path):
    conn = sqlite3.connect('givegift_ads_v3.db')
    c = conn.cursor()
    c.execute("UPDATE projects SET report_path = ? WHERE id = ?", (path, pid))
    conn.commit()
    conn.close()

def save_chat(pid, role, content):
    conn = sqlite3.connect('givegift_ads_v3.db')
    c = conn.cursor()
    c.execute("INSERT INTO chat_history (project_id, role, content, created_at) VALUES (?, ?, ?, ?)", 
              (pid, role, content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def load_chats(pid):
    conn = sqlite3.connect('givegift_ads_v3.db')
    df = pd.read_sql_query(f"SELECT role, content FROM chat_history WHERE project_id={pid} ORDER BY id ASC", conn)
    conn.close()
    return df.to_dict('records')

# ==========================================
# 1. 系統設定
# ==========================================
st.set_page_config(page_title="GGB Ads Consultant", page_icon="💐", layout="wide")

SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告顧問。
你與使用者的關係是長期的夥伴，請保持人性化、親切且專業的語氣。
當專案有掛鉤報表時，請參考數據；若無報表，請根據尚禮坊的高端花藝定位給予建議。"""

# ==========================================
# 2. 側邊欄：項目與模型管理
# ==========================================
st.sidebar.title("💐 顧問中心")

# 建立專案
with st.sidebar.expander("➕ 建立新項目"):
    n = st.text_input("項目名稱")
    if st.button("確認建立"):
        if n:
            conn = sqlite3.connect('givegift_ads_v3.db')
            conn.execute("INSERT INTO projects (name, created_at) VALUES (?, ?)", (n, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit(); conn.close()
            st.rerun()

# 選擇專案
projects_df = get_projects()
if not projects_df.empty:
    proj_map = {row['name']: row for _, row in projects_df.iterrows()}
    sel_name = st.sidebar.selectbox("📂 選擇目前跟進項目：", list(proj_map.keys()))
    curr_proj = proj_map[sel_name]
    curr_pid = curr_proj['id']
else:
    st.sidebar.warning("請先建立項目")
    curr_pid = None

st.sidebar.divider()
api_key = st.sidebar.text_input("🔑 API Key:", type="password")
selected_model = st.sidebar.selectbox("🧠 模型版本:", ["gemini-3.0-flash", "gemini-3.0-pro", "gemini-2.5-pro"], index=0)

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(selected_model, system_instruction=SYSTEM_PROMPT)

# ==========================================
# 3. 數據分析函數 (KPI 提取)
# ==========================================
def process_data(file_path):
    try:
        if file_path.endswith('.csv'):
            # 這裡沿用您最強大的自動定位標題邏輯
            tmp = pd.read_csv(file_path, nrows=10, header=None)
            h = 0
            for i, row in tmp.iterrows():
                if any(k in "".join(map(str, row.values)) for k in ["廣告活動", "費用"]): h = i; break
            df = pd.read_csv(file_path, skiprows=h)
        else:
            tmp = pd.read_excel(file_path, nrows=10, header=None)
            h = 0
            for i, row in tmp.iterrows():
                if any(k in "".join(map(str, row.values)) for k in ["廣告活動", "費用"]): h = i; break
            df = pd.read_excel(file_path, header=h)
        
        df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
        
        # 提取 KPI 邏輯 (簡化顯示)
        def clean(v): return float(str(v).replace('$', '').replace(',', '').strip()) if not pd.isna(v) and str(v).strip() != '--' else 0.0
        
        costs = 0.0; convs = 0; clicks = 0
        for col in df.columns:
            c_low = col.lower()
            if '費用' in c_low and not any(ex in c_low for ex in ['平均','每']): costs = df[col].apply(clean).sum()
            if '點擊' in c_low and '率' not in c_low: clicks = int(df[col].apply(clean).sum())
            if '轉換' in c_low and not any(ex in c_low for ex in ['價值','率']): convs = int(df[col].apply(clean).sum())
        
        return {"df": df, "cost": costs, "clicks": clicks, "convs": convs}
    except:
        return None

# ==========================================
# 4. 主介面：人性化顧問空間
# ==========================================
if curr_pid:
    st.title(f"💐 尚禮坊顧問空間：{sel_name}")
    
    # --- 報表管理區 (與專案掛鉤) ---
    with st.expander("📊 項目報表管理", expanded=not bool(curr_proj['report_path'])):
        col_up, col_info = st.columns([1, 1])
        with col_up:
            up_f = st.file_uploader("更新/上傳此項目的報表", type=['csv', 'xlsx'])
            if up_f:
                save_path = f"saved_reports/proj_{curr_pid}_{up_f.name}"
                with open(save_path, "wb") as f:
                    f.write(up_f.getbuffer())
                update_project_report(curr_pid, save_path)
                st.success("報表已與項目掛鉤儲存！")
                st.rerun()
        
        with col_info:
            if curr_proj['report_path']:
                st.info(f"📁 目前掛鉤報表：{os.path.basename(curr_proj['report_path'])}")
                if st.button("❌ 解除報表掛鉤"):
                    update_project_report(curr_pid, None)
                    st.rerun()
            else:
                st.write("目前此項目尚未掛鉤報表。")

    # --- 數據看板 (若有報表則自動載入) ---
    analysis_res = None
    if curr_proj['report_path'] and os.path.exists(curr_proj['report_path']):
        analysis_res = process_data(curr_proj['report_path'])
        if analysis_res:
            st.subheader("📊 實時數據概覽")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("總費用", f"${analysis_res['cost']:,.2f}")
            k2.metric("總點擊", f"{analysis_res['clicks']:,}")
            k3.metric("總轉換", f"{analysis_res['convs']:,}")
            cpa = analysis_res['cost']/analysis_res['convs'] if analysis_res['convs']>0 else 0
            k4.metric("平均 CPA", f"${cpa:,.2f}")

    st.divider()

    # --- 人性化對話區 (持久化記錄) ---
    st.subheader("💬 顧問對話紀錄")
    
    # 快捷分析按鈕 (只有在有報表時才出現，但不會「綁架」對話)
    if analysis_res:
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        fast_q = None
        if btn_col1.button("🚨 診斷當前數據"): fast_q = "請根據目前掛鉤的數據，告訴我這個活動表現如何？"
        if btn_col2.button("🚀 提高轉換策略"): fast_q = "針對目前的轉換情況，有什麼具體的優化動作？"
        if btn_col3.button("📈 生成趨勢洞察"): fast_q = "請分析數據中的異常點與未來的投放機會。"

    # 顯示歷史紀錄
    history = load_chats(curr_pid)
    if not history:
        with st.chat_message("assistant"):
            st.markdown(f"您好！我是您的廣告顧問。我們今天來聊聊『{sel_name}』這個項目吧。您是想上傳報表讓我分析，還是想討論文案策略？")
    else:
        for m in history:
            with st.chat_message(m["role"]): st.markdown(m["content"])

    # 處理輸入
    user_input = st.chat_input("輸入您的想法...")
    final_q = fast_q if fast_q else user_input

    if final_q and api_key:
        with st.chat_message("user"): st.markdown(final_q)
        save_chat(curr_pid, "user", final_q)
        
        with st.chat_message("assistant"):
            # 組合上下文：如果有報表，就把報表內容也塞進去
            context = f"【專案名稱】：{sel_name}\n"
            if analysis_res:
                context += f"【報表數據摘要】：\n{analysis_res['df'].head(30).to_string()}\n"
            context += f"\n使用者提問：{final_q}"
            
            res = model.generate_content(context, stream=True)
            full_res = ""
            ph = st.empty()
            for chunk in res:
                full_res += chunk.text
                ph.markdown(full_res + "▌")
            ph.markdown(full_res)
            save_chat(curr_pid, "assistant", full_res)
            st.rerun()

else:
    st.title("🚀 歡迎使用尚禮坊 AI 工作站")
    st.info("請先在側邊欄『建立項目』，或選擇一個現有的活動開始。")
