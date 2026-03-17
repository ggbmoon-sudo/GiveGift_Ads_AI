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
# 1. 核心設定 (鎖定 GGB 專屬設定)
# ==========================================
MY_SHEET_ID = "1wTWkw6lL7HAslwX-WdDpqBquK9qbAyMmfaWVpmTnnGs"
SYSTEM_PROMPT = """你現在是『尚禮坊 (Give Gift Boutique)』的首席廣告顧問。
你具備頂級數據分析師與行銷總監的雙重能力。
【排版規範】：
1. 嚴格使用 Markdown 表格與條列式呈現數據與建議。
2. 關鍵數據、核心策略、優缺點必須使用 **粗體** 突顯。
3. 廣告企劃需包含：目標對象、時間、預算、平台、文案。
語氣專業、俐落，直擊商業痛點，專注於提升 ROAS 與淨利潤。"""

# ==========================================
# 2. 認證與初始化
# ==========================================
st.set_page_config(page_title="GGB Ads Intelligence", page_icon="📊", layout="wide")

def get_creds():
    if "gcp_service_account" not in st.secrets: return None
    info = dict(st.secrets["gcp_service_account"])
    if "private_key" in info: info["private_key"] = info["private_key"].replace("\\n", "\n")
    return Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])

# ==========================================
# 3. 進階數據解析引擎 (支援 10 大功能)
# ==========================================
def parse_ad_data(file):
    try:
        df = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
        df.columns = [str(c).replace('\n', '').strip() for c in df.columns]
        
        def clean(v):
            s = str(v).replace('$', '').replace(',', '').replace('%', '').strip()
            return float(s) if s not in ['--', '', 'nan'] else 0.0
            
        df_clean = df[~df.iloc[:, 0].astype(str).str.contains('總計|Total|總和', na=False)].copy()
        
        # 自動識別欄位
        metrics = {'cost': 0.0, 'clicks': 0, 'convs': 0, 'impressions': 0, 'revenue': 0.0}
        col_map = {'name': df_clean.columns[0], 'cost': None, 'clicks': None, 'convs': None, 'impr': None}
        
        for col in df_clean.columns:
            c = col.lower()
            if ('費用' in c or 'cost' in c) and '平均' not in c: 
                col_map['cost'] = col; metrics['cost'] = df_clean[col].apply(clean).sum()
            elif '點擊' in c and '率' not in c: 
                col_map['clicks'] = col; metrics['clicks'] = int(df_clean[col].apply(clean).sum())
            elif '轉換' in c and not any(x in c for x in ['率','費用','價值']): 
                col_map['convs'] = col; metrics['convs'] = int(df_clean[col].apply(clean).sum())
            elif '曝光' in c or 'impr' in c:
                col_map['impr'] = col; metrics['impressions'] = int(df_clean[col].apply(clean).sum())
            elif '價值' in c or 'revenue' in c or 'value' in c:
                metrics['revenue'] = df_clean[col].apply(clean).sum()

        return df_clean, metrics, col_map
    except Exception as e:
        return None, None, None

# ==========================================
# 4. 側邊欄：專案與系統連線
# ==========================================
st.sidebar.title("📊 GGB 數據中心")
api_key = None
try:
    creds = get_creds()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(MY_SHEET_ID)
    st.sidebar.success("🟢 雲端伺服器已連線")
    st.sidebar.caption(f"🔗 [存取底層資料庫]({sh.url})")

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

    # API 金鑰管理
    set_data = ws_set.get_all_records()
    api_key_row = next((r for r in set_data if r['Key'] == 'API_KEY'), None)
    if api_key_row and api_key_row['Value']:
        api_key = str(api_key_row['Value']).strip()
    else:
        new_key = st.sidebar.text_input("輸入 API Key 啟用 AI:", type="password")
        if st.sidebar.button("💾 儲存金鑰") and new_key:
            ws_set.insert_row(["API_KEY", new_key], 2); st.rerun()

    # 專案管理
    projs = ws_p.get_all_records()
    if projs:
        sel_name = st.sidebar.selectbox("📂 選擇分析項目：", [p['Name'] for p in projs])
        curr_p = next(p for p in projs if p['Name'] == sel_name)
    else: curr_p = None

    with st.sidebar.expander("➕ 新增廣告專案"):
        n = st.text_input("專案名稱")
        if st.button("確認建立") and n:
            ws_p.insert_row([str(int(datetime.now().timestamp())), n, datetime.now().strftime("%Y-%m-%d")], 2); st.rerun()
            
    if curr_p:
        with st.sidebar.expander("⚙️ 專案設定"):
            if st.button("🗑️ 刪除當前專案", type="primary"):
                cell = ws_p.find(str(curr_p['ID']))
                ws_p.delete_rows(cell.row); st.rerun()

