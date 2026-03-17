import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import sqlite3
from datetime import datetime
import io

# ==========================================
# 0. 資料庫初始化 (新增 Project 關聯)
# ==========================================
def init_db():
    conn = sqlite3.connect('givegift_ads.db')
    c = conn.cursor()
    # 專案列表
    c.execute('''CREATE TABLE IF NOT EXISTS projects 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, created_at TEXT)''')
    # 廣告企劃 (連結 project_id)
    c.execute('''CREATE TABLE IF NOT EXISTS campaigns 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, name TEXT, 
                  ad_type TEXT, budget REAL, ai_proposal TEXT, created_at TEXT)''')
    # 對話紀錄 (連結 project_id)
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, 
                  role TEXT, content TEXT, created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

# 資料庫輔助函數
def get_projects():
    conn = sqlite3.connect('givegift_ads.db')
    df = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    conn.close()
    return df

def create_project(name):
    conn = sqlite3.connect('givegift_ads.db')
    c = conn.cursor()
    c.execute("INSERT INTO projects (name, created_at) VALUES (?, ?)", (name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id

def save_chat(project_id, role, content):
    conn = sqlite3.connect('givegift_ads.db')
    c = conn.cursor()
    c.execute("INSERT INTO chat_history (project_id, role, content, created_at) VALUES (?, ?, ?, ?)", 
              (project_id, role, str(content), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def load_chats(project_id):
    conn = sqlite3.connect('givegift_ads.db')
    df = pd.read_sql_query(f"SELECT role, content FROM chat_history WHERE project_id={project_id} ORDER BY id ASC", conn)
    conn.close()
    return df.to_dict('records')

# ==========================================
# 1. 介面與模型設定
# ==========================================
st.set_page_config(page_title="GGB Ads Management System", page_icon="💐", layout="wide")

SYSTEM_PROMPT = "你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告顧問。你正在針對一個特定的廣告活動進行分析，請記住之前的數據與對話，給出獨立且專業的調整建議。"

# ==========================================
# 2. 側邊欄：專案管理中心 (核心更新)
# ==========================================
st.sidebar.title("💐 尚禮坊活動管理中心")

# --- 新增活動功能 ---
with st.sidebar.expander("➕ 新增廣告活動項目", expanded=False):
    new_proj_name = st.text_input("輸入活動名稱 (如: 2026中秋節)")
    if st.button("確認創建"):
        if new_proj_name:
            create_project(new_proj_name)
            st.success("項目已建立")
            st.rerun()

# --- 選擇活動列表 ---
st.sidebar.subheader("📂 選擇活動項目")
projects_df = get_projects()

if projects_df.empty:
    st.sidebar.info("目前沒有活動，請先新增一個項目。")
    current_project_id = None
else:
    # 格式化顯示名稱
    proj_options = {row['name']: row['id'] for _, row in projects_df.iterrows()}
    selected_proj_name = st.sidebar.selectbox("切換目前操作的檔案：", list(proj_options.keys()))
    current_project_id = proj_options[selected_proj_name]

st.sidebar.divider()
api_key = st.sidebar.text_input("🔑 API Key:", type="password")
selected_model = st.sidebar.selectbox("🧠 模型:", ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"])

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(selected_model, system_instruction=SYSTEM_PROMPT)

st.sidebar.divider()
page = st.sidebar.radio("功能區域：", ["📈 數據分析看板", "💡 獨立文案生成"])

# ==========================================
# 3. KPI 數據處理函數 (維持之前最強健的版本)
# ==========================================
def extract_kpi_final(df):
    kpi = {"cost": 0.0, "clicks": 0, "conversions": 0}
    def clean(v):
        if pd.isna(v) or str(v).strip() in ['--', '']: return 0.0
        return float(str(v).replace('$', '').replace(',', '').strip())
    
    # 排除總計行
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
# 4. 頁面：廣告看板 (連結到特定 Project)
# ==========================================
if page == "📈 數據分析看板":
    if current_project_id:
        st.title(f"📈 正在操作：{selected_proj_name}")
        
        f = st.file_uploader(f"為 {selected_proj_name} 上傳專屬報表", type=['csv', 'xlsx'])
        
        if f:
            # (省略之前相同的檔案讀取與 KPI 顯示邏輯)
            try:
                if f.name.endswith('.csv'):
                    tmp = pd.read_csv(f, nrows=5, header=None); f.seek(0)
                    h = 0
                    for i, r in tmp.iterrows():
                        if any(k in "".join(map(str,r.values)) for k in ["廣告活動","費用"]): h=i; break
                    df = pd.read_csv(f, skiprows=h)
                else:
                    tmp = pd.read_excel(f, nrows=5, header=None)
                    h = 0
                    for i, r in tmp.iterrows():
                        if any(k in "".join(map(str,r.values)) for k in ["廣告活動","費用"]): h=i; break
                    df = pd.read_excel(f, header=h)
                
                df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
                data = extract_kpi_final(df)
                
                # KPI 看板
                c1, c2, c3 = st.columns(3)
                c1.metric("活動花費", f"${data['cost']:,.2f}")
                c2.metric("點擊數", f"{data['clicks']:,} 次")
                c3.metric("轉換數", f"{data['conversions']:,} 筆")
                
                st.divider()
                st.subheader("🤖 針對此活動的 AI 優化對話")
                
                # 載入此專案的歷史對話
                chats = load_chats(current_project_id)
                for m in chats:
                    with st.chat_message(m["role"]): st.markdown(m["content"])
                
                # 對話輸入
                q = st.chat_input(f"關於 {selected_proj_name}，有什麼想問 AI？")
                if q and api_key:
                    with st.chat_message("user"): st.markdown(q)
                    save_chat(current_project_id, "user", q)
                    
                    with st.chat_message("assistant"):
                        full_context = f"歷史紀錄:\n{str(chats[-5:])}\n目前數據摘要:\n{df.head(20).to_string()}\n問題: {q}"
                        res = model.generate_content(full_context, stream=True)
                        full = ""
                        placeholder = st.empty()
                        for chunk in res:
                            full += chunk.text
                            placeholder.markdown(full + "▌")
                        placeholder.markdown(full)
                        save_chat(current_project_id, "assistant", full)
            except Exception as e:
                st.error(f"解析失敗: {e}")
    else:
        st.warning("請在左側先建立一個活動項目。")

# (頁面二 A/B 測試邏輯以此類推，也可連結到專案)
