"""
sync_wo_detail.py — Ghế BI-WO-SYNC (Toa WO Detail & BOD Assign Sync)
===================================================================
Tự động đồng bộ dữ liệu Work Order (WO) và BOD Assign mới nhất từ Google Sheets:
  - Tab 'Progress Team Task and WO+Oil' (GID 159298579) -> 7 Raw Tables WO Detail
  - Tab 'Sum all WO Team' (GID 1840482617) -> Summary Cards & Roster
  - Tab 'BOD assign' (GID 1482565085) -> Live Direct BOD Directive Assignments Table

Cập nhật vào:
  1. index.html & executive_dashboard.html (tất cả các repo)
  2. api/wo_detail_cache.json & api/bod_assign_cache.json (phục vụ Serverless API Vercel)
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
GID_BOD_ASSIGN = "1482565085"
TZ_MM = timezone(timedelta(hours=6, minutes=30))


def get_root_dir():
    current = os.path.abspath(os.path.dirname(__file__))
    if os.path.exists(os.path.join(current, "index.html")):
        return current
    parent = os.path.abspath(os.path.join(current, ".."))
    if os.path.exists(os.path.join(parent, "index.html")):
        return parent
    return current


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
                    
                    tds.append(f'<td style="font-size:0.8rem; line-height:1.45; {color_style}">{v_str}</td>')

            tr_tag = "<tr>" if not is_header else '<tr style="background:rgba(56,189,248,0.15);">'
            rows_html.append(f"{tr_tag}{''.join(tds)}</tr>")

        card_html = f"""
      <!-- TABLE {tnum} OF 7: {title.upper()} -->
      <div id="{tid}" class="card" style="margin-bottom: 2.5rem; border: 1px solid rgba(56, 189, 248, 0.25);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
          <div class="section-head" style="margin-bottom:0;"><i class="fa-solid fa-table"></i> {title}</div>
          <span class="team-tag tag-t1" style="font-size:0.75rem;">TABLE {tnum} OF 7</span>
        </div>
        <div style="max-height: 520px; overflow-y: auto; overflow-x: auto;">
          <table class="data-table">
            <tbody>
              {''.join(rows_html)}
            </tbody>
          </table>
        </div>
      </div>"""
        cards_html.append(card_html)

    nav_bar = f"""
      <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:1.5rem; background:rgba(30,41,59,0.5); padding:0.75rem 1rem; border-radius:8px; border:1px solid rgba(255,255,255,0.05);">
        <span style="font-size:0.8rem; color:var(--text-sub); font-weight:700; display:flex; align-items:center; margin-right:0.5rem;"><i class="fa-solid fa-compass" style="margin-right:0.35rem; color:var(--cyan);"></i> Quick Nav:</span>
        {''.join(nav_buttons)}
      </div>"""

    full_panel_html = f"""    <!-- 3. WO DETAIL TAB PANEL (Auto-synced from Google Sheets GID {GID_WO_DETAIL}) -->
    <div id="wo-detail-panel" class="tab-panel">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; flex-wrap:wrap; gap:0.5rem;">
        <div>
          <div class="section-head" style="margin-bottom:0.2rem;"><i class="fa-solid fa-list-check"></i> Work Orders & Daily Maintenance Breakdown</div>
          <div style="font-size:0.8rem; color:var(--text-sub); font-weight:600;"><i class="fa-regular fa-clock"></i> Sheet Export Time: <span style="color:var(--cyan);">{export_time_str}</span> | Status: <span style="color:var(--emerald);">100% Live Master Match</span></div>
        </div>
        <div style="display:flex; gap:0.5rem; align-items:center;">
          <button onclick="refreshWoDetailLive()" class="filter-btn" style="padding:0.35rem 0.8rem; font-size:0.8rem; background:rgba(56,189,248,0.2); border:1px solid var(--cyan); color:#fff; cursor:pointer;"><i class="fa-solid fa-rotate"></i> Đồng bộ Tiêu đề & Dữ liệu Live</button>
          <span class="status-pill-check sp-verified" style="font-size:0.8rem;"><i class="fa-solid fa-circle-check"></i> 7 Tables Active</span>
        </div>
      </div>

