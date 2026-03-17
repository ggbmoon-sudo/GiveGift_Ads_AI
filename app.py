import streamlit as st
import pandas as pd
import google.generativeai as genai
import sqlite3
import os
from datetime import datetime

# ==========================================
# 0. 資料庫與目錄初始化
# ==========================================
def init_db():
    conn = sqlite3.connect('givegift_ads_v3.db')
    c = conn.cursor()
    # 專案列表：報表與專案永久掛鉤
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
    
    if not os.path.exists("saved_reports"):
        os.makedirs("saved_reports")

init_db()

# --- 資料庫操作 ---
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
    if content:
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
st.set_page_config(page_title="GGB Ads Intelligence 2026", page_icon="💐", layout="wide")

SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告顧問。
你與使用者的關係是長期的夥伴，請保持人性化、親切且專業。
若專案已掛鉤報表，請優先參考數據；若無，則以尚禮坊的高端品牌調性給予專業建議。"""

# ==========================================
# 2. 側邊欄：管理中心
# ==========================================
st.sidebar.title("💐 專案管理中心")

with st.sidebar.expander("➕ 建立新項目"):
    n = st.text_input("項目名稱 (如：2026 中秋果籃)")
    if st.button("確認建立"):
        if n:
            conn = sqlite3.connect('givegift_ads_v3.db')
            conn.execute("INSERT INTO projects (name, created_at) VALUES (?, ?)", (n, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit(); conn.close()
            st.rerun()

projects_df = get_projects()
if not projects_df.empty:
    proj_map = {row['name']: row for _, row in projects_df.iterrows()}
    sel_name = st.sidebar.selectbox("📂 選擇目前操作項目：", list(proj_map.keys()))
    curr_proj = proj_map[sel_name]
    curr_pid = curr_proj['id']
else:
    st.sidebar.warning("請先建立項目")
    curr_pid = None

st.sidebar.divider()
api_key = st.sidebar.text_input("🔑 API Key:", type="password")

# --- 限制模型版本為 2.5 系列 ---
selected_model = st.sidebar.selectbox(
    "🧠 模型引擎:", 
    ["gemini-2.5-flash", "gemini-2.5-pro"], 
    index=0
)

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(selected_model, system_instruction=SYSTEM_PROMPT)

page = st.sidebar.radio("導覽：", ["📈 數據看板與分析", "💡 文案生成"])

# ==========================================
# 3. 數據解析核心
# ==========================================
def process_data(file_path):
    try:
        if file_path.endswith('.csv'):
            tmp = pd.read_csv(file_path, nrows=10, header=None)
            f_seek = 0
            for i, row in tmp.iterrows():
                if any(k in "".join(map(str, row.values)) for k in ["廣告活動", "費用"]): f_seek = i; break
            df = pd.read_csv(file_path, skiprows=f_seek)
        else:
            tmp = pd.read_excel(file_path, nrows=10, header=None)
            f_seek = 0
            for i, row in tmp.iterrows():
                if any(k in "".join(map(str, row.values)) for k in ["廣告活動", "費用"]): f_seek = i; break
            df = pd.read_excel(file_path, header=f_seek)
        
        df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
        
        def clean(v): return float(str(v).replace('$', '').replace(',', '').strip()) if not pd.isna(v) and str(v).strip() != '--' else 0.0
        
        res = {"df": df, "cost": 0.0, "clicks": 0, "convs": 0}
        name_col = df.columns[0]
        for col in df.columns:
            c_low = col.lower()
            if '廣告活動' in c_low: name_col = col
            if '費用' in c_low and not any(ex in c_low for ex in ['平均','每']): res['cost_col']=col; res['cost']=df[col].apply(clean).sum()
            if '點擊' in c_low and '率' not in c_low: res['click_col']=col; res['clicks']=int(df[col].apply(clean).sum())
            if '轉換' in c_low and not any(ex in c_low for ex in ['價值','率']): res['conv_col']=col; res['convs']=int(df[col].apply(clean).sum())
        
        # 準備圖表數據
        chart_df = df[[name_col]].copy()
        if 'cost_col' in res: chart_df['Cost'] = df[res['cost_col']].apply(clean)
        if 'conv_col' in res: chart_df['Conversions'] = df[res['conv_col']].apply(clean)
        res['chart_data'] = chart_df.set_index(name_col)
        
        return res
    except:
        return None

# ==========================================
# 4. 頁面邏輯
# ==========================================
if curr_pid:
    if page == "📈 數據看板與分析":
        st.title(f"📈 {sel_name}")
        
        # --- 報表持久化掛鉤區 ---
        with st.expander("📊 項目報表連結", expanded=not bool(curr_proj['report_path'])):
            up_f = st.file_uploader("為此項目更換報表", type=['csv', 'xlsx'])
            if up_f:
                s_path = f"saved_reports/p{curr_pid}_{up_f.name}"
                with open(s_path, "wb") as f: f.write(up_f.getbuffer())
                update_project_report(curr_pid, s_path)
                st.success("報表已與項目掛鉤儲存！")
                st.rerun()
            
            if curr_proj['report_path']:
                st.caption(f"目前掛鉤檔案：{os.path.basename(curr_proj['report_path'])}")
                if st.button("❌ 移除報表連結"):
                    update_project_report(curr_pid, None); st.rerun()

        # 載入掛鉤數據
        data_res = None
        if curr_proj['report_path'] and os.path.exists(curr_proj['report_path']):
            data_res = process_data(curr_proj['report_path'])
            if data_res:
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("項目總費用", f"${data_res['cost']:,.2f}")
                k2.metric("總點擊", f"{data_res['clicks']:,}")
                k3.metric("總轉換", f"{data_res['convs']:,}")
                cpa = data_res['cost']/data_res['convs'] if data_res['convs']>0 else 0
                k4.metric("平均 CPA", f"${cpa:,.2f}")

        st.divider()
        
        # --- 快捷鍵與對話 ---
        st.subheader("💬 優化顧問區")
        
        col_btns = st.columns(4)
        fast_q = None
        if col_btns[0].button("📊 成效分析"): fast_q = "請根據目前數據分析成效，並列出表現最好與最差的廣告活動。"
        if col_btns[1].button("🚀 提高轉換"): fast_q = "針對目前的轉換情況，有什麼具體的優化建議？"
        if col_btns[2].button("🧠 自動深度診斷"): fast_q = "執行全自動深度診斷，找出浪費預算的地方。"
        
        show_charts = col_btns[3].button("📈 生成視覺化圖表")
        if show_charts and data_res:
            st.write("### 數據分布")
            tab1, tab2 = st.tabs(["費用 (Cost)", "轉換 (Conversions)"])
            tab1.bar_chart(data_res['chart_data']['Cost'])
            tab2.bar_chart(data_res['chart_data']['Conversions'])

        if st.button("💾 手動同步對話內容"): st.toast("✅ 對話紀錄已寫入資料庫")

        # 對話顯示
        history = load_chats(curr_pid)
        for m in history:
            with st.chat_message(m["role"]): st.markdown(m["content"])

        u_input = st.chat_input("輸入對話或按上方快捷鍵...")
        final_q = fast_q if fast_q else u_input

        if final_q and api_key:
            with st.chat_message("user"): st.markdown(final_q)
            save_chat(curr_pid, "user", final_q)
            
            with st.chat_message("assistant"):
                ctx = f"專案：{sel_name}\n"
                if data_res: ctx += f"報表數據摘要：\n{data_res['df'].head(40).to_string()}\n"
                ctx += f"指令：{final_q}"
                
                res = model.generate_content(ctx, stream=True)
                full = ""
                ph = st.empty()
                for chunk in res:
                    full += chunk.text
                    ph.markdown(full + "▌")
                ph.markdown(full)
                save_chat(curr_pid, "assistant", full)
                st.rerun()

else:
    st.title("🚀 尚禮坊 AI 廣告工作站")
    st.info("請先從左側建立一個新專案。")
