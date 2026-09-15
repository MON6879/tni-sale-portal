"""
sync_wo_detail.py — Ghế BI-WO-SYNC (Toa WO Detail)
==================================================
Tự động đồng bộ dữ liệu Work Order (WO) mới nhất từ Google Sheets:
  - Tab 'Progress Team Task and WO+Oil' (GID 159298579) -> 7 Raw Tables WO Detail
  - Tab 'Sum all WO Team' (GID 1840482617) -> Summary Cards & Roster

Cập nhật vào:
  1. index.html & executive_dashboard.html
  2. api/wo_detail_cache.json (phục vụ Serverless API Vercel)
"""

import os
import re
import io
import json
import logging
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BI-WO-SYNC")

SPREADSHEET_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8"
GID_WO_DETAIL  = "159298579"
GID_SUM_ALL    = "1840482617"
TZ_MM = timezone(timedelta(hours=6, minutes=30))

def fetch_csv_gviz(gid: str, timeout: int = 30) -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid={gid}"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.text), header=None, dtype=str, on_bad_lines="skip")

def clean_val(v):
    if pd.isna(v) or v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none", "#n/a", "#na", "#ref!", "#value!"):
        return ""
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s

def build_7_tables_html(df_wo: pd.DataFrame) -> tuple[str, str]:
    table_ranges = [
        (0, 6, "Table 1: Progress Team Task & Work Orders Breakdown (Cols A-G)", "wo-table-1", 1),
        (10, 15, "Table 2: Department & Group Assign Tasks Roster (Cols K-P)", "wo-table-2", 2),
        (18, 30, "Table 3: Engineers' Daily Maintenance & Filter Breakdown - Date 1 (Cols S-AE)", "wo-table-3", 3),
        (33, 45, "Table 4: Engineers' Daily Maintenance & Filter Breakdown - Date 2 (Cols AH-AT)", "wo-table-4", 4),
        (48, 60, "Table 5: Engineers' Daily Maintenance & Filter Breakdown - Date 3 (Cols AW-BI)", "wo-table-5", 5),
        (63, 74, "Table 6: Engineers' Daily Maintenance & Engine Oil Breakdown (Cols BL-BW)", "wo-table-6", 6),
        (76, 87, "Table 7: Engineers' Daily Maintenance & Water Coolant Breakdown (Cols BY-CJ)", "wo-table-7", 7)
    ]

    cards_html = []
    nav_buttons = []
    
    # Tìm export time từ sheet
    export_time_str = datetime.now(TZ_MM).strftime("%d/%m/%Y %H:%M:%S")
    for r in range(min(5, len(df_wo))):
        for c in range(min(10, len(df_wo.columns))):
            val = str(df_wo.iloc[r, c])
            m = re.search(r"Ex:?\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}(?::\d{2})?)", val, re.IGNORECASE)
            if m:
                export_time_str = m.group(1)
                break

    for sc, ec, title, tid, tnum in table_ranges:
        nav_buttons.append(
            f'<a href="#{tid}" class="filter-btn" style="text-decoration:none; padding:0.3rem 0.65rem; font-size:0.75rem;">'
            f'<i class="fa-solid fa-table"></i> Table {tnum}</a>'
        )
        if ec >= len(df_wo.columns):
            ec = len(df_wo.columns) - 1
        if sc > ec:
            continue

        sub_df = df_wo.iloc[:, sc:ec+1].copy()
        # Lọc bỏ các dòng hoàn toàn trống
        non_empty_mask = sub_df.apply(lambda row: any(clean_val(v) != "" for v in row), axis=1)
        sub_df = sub_df[non_empty_mask].reset_index(drop=True)
        if len(sub_df) == 0:
            continue

        rows_html = []
        for r_idx in range(len(sub_df)):
            row_vals = sub_df.iloc[r_idx]
            tds = []
            is_header = (r_idx == 0)
            
            for c_idx, val in enumerate(row_vals):
                v_str = clean_val(val)
                if not v_str:
                    v_str = "-"
                
                if is_header:
                    tds.append(
                        f'<th style="background:rgba(15,23,42,0.9); color:var(--cyan); white-space:nowrap; font-weight:800;">'
                        f'{v_str}</th>'
                    )
                else:
                    color_style = ""
                    if v_str.startswith("TNI"):
                        color_style = "color:#fff;"
                    elif v_str.startswith("Total:"):
                        color_style = "color:var(--emerald); font-weight:600;"
                    elif "8KVA:" in v_str:
                        color_style = "color:var(--amber); font-weight:600;"
                    
                    tds.append(
                        f'<td style="font-size:0.8rem; line-height:1.45; {color_style}">'
                        f'{v_str}</td>'
                    )
            
            tr_tag = '<tr>' if not is_header else '<tr style="background:rgba(56,189,248,0.15);">'
            rows_html.append(f"{tr_tag}{''.join(tds)}</tr>")

        tbody_content = "\n".join(rows_html)
        card = f"""      <!-- TABLE {tnum} OF 7: {title.upper()} -->
      <div id="{tid}" class="card" style="margin-bottom: 2.5rem; border: 1px solid rgba(56, 189, 248, 0.25);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
          <div class="section-head" style="margin-bottom:0;"><i class="fa-solid fa-table"></i> {title}</div>
          <span class="team-tag tag-t1" style="font-size:0.75rem;">TABLE {tnum} OF 7</span>
        </div>
        <div style="max-height: 520px; overflow-y: auto; overflow-x: auto;">
          <table class="data-table">
            <tbody>
{tbody_content}
            </tbody>
          </table>
        </div>
      </div>"""
        cards_html.append(card)

    nav_html = " ".join(nav_buttons)
    full_panel = f"""                    <!-- 3. WO DETAIL TAB PANEL (All 7 Raw Tables from Sheet 'Progress Team Task and WO+Oil' - GID 159298579) -->
    <div id="wo-detail-panel" class="tab-panel">
      <div class="header-card" style="margin-bottom: 1.2rem; padding: 1.1rem 1.4rem;">
        <!-- DÒNG 1: TIÊU ĐỀ BẢNG RAW & GID TAG -->
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.6rem;">
          <h2 style="font-size:1.25rem; font-weight:800; color:#fff; margin:0; display:flex; align-items:center; gap:0.5rem;"><i class="fa-solid fa-table-list" style="color:var(--cyan);"></i> Raw Google Sheet Import: Tables 1 to 7 <span class="welcome-badge" style="font-size:0.75rem; padding:0.25rem 0.65rem; margin-left:0.4rem; vertical-align:middle;"><i class="fa-solid fa-database"></i> Tab: Progress Team Task and WO+Oil (GID 159298579)</span></h2>
          <button onclick="refreshWoDetailLive()" class="filter-btn" style="padding:0.35rem 0.8rem; font-size:0.8rem; background:rgba(56,189,248,0.2); border:1px solid var(--cyan); color:#fff; cursor:pointer;"><i class="fa-solid fa-rotate"></i> Đồng bộ Tiêu đề & Dữ liệu Live</button>
        </div>
        <!-- DÒNG 2: THANH ĐIỀU HƯỚNG NHANH QUICK JUMP -->
        <div style="margin-top: 0.65rem; display:flex; flex-wrap:wrap; gap:0.4rem; align-items:center;">
          <span style="font-size:0.8rem; font-weight:700; color:var(--text-sub); margin-right:0.2rem;"><i class="fa-solid fa-arrow-down-short-wide"></i> Quick Jump:</span>
          {nav_html}
        </div>
      </div>

      <div id="wo-detail-tables-container">
""" + "\n\n".join(cards_html) + """
      </div>
    </div>"""

    return full_panel, export_time_str


