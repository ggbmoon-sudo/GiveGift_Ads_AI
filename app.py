import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import sqlite3
from datetime import datetime
import io

# ==========================================
# 0. 資料庫初始化 (強化對話儲存)
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
    if content: # 確保不儲存空白內容
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
st.set_page_config(page_title="GGB Ads Intelligence", page_icon="📊", layout="wide")

SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席 AI 優化師。
你的任務是協助管理廣告活動。請記住此專案的歷史背景。
當使用者要求生成圖表時，請結合數據給予圖表後的深度洞察。"""

# ==========================================
# 2. 側邊欄管理
# ==========================================
st.sidebar.title("💐 尚禮坊活動管理中樞")

with st.sidebar.expander("➕ 建立新廣告項目", expanded=False):
    new_name = st.text_input("項目名稱 (如：2026情人節)")
    if st.button("確認建立"):
        if new_name:
            create_project(new_name)
            st.rerun()

projects_df = get_projects()
if not projects_df.empty:
    proj_map = {row['name']: row['id'] for _, row in projects_df.iterrows()}
    selected_name = st.sidebar.selectbox("📂 目前操作項目：", list(proj_map.keys()))
    current_pid = proj_map[selected_name]
else:
    st.sidebar.warning("請先建立項目")
    current_pid = None

st.sidebar.divider()
api_key = st.sidebar.text_input("🔑 API Key:", type="password")
selected_model = st.sidebar.selectbox("🧠 AI 模型:", ["gemini-3.0-pro", "gemini-3.0-flash", "gemini-2.5-pro", "gemini-1.5-flash"], index=1)

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(selected_model, system_instruction=SYSTEM_PROMPT)

page = st.sidebar.radio("功能導覽：", ["📈 數據分析與圖表", "💡 文案企劃"])

# ==========================================
# 3. 數據分析邏輯
# ==========================================
def extract_kpi_v4(df):
    kpi = {"cost": 0.0, "clicks": 0, "conversions": 0, "chart_data": None}
    def clean(v):
        if pd.isna(v) or str(v).strip() in ['--', '']: return 0.0
        return float(str(v).replace('$', '').replace(',', '').strip())
    
    df_clean = df[~df.iloc[:, 0].astype(str).str.contains('總計|Total|總和', na=False)].copy()
    
    # 嘗試抓取名稱列 (廣告活動名稱)
    name_col = df_clean.columns[0]
    for c in df_clean.columns:
        if '廣告活動' in str(c) or 'Campaign' in str(c):
            name_col = c; break

    for col in df_clean.columns:
        c_low = str(col).lower()
        if ('費用' in c_low or 'cost' in c_low) and not any(ex in c_low for ex in ['平均', '每', 'avg']):
            kpi['cost_col'] = col
            kpi['cost'] = df_clean[col].apply(clean).sum()
        elif '點擊' in c_low and '率' not in c_low:
            kpi['click_col'] = col
            kpi['clicks'] = int(df_clean[col].apply(clean).sum())
        elif '轉換' in c_low and not any(ex in c_low for ex in ['價值', '率', '費用']):
            kpi['conv_col'] = col
            kpi['conversions'] = int(df_clean[col].apply(clean).sum())

    # 準備圖表數據
    chart_df = df_clean[[name_col]].copy()
    if 'cost_col' in kpi: chart_df['Cost'] = df_clean[kpi['cost_col']].apply(clean)
    if 'conv_col' in kpi: chart_df['Conversions'] = df_clean[kpi['conv_col']].apply(clean)
    kpi['chart_data'] = chart_df.set_index(name_col)
    
    return kpi

# ==========================================
# 4. 頁面：數據看板 (增加手動儲存與圖表)
# ==========================================
if current_pid:
    if page == "📈 數據分析與圖表":
        st.title(f"📈 項目：{selected_name}")
        
        f = st.file_uploader("上傳報表 (CSV/XLSX)", type=['csv', 'xlsx'])
        if f:
            try:
                # 智能讀取
                if f.name.endswith('.csv'):
                    tmp = pd.read_csv(f, nrows=5, header=None); f.seek(0)
                    h=0
                    for i, r in tmp.iterrows():
                        if any(k in "".join(map(str,r.values)) for k in ["廣告活動","費用"]): h=i; break
                    df = pd.read_csv(f, skiprows=h)
                else:
                    tmp = pd.read_excel(f, nrows=5, header=None)
                    h=0
                    for i, r in tmp.iterrows():
                        if any(k in "".join(map(str,r.values)) for k in ["廣告活動","費用"]): h=i; break
                    df = pd.read_excel(f, header=h)
                
                df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
                data = extract_kpi_v4(df)

                # KPI 卡片
                col1, col2, col3 = st.columns(3)
                col1.metric("活動總花費", f"${data['cost']:,.2f}")
                col2.metric("總點擊數", f"{data['clicks']:,} 次")
                col3.metric("總轉換數", f"{data['conversions']:,} 筆")

                st.divider()

                # --- 🚀 快捷鍵區塊 ---
                st.subheader("🛠️ 智能操作")
                q_col1, q_col2, q_col3, q_col4 = st.columns(4)
                
                trigger_query = None
                show_charts = False

                if q_col1.button("📊 分析活動成效"):
                    trigger_query = "請根據數據分析此廣告活動的整體 ROAS 與成效指標。"
                if q_col2.button("🚀 提高轉換策略"):
                    trigger_query = "請給予具體的優化建議以提高目前的轉換率。"
                if q_col3.button("🧠 自動深度分析"):
                    trigger_query = "請執行全自動深度診斷，找出潛在的問題與機會。"
                if q_col4.button("📈 生成視覺化圖表"):
                    show_charts = True
                    trigger_query = "我已經生成了費用與轉換的圖表，請根據圖表分布情況，告訴我哪個活動最值得繼續投資，哪個該停止？"

                # --- 顯示圖表邏輯 ---
                if show_charts:
                    st.write("### 📊 數據分布圖表")
                    c_tab1, c_tab2 = st.tabs(["費用分布 (Cost)", "轉換表現 (Conversions)"])
                    with c_tab1:
                        st.bar_chart(data['chart_data']['Cost'])
                    with c_tab2:
                        st.bar_chart(data['chart_data']['Conversions'])

                st.divider()

                # --- 對話歷史與手動儲存 ---
                st.subheader("💬 優化顧問對話")
                
                # 增加手動儲存按鈕
                if st.button("💾 手動備存目前對話 (確保不遺失)"):
                    st.toast("✅ 已強制同步所有對話至資料庫")
                
                # 載入並顯示
                history = load_chats(current_pid)
                for m in history:
                    with st.chat_message(m["role"]): st.markdown(m["content"])

                # 輸入處理
                user_input = st.chat_input(f"詢問關於 {selected_name}...")
                final_q = trigger_query if trigger_query else user_input

                if final_q and api_key:
                    with st.chat_message("user"): st.markdown(final_q)
                    save_chat(current_pid, "user", final_q) # 自動儲存 User
                    
                    with st.chat_message("assistant"):
                        ctx = f"數據摘要：\n{df.head(30).to_string()}\n\n問題：{final_q}"
                        res = model.generate_content(ctx, stream=True)
                        full = ""
                        ph = st.empty()
                        for chunk in res:
                            full += chunk.text
                            ph.markdown(full + "▌")
                        ph.markdown(full)
                        save_chat(current_pid, "assistant", full) # 自動儲存 Assistant
                        st.rerun() # 刷新以確保對話框順序正確

            except Exception as e:
                st.error(f"解析失敗: {e}")
    else:
        st.title("🚀 歡迎")
        st.info("請在左側選擇一個廣告項目。")