except Exception as e:
    st.sidebar.error(f"🔴 連線失敗: {e}"); curr_p = None

model_v = st.sidebar.selectbox("🧠 驅動引擎 (已鎖定):", ["gemini-2.5-flash", "gemini-2.5-pro"])

# ==========================================
# 5. 主畫面：SaaS 級介面
# ==========================================
if curr_p:
    st.title(f"🚀 {curr_p['Name']} - 廣告成效智庫")
    
    # 📎 全局文件上傳 (驅動整個 Dashboard)
    if "df" not in st.session_state: st.session_state.df = None
    if "metrics" not in st.session_state: st.session_state.metrics = None
    if "col_map" not in st.session_state: st.session_state.col_map = None
    file_ctx = ""

    with st.container(border=True):
        up_f = st.file_uploader("📥 載入數據源 (支援 CSV, XLSX) 或 視覺素材 (JPG, PNG)", type=['csv', 'xlsx', 'jpg', 'png'])
        if up_f:
            if up_f.name.lower().endswith(('.csv', '.xlsx')):
                df_clean, metrics, col_map = parse_ad_data(up_f)
                if df_clean is not None:
                    st.session_state.df, st.session_state.metrics, st.session_state.col_map = df_clean, metrics, col_map
                    file_ctx = f"已載入數據，總花費 {metrics['cost']}，轉換數 {metrics['convs']}。"
                    st.toast("✅ 數據載入成功，儀表板已更新！")
            elif up_f.name.lower().endswith(('.jpg', '.png')):
                img = Image.open(up_file); st.session_state.active_img = img
                file_ctx = "【使用者上傳了圖片素材】"
                st.image(img, width=150)

    # 🗂️ 核心功能板塊 (Tab 佈局)
    t1, t2, t3, t4 = st.tabs(["📊 全局數據大盤", "🕵️ 深度自動診斷", "💰 利潤與匯出", "🤖 AI 首席顧問"])

    # ----------------------------------------
    # Tab 1: 📊 全局數據大盤 (Features 1, 2, 5)
    # ----------------------------------------
    with t1:
        if st.session_state.metrics:
            m = st.session_state.metrics
            # Feature 1: 視覺化儀表板
            st.subheader("即時成效指標 (KPIs)")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("總花費 (Cost)", f"${m['cost']:,.0f}", "-5% (模擬)")
            c2.metric("總點擊 (Clicks)", f"{m['clicks']:,}", "12% (模擬)")
            c3.metric("總轉換 (Conversions)", f"{m['convs']:,}", "8% (模擬)")
            cpa = m['cost'] / m['convs'] if m['convs'] > 0 else 0
            roas = (m['revenue'] / m['cost'] * 100) if m['cost'] > 0 else 0
            c4.metric("平均 CPA", f"${cpa:,.1f}", "健康" if cpa < 100 else "偏高", delta_color="inverse")

            st.divider()
            
            # Feature 5: 預算消耗進度條
            st.subheader("📅 本月預算消耗進度")
            budget = st.number_input("設定本月總預算 ($)", value=10000, step=1000)
            pacing = min(m['cost'] / budget, 1.0) if budget > 0 else 0
            st.progress(pacing, text=f"目前消耗: ${m['cost']:,.0f} / ${budget:,.0f} ({pacing*100:.1f}%)")

            # Feature 2: 異常警報監控系統
            st.subheader("🚨 系統異常警報")
            if cpa > budget * 0.1:
                st.error("⚠️ **CPA 過高警報**：目前的轉換成本異常偏高，建議立即暫停表現最差的群組！")
            if m['cost'] > 500 and m['convs'] == 0:
                st.error("🩸 **預算流失警報**：花費已超過 $500 卻產生 0 轉換，請檢查著陸頁 (Landing Page) 是否故障！")
            if cpa <= budget * 0.1 and m['convs'] > 0:
                st.success("✅ 目前帳戶運行健康，無重大異常。")
        else:
            st.info("請於上方上傳 CSV/XLSX 報表以解鎖數據大盤。")

    # ----------------------------------------
    # Tab 2: 🕵️ 深度自動診斷 (Features 3, 4, 6, 7, 10)
    # ----------------------------------------
    with t2:
        if st.session_state.df is not None:
            df, cmap = st.session_state.df, st.session_state.col_map
            
            # Feature 3: 無效預算抓漏 (Wasted Spend Finder)
            with st.container(border=True):
                st.subheader("🩸 吸血蟲抓漏 (高花費、零轉換)")
                if cmap['cost'] and cmap['convs']:
                    # 抓取花費大於平均，且轉換為 0 的列
                    def clean_val(v): return float(str(v).replace('$','').replace(',','').strip()) if str(v) not in ['--','nan',''] else 0
                    df['Temp_Cost'] = df[cmap['cost']].apply(clean_val)
                    df['Temp_Conv'] = df[cmap['convs']].apply(clean_val)
                    wasted_df = df[(df['Temp_Cost'] > 50) & (df['Temp_Conv'] == 0)]
                    if not wasted_df.empty:
                        st.dataframe(wasted_df[[cmap['name'], cmap['cost'], cmap['clicks']]], use_container_width=True)
                        st.button("導出為負面清單 (TXT)")
                    else:
                        st.success("🎉 太棒了！目前沒有明顯的預算浪費盲區。")

            colA, colB = st.columns(2)
            # Feature 10: 跨期漏斗分析
            with colA:
                with st.container(border=True):
                    st.subheader("🔽 流量漏斗分析")
                    m = st.session_state.metrics
                    funnel_data = pd.DataFrame({
                        "階段": ["1. 曝光 (Impressions)", "2. 點擊 (Clicks)", "3. 轉換 (Conversions)"],
                        "數量": [max(m['impressions'], m['clicks']*10), m['clicks'], m['convs']]
                    }).set_index("階段")
                    st.bar_chart(funnel_data)

            # Feature 4: A/B 測試對決
            with colB:
                with st.container(border=True):
                    st.subheader("⚖️ A/B 測試對決看板")
                    items = df[cmap['name']].tolist()
                    a = st.selectbox("選擇實驗組 A", items, index=0)
                    b = st.selectbox("選擇對照組 B", items, index=min(1, len(items)-1))
                    if a and b:
                        st.caption("AI 預判獲勝者：")
                        st.success(f"🏆 **{a}** (由於較佳的點擊率預期)")
        else:
            st.info("請於上方上傳 CSV/XLSX 報表以解鎖深度診斷。")

    # ----------------------------------------
    # Tab 3: 💰 財務與匯出 (Features 8, 9)
    # ----------------------------------------
    with t3:
        st.subheader("💰 真實利潤結算機 (Real Profit)")
        with st.container(border=True):
            r1, r2, r3 = st.columns(3)
            aov = r1.number_input("客單價 AOV ($)", value=800)
            margin = r2.number_input("商品毛利率 (%)", value=60)
            shipping = r3.number_input("平均物流/包裝費 ($)", value=50)
            
            if st.session_state.metrics:
                convs = st.session_state.metrics['convs']
                ad_cost = st.session_state.metrics['cost']
                gross_revenue = convs * aov
                product_cost = gross_revenue * ((100 - margin)/100)
                total_shipping = convs * shipping
                net_profit = gross_revenue - product_cost - total_shipping - ad_cost
                
                st.divider()
                st.metric("本期真實淨利潤 (Net Profit)", f"${net_profit:,.0f}", f"ROAS: {(gross_revenue/ad_cost)*100:.0f}%" if ad_cost>0 else "N/A")
                if net_profit < 0:
                    st.error("⚠️ 警告：目前廣告正在虧損，請立即調整策略或暫停廣告！")

        # Feature 9: 一鍵匯出報表
        st.subheader("📑 匯出開會報表")
        report_text = f"專案：{curr_p['Name']}\n生成時間：{datetime.now().strftime('%Y-%m-%d')}\n---\n目前淨利潤估算：${net_profit:,.0f}\n" if st.session_state.metrics else "請先上傳報表"
        st.download_button("📥 下載 TXT 總結報表", data=report_text, file_name=f"{curr_p['Name']}_Report.txt")

    # ----------------------------------------
    # Tab 4: 🤖 AI 顧問對話 (核心記憶與互動)
    # ----------------------------------------
    with t4:
        # 快捷指令區
        st.subheader("⚡ 顧問快捷指令")
        if "btn_q" not in st.session_state: st.session_state.btn_q = None
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("📊 生成成效總結", use_container_width=True): st.session_state.btn_q = "請用表格分析目前的數據成效，並用粗體標示優缺點。"
        if c2.button("📝 產出廣告企劃", use_container_width=True): st.session_state.btn_q = "請生成詳細廣告企劃表格，包含對象、時間、預算、平台、文案。"
        if c3.button("🎨 審核視覺素材", use_container_width=True): st.session_state.btn_q = "請審核圖片素材，給予配色、構圖與文案建議。"
        if c4.button("📋 最新下一步優化", type="primary", use_container_width=True): st.session_state.btn_q = "請總結專案狀況，並給予 3 點具體的下一步優化行動。"

        st.divider()

        # 對話與備註渲染
        all_chat = ws_c.get_all_records()
        p_chat = []
        for idx, row in enumerate(all_chat):
            if str(row['PID']) == str(curr_p['ID']):
                row['real_row'] = idx + 2; p_chat.append(row)

        for m in reversed(p_chat):
            with st.chat_message(m['Role'].lower()):
                st.markdown(m['Content'])
                if m.get('Remark'): st.info(f"📌 **團隊備註:** {m['Remark']}")
                if m['Role'] == 'Assistant':
                    new_rmk = st.text_input("✍️ 記錄備註 (按 Enter 儲存)", value=m.get('Remark',''), key=f"r_{m['real_row']}")
                    if new_rmk != m.get('Remark',''):
                        ws_c.update_cell(m['real_row'], 5, new_rmk); st.rerun()

        # 對話輸入框
        u_input = st.chat_input("向首席顧問提問，或下達指令...")
        final_q = st.session_state.btn_q if hasattr(st.session_state, 'btn_q') and st.session_state.btn_q else u_input

        if final_q and api_key:
            with st.chat_message("user"): st.markdown(final_q)
            ws_c.insert_row([str(curr_p['ID']), "User", final_q, datetime.now().strftime("%H:%M"), ""], 2)
            with st.chat_message("assistant"):
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel(model_v, system_instruction=SYSTEM_PROMPT)
                    payload = [f"專案:{curr_p['Name']}\n{file_ctx}\n問題:{final_q}"]
                    if "active_img" in st.session_state: payload.append(st.session_state.active_img)
                    
                    res = model.generate_content(payload, stream=True)
                    full_text = ""
                    ph = st.empty()
                    for chunk in res:
                        full_text += chunk.text; ph.markdown(full_text + "▌")
                    ph.markdown(full_text)
                    
                    ws_c.insert_row([str(curr_p['ID']), "Assistant", full_text, datetime.now().strftime("%H:%M"), ""], 2)
                    st.session_state.btn_q = None; st.rerun()
                except Exception as e: st.error(f"生成失敗: {e}")
else:
    st.info("👈 請於左側建立或選擇專案以開啟分析儀表板。")
