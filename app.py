import streamlit as st
import pandas as pd
import google.generativeai as genai
import sqlite3
import os
from datetime import datetime

# ==========================================
# 0. 初始化
# ==========================================
def init_db():
    conn = sqlite3.connect('givegift_ads_v3.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS projects 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, report_path TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, role TEXT, content TEXT, created_at TEXT)''')
    conn.commit(); conn.close()
    if not os.path.exists("saved_reports"): os.makedirs("saved_reports")

init_db()

# 初始化 Session State (防止按鈕失效)
if "run_query" not in st.session_state: st.session_state.run_query = None
if "show_charts" not in st.session_state: st.session_state.show_charts = False

# --- 資料庫操作 ---
def get_projects():
    conn = sqlite3.connect('givegift_ads_v3.db'); df = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn); conn.close()
    return df

def save_chat(pid, role, content):
    if content:
        conn = sqlite3.connect('givegift_ads_v3.db'); c = conn.cursor()
        c.execute("INSERT INTO chat_history (project_id, role, content, created_at) VALUES (?, ?, ?, ?)", (pid, role, content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit(); conn.close()

def load_chats(pid):
    conn = sqlite3.connect('givegift_ads_v3.db'); df = pd.read_sql_query(f"SELECT role, content FROM chat_history WHERE project_id={pid} ORDER BY id ASC", conn); conn.close()
    return df.to_dict('records')

# ==========================================
# 1. 系統設定 (限 2.5 版本)
# ==========================================
st.set_page_config(page_title="GGB Ads Manager", page_icon="💐", layout="wide")
SYSTEM_PROMPT = "你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告顧問。請根據數據給予人性化且專業的分析。"

st.sidebar.title("💐 專案管理中心")
with st.sidebar.expander("➕ 建立新項目"):
    n = st.text_input("項目名稱")
    if st.button("確認建立"):
        if n:
            conn = sqlite3.connect('givegift_ads_v3.db')
            conn.execute("INSERT INTO projects (name, created_at) VALUES (?, ?)", (n, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit(); conn.close(); st.rerun()

projects_df = get_projects()
if not projects_df.empty:
    proj_map = {row['name']: row for _, row in projects_df.iterrows()}
    sel_name = st.sidebar.selectbox("📂 選擇項目：", list(proj_map.keys()))
    curr_proj = proj_map[sel_name]; curr_pid = curr_proj['id']
else:
    st.sidebar.warning("請先建立項目"); curr_pid = None

st.sidebar.divider()
api_key = st.sidebar.text_input("🔑 API Key:", type="password")
selected_model = st.sidebar.selectbox("🧠 模型:", ["gemini-2.5-flash", "gemini-2.5-pro"], index=0)

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(selected_model, system_instruction=SYSTEM_PROMPT)

# ==========================================
# 2. 強化版數據解析 (解決 KPI 0 的問題)
# ==========================================
def process_data(file_path):
    try:
        if file_path.endswith('.csv'):
            tmp = pd.read_csv(file_path, nrows=15, header=None)
            h = 0
            for i, row in tmp.iterrows():
                row_str = "".join(map(str, row.values))
                if any(k in row_str for k in ["廣告活動", "費用", "點擊", "Campaign", "Cost"]): h = i; break
            df = pd.read_csv(file_path, skiprows=h)
        else:
            tmp = pd.read_excel(file_path, nrows=15, header=None)
            h = 0
            for i, row in tmp.iterrows():
                row_str = "".join(map(str, row.values))
                if any(k in row_str for k in ["廣告活動", "費用", "點擊", "Campaign", "Cost"]): h = i; break
            df = pd.read_excel(file_path, header=h)
        
        df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
        def clean(v):
            s = str(v).replace('$', '').replace(',', '').replace('%', '').strip()
            return float(s) if s not in ['--', '', 'nan', 'None'] else 0.0
        
        res = {"df": df, "cost": 0.0, "clicks": 0, "convs": 0, "name_col": df.columns[0]}
        # 排除總計行
        df_clean = df[~df.iloc[:, 0].astype(str).str.contains('總計|Total|總和', na=False)].copy()

        for col in df_clean.columns:
            c_low = col.lower()
            if '廣告活動' in c_low or 'campaign' in c_low: res['name_col'] = col
            if ('費用' in c_low or 'cost' in c_low) and not any(ex in c_low for ex in ['平均','每','avg']):
                res['cost_col'] = col; res['cost'] = df_clean[col].apply(clean).sum()
            if '點擊' in c_low and '率' not in c_low:
                res['click_col'] = col; res['clicks'] = int(df_clean[col].apply(clean).sum())
            if '轉換' in c_low and not any(ex in c_low for ex in ['價值','率','費用']):
                res['conv_col'] = col; res['convs'] = int(df_clean[col].apply(clean).sum())
        
        # 準備圖表
        chart_df = df_clean[[res['name_col']]].copy()
        if 'cost_col' in res: chart_df['Cost'] = df_clean[res['cost_col']].apply(clean)
        if 'conv_col' in res: chart_df['Conversions'] = df_clean[res['conv_col']].apply(clean)
        res['chart_data'] = chart_df.set_index(res['name_col'])
        return res
    except: return None

# ==========================================
# 3. 主頁面邏輯
# ==========================================
if curr_pid:
    st.title(f"📈 項目：{sel_name}")
    
    with st.expander("📊 報表掛鉤管理"):
        up_f = st.file_uploader("上傳/更換報表", type=['csv', 'xlsx'])
        if up_f:
            path = f"saved_reports/p{curr_pid}_{up_f.name}"
            with open(path, "wb") as f: f.write(up_f.getbuffer())
            conn = sqlite3.connect('givegift_ads_v3.db'); conn.execute("UPDATE projects SET report_path = ? WHERE id = ?", (path, curr_pid)); conn.commit(); conn.close()
            st.rerun()
        if curr_proj['report_path']:
            st.caption(f"目前檔案：{os.path.basename(curr_proj['report_path'])}")
            if st.button("❌ 移除報表"): 
                conn = sqlite3.connect('givegift_ads_v3.db'); conn.execute("UPDATE projects SET report_path = NULL WHERE id = ?", (curr_pid,)); conn.commit(); conn.close(); st.rerun()

    data_res = None
    if curr_proj['report_path'] and os.path.exists(curr_proj['report_path']):
        data_res = process_data(curr_proj['report_path'])
        if data_res:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("總費用", f"${data_res['cost']:,.2f}")
            k2.metric("總點擊", f"{data_res['clicks']:,}")
            k3.metric("總轉換", f"{data_res['convs']:,}")
            cpa = data_res['cost']/data_res['convs'] if data_res['convs']>0 else 0
            k4.metric("平均 CPA", f"${cpa:,.2f}")

    st.divider()

    # --- 快捷按鈕區 (修復沒反應問題) ---
    st.subheader("🤖 快捷優化指令")
    c_btn = st.columns(4)
    
    if c_btn[0].button("📊 成效分析"): st.session_state.run_query = "請根據目前數據分析成效，列出表現最好與最差的廣告活動。"
    if c_btn[1].button("🚀 提高轉換"): st.session_state.run_query = "針對目前的轉換情況，有什麼具體的優化建議？"
    if c_btn[2].button("🧠 自動深度分析"): st.session_state.run_query = "執行全自動深度診斷，找出浪費預算的地方與優化機會。"
    if c_btn[3].button("📈 生成視覺化圖表"): 
        st.session_state.show_charts = not st.session_state.show_charts

    if st.session_state.show_charts and data_res:
        st.write("### 視覺化分布")
        t1, t2 = st.tabs(["費用分布", "轉換表現"])
        t1.bar_chart(data_res['chart_data']['Cost'])
        t2.bar_chart(data_res['chart_data']['Conversions'])

    # --- 對話與 AI 生成 ---
    history = load_chats(curr_pid)
    for m in history:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    u_input = st.chat_input("輸入您的問題...")
    
    # 決定最終要跑的指令
    if u_input: st.session_state.run_query = u_input

    if st.session_state.run_query and api_key:
        query = st.session_state.run_query
        with st.chat_message("user"): st.markdown(query)
        save_chat(curr_pid, "user", query)
        
        with st.chat_message("assistant"):
                        ctx = f"專案：{sel_name}\n"
                        if data_res: ctx += f"報表數據摘要：\n{data_res['df'].head(40).to_string()}\n"
                        ctx += f"指令：{query}"
                        
                        res = model.generate_content(ctx, stream=True)
                        full = ""
                        ph = st.empty()
                        
                        try:
                            for chunk in res:
                                # --- 核心修復：檢查 chunk 是否包含有效文字 ---
                                if chunk.candidates and chunk.candidates[0].content.parts:
                                    chunk_text = chunk.text
                                    full += chunk_text
                                    ph.markdown(full + "▌")
                                else:
                                    # 如果內容被屏蔽，顯示提示而非崩潰
                                    st.warning("⚠️ 部分內容因安全策略被屏蔽，請嘗試更換提問方式。")
                        except Exception as e:
                            st.error(f"生成過程發生錯誤：{e}")
                        
                        ph.markdown(full)
                        save_chat(curr_pid, "assistant", full)
        
        # 清除指令狀態，防止重整時重複觸發
        st.session_state.run_query = None
        st.rerun()

else:
    st.title("🚀 尚禮坊 AI 工作站")
    st.info("請先在側邊欄建立項目。")
