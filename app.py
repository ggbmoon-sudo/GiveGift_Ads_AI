import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import sqlite3
from datetime import datetime
import io

# ==========================================
# 0. 資料庫初始化 (支援多專案隔離)
# ==========================================
def init_db():
    conn = sqlite3.connect('givegift_ads_v2.db') # 使用新版資料庫
    c = conn.cursor()
    # 專案列表
    c.execute('''CREATE TABLE IF NOT EXISTS projects 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, created_at TEXT)''')
    # 對話紀錄 (連結 project_id)
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
# 1. 介面設定與系統人設
# ==========================================
st.set_page_config(page_title="GGB Ads Manager 2026", page_icon="💐", layout="wide")

SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席 AI 廣告優化師。
你的目標是協助使用者管理特定的廣告活動項目。請記住此項目的歷史數據與對話，
提供符合香港市場與尚禮坊高端形象的優化建議。"""

# ==========================================
# 2. 側邊欄：專案切換與模型選擇
# ==========================================
st.sidebar.title("💐 尚禮坊活動管理中樞")

# --- 功能：新增專案 ---
with st.sidebar.expander("➕ 建立新廣告活動項目", expanded=False):
    new_name = st.text_input("活動名稱 (如：2026 中秋企業送禮)")
    if st.button("確認建立"):
        if new_name:
            create_project(new_name)
            st.toast(f"✅ 項目 '{new_name}' 已建立！")
            st.rerun()

# --- 功能：選擇目前專案 ---
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

# --- 功能：最新模型選擇 ---
api_key = st.sidebar.text_input("🔑 API Key:", type="password")
selected_model = st.sidebar.selectbox(
    "🧠 AI 模型引擎版本:",
    [
        "gemini-3.0-pro",    # 2026 最新旗艦
        "gemini-3.0-flash",  # 2026 快速平衡
        "gemini-2.5-pro", 
        "gemini-2.5-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash"
    ],
    index=1 # 預設使用 3.0 Flash 兼顧速度與智慧
)

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(selected_model, system_instruction=SYSTEM_PROMPT)

st.sidebar.divider()
page = st.sidebar.radio("導覽：", ["📈 數據分析看板", "💡 獨立文案生成器"])

# ==========================================
# 3. 數據處理核心 (針對 Google Ads 報表優化)
# ==========================================
def extract_kpi_v3(df):
    kpi = {"cost": 0.0, "clicks": 0, "conversions": 0}
    def clean(v):
        if pd.isna(v) or str(v).strip() in ['--', '']: return 0.0
        return float(str(v).replace('$', '').replace(',', '').replace('%', '').strip())
    
    # 過濾總計行
    df_clean = df[~df.iloc[:, 0].astype(str).str.contains('總計|Total|總和', na=False)].copy()
    
    for col in df_clean.columns:
        c = str(col).lower().strip()
        # 抓總花費 (排除平均、CPC等)
        if ('費用' in c or 'cost' in c) and not any(ex in c for ex in ['平均', '每', 'avg', 'cpc', 'cpm']):
            kpi['cost'] = df_clean[col].apply(clean).sum()
        # 抓點擊
        elif '點擊' in c and '率' not in c:
            kpi['clicks'] = int(df_clean[col].apply(clean).sum())
        # 抓轉換
        elif '轉換' in c and not any(ex in c for ex in ['價值', '率', '費用', 'value']):
            kpi['conversions'] = int(df_clean[col].apply(clean).sum())
    return kpi

# ==========================================
# 4. 頁面邏輯
# ==========================================
if current_pid:
    if page == "📈 數據分析看板":
        st.title(f"📈 項目診斷：{selected_name}")
        
        f = st.file_uploader(f"上傳 {selected_name} 的數據報表", type=['csv', 'xlsx'])
        
        if f:
            try:
                # 智能標題定位
                tmp = pd.read_csv(f, nrows=10, header=None) if f.name.endswith('.csv') else pd.read_excel(f, nrows=10, header=None)
                f.seek(0)
                h = 0
                for i, row in tmp.iterrows():
                    if any(k in "".join(map(str, row.values)) for k in ["廣告活動", "費用", "點擊"]):
                        h = i; break
                
                df = pd.read_csv(f, skiprows=h) if f.name.endswith('.csv') else pd.read_excel(f, header=h)
                df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
                
                # 顯示 KPI
                data = extract_kpi_v3(df)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("活動花費", f"${data['cost']:,.2f}")
                c2.metric("總點擊", f"{data['clicks']:,} 次")
                c3.metric("總轉換", f"{data['conversions']:,} 筆")
                cpa = data['cost']/data['conversions'] if data['conversions'] > 0 else 0
                c4.metric("每次轉換成本", f"${cpa:,.2f}")
                
                st.divider()
                st.subheader(f"💬 {selected_name} 專屬 AI 顧問")
                
                # 顯示歷史紀錄
                chats = load_chats(current_pid)
                for m in chats:
                    with st.chat_message(m["role"]): st.markdown(m["content"])
                
                # 對話輸入
                q = st.chat_input(f"關於 {selected_name} 的後續優化...")
                if q and api_key:
                    with st.chat_message("user"): st.markdown(q)
                    save_chat(current_pid, "user", q)
                    
                    with st.chat_message("assistant"):
                        # 將數據摘要餵給 AI
                        context = f"活動名稱: {selected_name}\n數據摘要:\n{df.head(30).to_string()}\n問題: {q}"
                        res = model.generate_content(context, stream=True)
                        full = ""
                        placeholder = st.empty()
                        for chunk in res:
                            full += chunk.text
                            placeholder.markdown(full + "▌")
                        placeholder.markdown(full)
                        save_chat(current_pid, "assistant", full)
            except Exception as e:
                st.error(f"檔案解析失敗：{e}")

    elif page == "💡 獨立文案生成器":
        st.title(f"💡 文案開發：{selected_name}")
        st.info("這裡生成的文案會參考此項目的背景資訊。")
        # (文案生成邏輯，與之前相似，但會自動帶入專案名稱)
        with st.form("ab"):
            msg = st.text_area("活動核心賣點 (如：滿$1000免運，法國紅酒)")
            if st.form_submit_button("生成 A/B 測試文案") and api_key:
                res = model.generate_content(f"為『尚禮坊』的項目『{selected_name}』生成 A/B 文案。賣點：{msg}")
                st.markdown(res.text)
                save_chat(current_pid, "assistant", f"【系統生成文案】\n{res.text}")

else:
    st.title("🚀 歡迎使用尚禮坊 AI 廣告系統")
    st.info("請先在左側邊欄點擊『➕ 建立新廣告活動項目』來開始您的第一個檔案。")