def update_html_file(file_path: str, new_panel_html: str, export_time_str: str) -> bool:
    if not os.path.exists(file_path):
        return False
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Thay thế panel WO Detail
    pattern = r'(?s)\s*<!-- 3\.\s*WO DETAIL TAB PANEL.*?</div>\s*</div>\s*(?=\s*<!--\s*(?:4\.|3\.|BOD ASSIGN|Settings|GMAIL|\d+\.))'
    if re.search(pattern, content):
        content = re.sub(pattern, "\n\n" + new_panel_html + "\n\n", content, count=1)
        logger.info(f"Replaced wo-detail-panel in {file_path}")
    else:
        alt_pat = r'(?s)<div id="wo-detail-panel"[^>]*>.*?</div>\s*</div>'
        if re.search(alt_pat, content):
            content = re.sub(alt_pat, new_panel_html.strip(), content, count=1)
            logger.info(f"Replaced wo-detail-panel via alt_pat in {file_path}")
        else:
            logger.warning(f"Could not locate wo-detail-panel in {file_path}")

    # 2. Thay thế ngày cũ 05/08 thành ngày mới nhất
    content = content.replace("<td>05/08/2026</td>", "<td>15/09/2026</td>")
    content = content.replace("Close 05/08", "Close 14/09")
    content = content.replace("Close 06/08", "Close 15/09")
    content = content.replace("Close 04/08", "Close 13/09")
    content = content.replace("CLOSE 05/08", "CLOSE 14/09")
    content = content.replace("CLOSE 06/08", "CLOSE 15/09")
    content = content.replace("CLOSE 04/08", "CLOSE 13/09")
    content = content.replace("Plan 07/08", "Plan 15/09")
    content = content.replace("PLAN 07/08", "PLAN 15/09")

    # 3. Sửa URL refreshWoDetailLive để dùng gviz/tq (0 CORS) và fallback API
    old_fetch_url = 'const url = "https://docs.google.com/spreadsheets/d/1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8/export?format=csv&gid=159298579";'
    new_fetch_url = 'const url = "https://docs.google.com/spreadsheets/d/1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8/gviz/tq?tqx=out:csv&gid=159298579";'
    content = content.replace(old_fetch_url, new_fetch_url)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def main():
    logger.info("Starting Ghế BI-WO-SYNC (Toa WO Detail)...")
    logger.info(f"Fetching Tab 'Progress Team Task and WO+Oil' (GID {GID_WO_DETAIL})...")
    df_wo = fetch_csv_gviz(GID_WO_DETAIL)
    logger.info(f"Fetched GID {GID_WO_DETAIL}: {len(df_wo)} rows, {len(df_wo.columns)} cols")

    new_panel_html, export_time_str = build_7_tables_html(df_wo)
    logger.info(f"Built 7 Raw Tables HTML. Export time: {export_time_str}")

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    target_files = [
        os.path.join(base_dir, "index.html"),
        os.path.join(base_dir, "executive_dashboard.html"),
        os.path.join(base_dir, "Task and WO", "index.html"),
        os.path.join(base_dir, "Task and WO", "executive_dashboard.html"),
        os.path.join(base_dir, "tni-search", "index.html"),
        os.path.join(base_dir, "tni-search", "executive_dashboard.html"),
    ]

    updated_count = 0
    for tf in target_files:
        if update_html_file(tf, new_panel_html, export_time_str):
            updated_count += 1
            logger.info(f"✅ Successfully updated {tf}")

    cache_file = os.path.join(base_dir, "Task and WO", "api", "wo_detail_cache.json")
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(TZ_MM).strftime("%d/%m/%Y %H:%M:%S MMT"),
            "export_time": export_time_str,
            "html": new_panel_html
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ Saved cache to {cache_file}")

    print(f"\n[Ghế BI-WO-SYNC] Hoàn tất đồng bộ {updated_count} files HTML với số liệu WO mới nhất ({export_time_str})!")

if __name__ == "__main__":
    main()
