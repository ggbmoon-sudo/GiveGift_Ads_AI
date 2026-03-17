import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import sqlite3
from datetime import datetime
import io

# ==========================================
# 0. 資料庫初始化
# ==========================================
def init_db():
    conn = sqlite3.connect('givegift_ads_v2.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS projects 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, 
                  role TEXT, content TEXT, created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 資料庫操作函數 ---
def get_projects():
    conn = sqlite3.connect('givegift_ads_v2.db')
    df = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    conn.close()
    return df

def create_project(name):
    conn = sqlite3.connect('givegift_ads_v2.db')
    c = conn.cursor()
    c.execute("INSERT INTO projects (name, created_at) VALUES (?, ?)", 
              (name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def save_chat(project_id, role, content):
    conn = sqlite3.connect('givegift_ads_v2.db')
    c = conn.cursor()
    c.execute("INSERT INTO chat_history (project_id, role, content, created_at) VALUES (?, ?, ?, ?)", 
              (project_id, role, str(content), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def load_chats(project_id):
    conn = sqlite3.connect('givegift_ads_v2.db')
    df = pd.read_sql_query(f"SELECT role, content FROM chat_history WHERE project_id={project_id} ORDER BY id ASC", conn)
    conn.close()
    return df.to_dict('records')

# ==========================================
# 1. 介面與模型設定
# ==========================================
st.set_page_config(page_title="GGB Ads Manager 2026", page_icon="💐", layout="wide")

SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席 AI 廣告優化師。
你的目標是協助使用者管理特定的廣告活動項目。你的分析必須非常精準且具備執行力。
請使用專業的香港市場術語，並在分析中多使用表格與數據對比。"""

# ==========================================
# 2. 側邊欄：管理中樞
# ==========================================
st.sidebar.title("💐 尚禮坊活動管理中樞")

with st.sidebar.expander("➕ 建立新廣告活動項目", expanded=False):
    new_name = st.text_input("活動名稱 (如：2026 中秋企業送禮)")
    if st.button("確認建立"):
        if new_name:
            create_project(new_name)
            st.rerun()

st.sidebar.subheader("📂 我的活動項目列表")
projects_df = get_projects()
if not projects_df.empty:
    proj_map = {row['name']: row['id'] for _, row in projects_df.iterrows()}
    selected_name = st.sidebar.selectbox("切換目前操作項目：", list(proj_map.keys()))
    current_pid = proj_map[selected_name]
else:
    st.sidebar.warning("請先建立一個活動項目")
    current_pid = None

st.sidebar.divider()
api_key = st.sidebar.text_input("🔑 API Key:", type="password")
selected_model = st.sidebar.selectbox(
    "🧠 AI 模型引擎版本:",
    ["gemini-3.0-pro", "gemini-3.0-flash", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    index=1
)

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(selected_model, system_instruction=SYSTEM_PROMPT)

page = st.sidebar.radio("導覽：", ["📈 數據分析看板", "💡 獨立文案生成器"])

# ==========================================
# 3. 數據處理核心
# ==========================================
def extract_kpi_v3(df):
    kpi = {"cost": 0.0, "clicks": 0, "conversions": 0}
    def clean(v):
        if pd.isna(v) or str(v).strip() in ['--', '']: return 0.0
        return float(str(v).replace('$', '').replace(',', '').replace('%', '').strip())
    
    df_clean = df[~df.iloc[:, 0].astype(str).str.contains('總計|Total|總和', na=False)].copy()
    for col in df_clean.columns:
        c = str(col).lower().strip()
        if ('費用' in c or 'cost' in c) and not any(ex in c for ex in ['平均', '每', 'avg', 'cpc']):
            kpi['cost'] = df_clean[col].apply(clean).sum()
        elif '點擊' in c and '率' not in c:
            kpi['clicks'] = int(df_clean[col].apply(clean).sum())
        elif '轉換' in c and not any(ex in c for ex in ['價值', '率', '費用', 'value']):
            kpi['conversions'] = int(df_clean[col].apply(clean).sum())
    return kpi

# ==========================================
# 4. 頁面邏輯：數據分析看板 (含快捷按鈕)
# ==========================================
if current_pid:
    if page == "📈 數據分析看板":
        st.title(f"📈 項目診斷：{selected_name}")
        f = st.file_uploader(f"上傳 {selected_name} 的數據報表", type=['csv', 'xlsx'])
        
        if f:
            try:
                # 智能標題定位
                tmp = pd.read_csv(f, nrows=10, header=None) if f.name.endswith('.csv') else pd.read_excel(f, nrows=10, header=None)
                f.seek(0); h = 0
                for i, row in tmp.iterrows():
                    if any(k in "".join(map(str, row.values)) for k in ["廣告活動", "費用", "點擊"]):
                        h = i; break
                df = pd.read_csv(f, skiprows=h) if f.name.endswith('.csv') else pd.read_excel(f, header=h)
                df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
                
                # --- KPI 看板 ---
                data = extract_kpi_v3(df)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("活動花費", f"${data['cost']:,.2f}")
                c2.metric("總點擊", f"{data['clicks']:,} 次")
                c3.metric("總轉換", f"{data['conversions']:,} 筆")
                cpa = data['cost']/data['conversions'] if data['conversions'] > 0 else 0
                c4.metric("CPA (平均成本)", f"${cpa:,.2f}")
                
                st.divider()

                # --- 🚀 快捷行動按鈕 (Quick Actions) ---
                st.subheader("🤖 快捷分析指令")
                qa_col1, qa_col2, qa_col3 = st.columns(3)
                
                quick_query = None
                if qa_col1.button("📊 分析廣告活動成效"):
                    quick_query = "請針對此廣告活動的數據進行深度成效分析，涵蓋 ROAS、CPC、點擊表現，並用表格點出表現最好與最差的廣告活動。"
                if qa_col2.button("🚀 提高轉換率策略"):
                    quick_query = "請根據現有數據，針對提升『轉換率』提供具體策略。分析為何目前的點擊未能轉化，並給出關於文案、受眾或出價的調整建議。"
                if qa_col3.button("🧠 自動分析(非常仔細)"):
                    quick_query = "請執行一次『全自動地毯式』分析。請檢查：1. 預算分配合理性 2. 搜尋字詞是否有預算浪費 3. 設備與地理位置表現。請以極度詳細的格式產出專業報告。"

                # --- 處理快捷按鈕或對話輸入 ---
                chats = load_chats(current_pid)
                for m in chats:
                    with st.chat_message(m["role"]): st.markdown(m["content"])

                user_q = st.chat_input(f"關於 {selected_name} 的其他提問...")
                
                # 如果按了按鈕或輸入了問題
                final_q = quick_query if quick_query else user_q
                
                if final_q and api_key:
                    with st.chat_message("user"): st.markdown(final_q)
                    save_chat(current_pid, "user", final_q)
                    
                    with st.chat_message("assistant"):
                        context = f"專案：{selected_name}\n數據摘要：\n{df.head(40).to_string()}\n\n指令：{final_q}"
                        res = model.generate_content(context, stream=True)
                        full = ""
                        placeholder = st.empty()
                        for chunk in res:
                            full += chunk.text
                            placeholder.markdown(full + "▌")
                        placeholder.markdown(full)
                        save_chat(current_pid, "assistant", full)
                        st.download_button("📥 下載此分析報告", full, file_name=f"{selected_name}_Report.txt")

            except Exception as e:
                st.error(f"檔案解析失敗：{e}")
    else:
        st.title("🚀 歡迎回來")
        st.info("請在左側選擇或建立一個活動項目以開始。")