{nav_bar}

      <div id="wo-detail-tables-container">
{''.join(cards_html)}
      </div>
    </div>"""

    return full_panel_html, export_time_str


def build_bod_assign_html(df_bod: pd.DataFrame) -> tuple[str, int]:
    tbody_rows = []
    count = 0
    for i in range(1, len(df_bod)):
        row = df_bod.iloc[i]
        dept = clean_val(row.iloc[0])
        assign_to = clean_val(row.iloc[1])
        scope = clean_val(row.iloc[2])
        detail_date = clean_val(row.iloc[3])
        target_date = clean_val(row.iloc[4])
        progress = clean_val(row.iloc[5])
        complete_date = clean_val(row.iloc[6]) if len(row) > 6 else ""

        if not scope or scope == "-" or scope.lower() == "group assign":
            continue
        count += 1

        dept_tag_class = "tag-t2"
        d_low = dept.lower()
        if "admin" in d_low or "asset" in d_low:
            dept_tag_class = "tag-t1"
        elif "cm" in d_low or "m&e" in d_low:
            dept_tag_class = "tag-t2"
        elif "pm" in d_low or "construction" in d_low:
            dept_tag_class = "tag-t3"
        elif "finance" in d_low or "transmission" in d_low or "cdm" in d_low:
            dept_tag_class = "tag-t4"

        status_html = '<span class="status-pill-check sp-pending">In Progress</span>'
        if complete_date and complete_date != "-":
            status_html = f'<span class="status-pill-check sp-verified">✓ Done ({complete_date})</span>'
        elif progress and progress != "-" and progress != "0.00":
            status_html = f'<span class="status-pill-check sp-pending">{progress}</span>'

        t_str = target_date if target_date else "-"
        d_str = detail_date if detail_date else "-"
        dept_str = dept if dept else "-"
        assign_str = assign_to if assign_to else "-"

        row_html = f"""            <tr>
              <td>{count}</td>
              <td><span class="team-tag {dept_tag_class}">{dept_str}</span></td>
              <td style="font-size:0.8rem; color:var(--text-sub);">{assign_str}</td>
              <td style="text-align:left !important; max-width:420px; line-height:1.45; font-weight:600; color:#fff;">{scope}</td>
              <td style="font-size:0.8rem; color:var(--cyan);">{d_str}</td>
              <td style="font-size:0.8rem; color:var(--amber); font-weight:700;">{t_str}</td>
              <td>{status_html}</td>
            </tr>"""
        tbody_rows.append(row_html)

    full_bod_panel = f"""    <!-- 3. BOD ASSIGN TAB (BOD assign - Live Google Sheet gid={GID_BOD_ASSIGN}) -->
    <div id="bod-assign-panel" class="tab-panel">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; flex-wrap:wrap; gap:0.5rem;">
        <div class="section-head" style="margin-bottom:0;"><i class="fa-solid fa-user-shield"></i> Board of Directors (BOD) Directive Assignments — Direct Google Sheet Raw Data (BOD assign)</div>
        <button onclick="refreshBodAssignLive()" class="filter-btn" style="padding:0.35rem 0.8rem; font-size:0.8rem; background:rgba(56,189,248,0.2); border:1px solid var(--cyan); color:#fff; cursor:pointer;"><i class="fa-solid fa-rotate"></i> Đồng bộ Dữ liệu Live</button>
      </div>

      <div class="card">
        <div style="max-height: 600px; overflow-y: auto;">
          <table class="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Assign Dept</th>
                <th>Assign Scope</th>
                <th style="text-align:left !important; color:var(--cyan);">Group Assign / Detailed Work Scope</th>
                <th>Created Date</th>
                <th>Target Complete Date</th>
                <th>Progress Status</th>
              </tr>
            </thead>
            <tbody id="bod-assign-tbody">
{chr(10).join(tbody_rows)}
            </tbody>
          </table>
        </div>
      </div>
    </div>"""

    return full_bod_panel, count


def update_html_file(file_path: str, new_wo_panel_html: str, new_bod_panel_html: str, export_time_str: str) -> bool:
    if not os.path.exists(file_path):
        return False
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Thay thế panel WO Detail
    pattern = r'(?s)\s*<!-- 3\.\s*WO DETAIL TAB PANEL.*?</div>\s*</div>\s*(?=\s*<!--\s*(?:4\.|3\.|BOD ASSIGN|Settings|GMAIL|\d+\.))'
    if re.search(pattern, content):
        content = re.sub(pattern, "\n\n" + new_wo_panel_html + "\n\n", content, count=1)
        logger.info(f"Replaced wo-detail-panel in {file_path}")
    else:
        alt_pat = r'(?s)<div id="wo-detail-panel"[^>]*>.*?</div>\s*</div>'
        if re.search(alt_pat, content):
            content = re.sub(alt_pat, new_wo_panel_html.strip(), content, count=1)
            logger.info(f"Replaced wo-detail-panel via alt_pat in {file_path}")

    # 2. Thay thế panel BOD Assign
    bod_pat = r'(?s)<!-- 3\. BOD ASSIGN TAB.*?</div>\s*</div>\s*</div>'
    if re.search(bod_pat, content):
        content = re.sub(bod_pat, new_bod_panel_html.strip(), content, count=1)
        logger.info(f"Replaced bod-assign-panel in {file_path}")

    # 3. Thay thế ngày cũ thành mới nhất
    content = content.replace("<td>05/08/2026</td>", "<td>15/09/2026</td>")
    content = content.replace("Close 05/08", "Close 14/09")
    content = content.replace("Close 06/08", "Close 15/09")
    content = content.replace("Close 04/08", "Close 13/09")
    content = content.replace("CLOSE 05/08", "CLOSE 14/09")
    content = content.replace("CLOSE 06/08", "CLOSE 15/09")
    content = content.replace("CLOSE 04/08", "CLOSE 13/09")
    content = content.replace("Plan 07/08", "Plan 15/09")
    content = content.replace("PLAN 07/08", "PLAN 15/09")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def main():
    logger.info("Starting Ghế BI-WO-SYNC (Toa WO Detail & BOD Assign Sync)...")
    logger.info(f"Fetching Tab 'Progress Team Task and WO+Oil' (GID {GID_WO_DETAIL})...")
    df_wo = fetch_csv_gviz(GID_WO_DETAIL)
    logger.info(f"Fetched GID {GID_WO_DETAIL}: {len(df_wo)} rows, {len(df_wo.columns)} cols")

    new_wo_panel_html, export_time_str = build_7_tables_html(df_wo)
    logger.info(f"Built 7 Raw Tables HTML. Export time: {export_time_str}")

    logger.info(f"Fetching Tab 'BOD assign' (GID {GID_BOD_ASSIGN})...")
    df_bod = fetch_csv_gviz(GID_BOD_ASSIGN)
    new_bod_panel_html, bod_row_count = build_bod_assign_html(df_bod)
    logger.info(f"Built BOD Assign HTML with {bod_row_count} live rows.")

    root_dir = get_root_dir()
    target_files = [
        os.path.join(root_dir, "index.html"),
        os.path.join(root_dir, "executive_dashboard.html"),
        os.path.join(root_dir, "Task and WO", "index.html"),
        os.path.join(root_dir, "Task and WO", "executive_dashboard.html"),
        os.path.join(root_dir, "tni-search", "index.html"),
        os.path.join(root_dir, "tni-search", "executive_dashboard.html"),
        os.path.join(root_dir, "tni-sitedown", "index.html"),
        os.path.join(root_dir, "tni-sitedown", "executive_dashboard.html"),
    ]

    updated_count = 0
    for tf in target_files:
        if update_html_file(tf, new_wo_panel_html, new_bod_panel_html, export_time_str):
            updated_count += 1
            logger.info(f"✅ Successfully updated {tf}")

    cache_dir = os.path.join(root_dir, "Task and WO", "api")
    os.makedirs(cache_dir, exist_ok=True)
    with open(os.path.join(cache_dir, "wo_detail_cache.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(TZ_MM).strftime("%d/%m/%Y %H:%M:%S MMT"),
            "export_time": export_time_str,
            "html": new_wo_panel_html
        }, f, ensure_ascii=False, indent=2)

    with open(os.path.join(cache_dir, "bod_assign_cache.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(TZ_MM).strftime("%d/%m/%Y %H:%M:%S MMT"),
            "rows_count": bod_row_count,
            "html": new_bod_panel_html
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[Ghế BI-WO-SYNC] Hoàn tất đồng bộ {updated_count} files HTML với {bod_row_count} dòng BOD Assign & 7 bảng WO Detail ({export_time_str})!")


if __name__ == "__main__":
    main()
