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
GID_INPUT_TASK = "1755404595"
TZ_MM = timezone(timedelta(hours=6, minutes=30))


def get_root_dir():
    current = os.path.abspath(os.path.dirname(__file__))
    parent = os.path.abspath(os.path.join(current, ".."))
    if os.path.exists(os.path.join(parent, "Task and WO")):
        return parent
    if os.path.exists(os.path.join(current, "Task and WO")):
        return current
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


def build_dept_assign_html(df_dept: pd.DataFrame) -> tuple[str, int]:
    today = datetime.now(TZ_MM).date()

    def parse_dt(v):
        if not v or v.lower() in ("nan", "none", "-", ""):
            return None
        v = v.split()[0].replace(".", "/")
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(v, fmt).date()
            except Exception:
                pass
        return None

    tbody_rows = []
    dept_counts = {}
    count = 0

    for i in range(len(df_dept)):
        row = df_dept.iloc[i]
        dept = clean_val(row.iloc[1])
        if not dept or dept.lower() in ("nan", "dep assign", "sum"):
            continue
        team = clean_val(row.iloc[2]) if len(row) > 2 else ""
        group_assign = clean_val(row.iloc[3]) if len(row) > 3 else ""
        detailed_content = clean_val(row.iloc[4]) if len(row) > 4 else ""
        target_date = clean_val(row.iloc[6]) if len(row) > 6 else ""
        complete_date = clean_val(row.iloc[9]) if len(row) > 9 else ""

        count += 1
        dept_counts[dept] = dept_counts.get(dept, 0) + 1

        # Team tag class
        team_tag_class = "tag-all"
        t_low = team.lower()
        if "team 01" in t_low or "team 1" in t_low or "t1" in t_low:
            team_tag_class = "tag-t1"
        elif "team 02" in t_low or "team 2" in t_low or "t2" in t_low:
            team_tag_class = "tag-t2"
        elif "team 03" in t_low or "team 3" in t_low or "t3" in t_low:
            team_tag_class = "tag-t3"
        elif "team 04" in t_low or "team 4" in t_low or "t4" in t_low:
            team_tag_class = "tag-t4"

        # Dept tag class
        dept_tag_class = "tag-t2"
        d_low = dept.lower()
        if "admin" in d_low or "asset" in d_low:
            dept_tag_class = "tag-t1"
        elif "cm" in d_low or "m&e" in d_low:
            dept_tag_class = "tag-t2"
        elif "pm" in d_low or "manager" in d_low or "construction" in d_low:
            dept_tag_class = "tag-t3"
        elif "finance" in d_low or "transmission" in d_low:
            dept_tag_class = "tag-t4"

        # Status
        c_dt = parse_dt(complete_date)
        t_dt = parse_dt(target_date)
        if c_dt:
            status_html = f'<span class="status-pill-check sp-verified">✓ Done ({complete_date})</span>'
        elif t_dt and t_dt < today:
            status_html = f'<span class="status-pill-check" style="background:rgba(239,68,68,0.2); color:#f87171; border:1px solid rgba(239,68,68,0.4);"><i class="fa-solid fa-triangle-exclamation"></i> Overdue ({target_date})</span>'
        elif target_date:
            status_html = f'<span class="status-pill-check sp-pending">⏳ In Progress ({target_date})</span>'
        else:
            status_html = '<span class="status-pill-check sp-pending">In Progress</span>'

        t_str = target_date if target_date else "-"
        dept_str = dept if dept else "-"
        team_str = team if team else "-"
        group_str = group_assign if group_assign else "-"
        content_str = detailed_content if detailed_content else "-"

        row_html = f"""            <tr data-dept="{dept}">
              <td>{count}</td>
              <td><span class="team-tag {dept_tag_class}">{dept_str}</span></td>
              <td><span class="team-tag {team_tag_class}">{team_str}</span></td>
              <td style="font-size:0.8rem; color:var(--text-sub); font-weight:600;">{group_str}</td>
              <td style="text-align:left !important; max-width:420px; line-height:1.45; font-weight:600; color:#fff;">{content_str}</td>
              <td style="font-size:0.8rem; color:var(--amber); font-weight:700;">{t_str}</td>
              <td>{status_html}</td>
            </tr>"""
        tbody_rows.append(row_html)

    # Filter buttons
    filter_btns = []
    for d, c in sorted(dept_counts.items(), key=lambda x: -x[1]):
        filter_btns.append(f'<button class="filter-btn" onclick="filterDeptTable(\'{d}\', this)" style="padding:0.25rem 0.6rem; font-size:0.75rem;">{d} ({c})</button>')

    export_time_str = datetime.now(TZ_MM).strftime("%d/%m/%Y %H:%M:%S")

    full_dept_panel = f"""    <!-- 2. DEPARTMENT ASSIGN TAB (Phòng Dep - Live Google Sheet gid={GID_INPUT_TASK}) -->
    <div id="dept-assign-panel" class="tab-panel">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; flex-wrap:wrap; gap:0.5rem;">
        <div>
          <div class="section-head" style="margin-bottom:0.2rem;"><i class="fa-solid fa-building"></i> Department Assignment Overview (Phòng Dep Tasks)</div>
          <div style="font-size:0.8rem; color:var(--text-sub); font-weight:600;"><i class="fa-regular fa-clock"></i> Sheet Sync: <span class="sheet-sync-time" style="color:var(--cyan);">{export_time_str}</span> | Total Active Tasks: <span style="color:var(--emerald);">{count} Tasks Live</span></div>
        </div>
        <div style="display:flex; gap:0.5rem; align-items:center;">
          <button onclick="refreshDeptAssignLive()" class="filter-btn" style="padding:0.35rem 0.8rem; font-size:0.8rem; background:rgba(56,189,248,0.2); border:1px solid var(--cyan); color:#fff; cursor:pointer;"><i class="fa-solid fa-rotate"></i> Đồng bộ Dữ liệu Live</button>
          <span class="status-pill-check sp-verified" style="font-size:0.8rem;"><i class="fa-solid fa-circle-check"></i> {count} Tasks Synced</span>
        </div>
      </div>

      <!-- Quick Filter Pills -->
      <div style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:1rem; background:rgba(30,41,59,0.5); padding:0.6rem 0.8rem; border-radius:8px; border:1px solid rgba(255,255,255,0.05);">
        <span style="font-size:0.8rem; color:var(--text-sub); font-weight:700; display:flex; align-items:center; margin-right:0.3rem;"><i class="fa-solid fa-filter" style="margin-right:0.35rem; color:var(--cyan);"></i> Filter Dept:</span>
        <button class="filter-btn active" onclick="filterDeptTable('ALL', this)" style="padding:0.25rem 0.6rem; font-size:0.75rem;">All ({count})</button>
        {' '.join(filter_btns)}
      </div>

      <div class="card">
        <div style="max-height: 650px; overflow-y: auto; overflow-x: auto;">
          <table class="data-table" id="dept-assign-table">
            <thead>
              <tr>
                <th style="width:40px;">#</th>
                <th>Department</th>
                <th>Assigned Team</th>
                <th>Task Group</th>
                <th style="text-align:left !important; color:var(--cyan);">Detailed Scope & Work Description</th>
                <th>Target Date</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody id="dept-assign-tbody">
{chr(10).join(tbody_rows)}
            </tbody>
          </table>
        </div>
      </div>
    </div>"""

    return full_dept_panel, count


def update_html_file(file_path: str, new_wo_panel_html: str, new_bod_panel_html: str, new_dept_panel_html: str, export_time_str: str) -> bool:
    if not os.path.exists(file_path):
        return False
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Thay thế panel Department Assign
    dept_pat = r'(?s)<!-- 2\. DEPARTMENT ASSIGN TAB.*?</div>\s*</div>(?=\s*<!--\s*(?:3\.|WO DETAIL))'
    if re.search(dept_pat, content):
        content = re.sub(dept_pat, new_dept_panel_html.strip(), content, count=1)
        logger.info(f"Replaced dept-assign-panel in {file_path}")

    # 2. Thay thế panel WO Detail
    pattern = r'(?s)\s*<!-- 3\.\s*WO DETAIL TAB PANEL.*?</div>\s*</div>\s*(?=\s*<!--\s*(?:4\.|3\.|BOD ASSIGN|Settings|GMAIL|\d+\.))'
    if re.search(pattern, content):
        content = re.sub(pattern, "\n\n" + new_wo_panel_html + "\n\n", content, count=1)
        logger.info(f"Replaced wo-detail-panel in {file_path}")
    else:
        alt_pat = r'(?s)<div id="wo-detail-panel"[^>]*>.*?</div>\s*</div>'
        if re.search(alt_pat, content):
            content = re.sub(alt_pat, new_wo_panel_html.strip(), content, count=1)
            logger.info(f"Replaced wo-detail-panel via alt_pat in {file_path}")

    # 3. Thay thế panel BOD Assign
    bod_pat = r'(?s)<!-- 3\. BOD ASSIGN TAB.*?</div>\s*</div>\s*</div>'
    if re.search(bod_pat, content):
        content = re.sub(bod_pat, new_bod_panel_html.strip(), content, count=1)
        logger.info(f"Replaced bod-assign-panel in {file_path}")

    # 4. Thêm script refreshDeptAssignLive & filterDeptTable nếu chưa có
    if "window.refreshDeptAssignLive" not in content and "</body>" in content:
        dept_script = """
<script>
window.filterDeptTable = function(deptName, btn) {
  const buttons = document.querySelectorAll('#dept-assign-panel .filter-btn');
  buttons.forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');

  const rows = document.querySelectorAll('#dept-assign-tbody tr');
  rows.forEach(row => {
    const rowDept = row.getAttribute('data-dept') || '';
    if (deptName === 'ALL' || rowDept.toUpperCase() === deptName.toUpperCase()) {
      row.style.display = '';
    } else {
      row.style.display = 'none';
    }
  });
};

window.refreshDeptAssignLive = async function() {
  const tbody = document.getElementById('dept-assign-tbody');
  if (!tbody) return;
  const btn = document.querySelector('button[onclick="refreshDeptAssignLive()"]');
  if (btn) btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang đồng bộ...';

  try {
    const url = "https://docs.google.com/spreadsheets/d/1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8/gviz/tq?tqx=out:csv&gid=1755404595";
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const text = await resp.text();

    const rows = [];
    let curRow = [], curVal = "", inQuote = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (c === '"') inQuote = !inQuote;
      else if (c === ',' && !inQuote) { curRow.push(curVal); curVal = ""; }
      else if ((c === '\\r' || c === '\\n') && !inQuote) {
        if (c === '\\r' && text[i+1] === '\\n') i++;
        curRow.push(curVal); curVal = "";
        if (curRow.length > 0) rows.push(curRow);
        curRow = [];
      } else curVal += c;
    }
    if (curVal || curRow.length > 0) { curRow.push(curVal); rows.push(curRow); }

    let count = 0;
    const tbodyHtml = [];
    const today = new Date();
    today.setHours(0,0,0,0);

    const parseDateStr = (s) => {
      if (!s) return null;
      const parts = s.trim().split(' ')[0].replace(/\\./g, '/').split('/');
      if (parts.length === 3) {
        return new Date(parseInt(parts[2], 10), parseInt(parts[1], 10) - 1, parseInt(parts[0], 10));
      }
      return null;
    };

    for (let r = 1; r < rows.length; r++) {
      const row = rows[r];
      const dept = (row[1] || "").trim();
      if (!dept || ["nan", "dep assign", "sum"].includes(dept.toLowerCase())) continue;

      const team = (row[2] || "").trim();
      const groupAssign = (row[3] || "").trim();
      const content = (row[4] || "").trim();
      const targetDate = (row[6] || "").trim();
      const completeDate = (row[9] || "").trim();

      count++;

      let teamTagClass = "tag-all";
      const tLow = team.toLowerCase();
      if (tLow.includes("team 01") || tLow.includes("team 1") || tLow.includes("t1")) teamTagClass = "tag-t1";
      else if (tLow.includes("team 02") || tLow.includes("team 2") || tLow.includes("t2")) teamTagClass = "tag-t2";
      else if (tLow.includes("team 03") || tLow.includes("team 3") || tLow.includes("t3")) teamTagClass = "tag-t3";
      else if (tLow.includes("team 04") || tLow.includes("team 4") || tLow.includes("t4")) teamTagClass = "tag-t4";

      let deptTagClass = "tag-t2";
      const dLow = dept.toLowerCase();
      if (dLow.includes("admin") || dLow.includes("asset")) deptTagClass = "tag-t1";
      else if (dLow.includes("cm") || dLow.includes("m&e")) deptTagClass = "tag-t2";
      else if (dLow.includes("pm") || dLow.includes("manager") || dLow.includes("construction")) deptTagClass = "tag-t3";
      else if (dLow.includes("finance") || dLow.includes("transmission")) deptTagClass = "tag-t4";

      let statusHtml = '<span class="status-pill-check sp-pending">In Progress</span>';
      const cDt = parseDateStr(completeDate);
      const tDt = parseDateStr(targetDate);
      if (cDt) {
        statusHtml = `<span class="status-pill-check sp-verified">✓ Done (${completeDate})</span>`;
      } else if (tDt && tDt < today) {
        statusHtml = `<span class="status-pill-check" style="background:rgba(239,68,68,0.2); color:#f87171; border:1px solid rgba(239,68,68,0.4);"><i class="fa-solid fa-triangle-exclamation"></i> Overdue (${targetDate})</span>`;
      } else if (targetDate) {
        statusHtml = `<span class="status-pill-check sp-pending">⏳ In Progress (${targetDate})</span>`;
      }

      tbodyHtml.push(`            <tr data-dept="${dept}">
              <td>${count}</td>
              <td><span class="team-tag ${deptTagClass}">${dept || "-"}</span></td>
              <td><span class="team-tag ${teamTagClass}">${team || "-"}</span></td>
              <td style="font-size:0.8rem; color:var(--text-sub); font-weight:600;">${groupAssign || "-"}</td>
              <td style="text-align:left !important; max-width:420px; line-height:1.45; font-weight:600; color:#fff;">${content || "-"}</td>
              <td style="font-size:0.8rem; color:var(--amber); font-weight:700;">${targetDate || "-"}</td>
              <td>${statusHtml}</td>
            </tr>`);
    }

    tbody.innerHTML = tbodyHtml.join("\\n");
    const syncTimeEl = document.querySelector('#dept-assign-panel .sheet-sync-time');
    if (syncTimeEl) {
      const now = new Date();
      syncTimeEl.textContent = now.toLocaleDateString("vi-VN") + " " + now.toLocaleTimeString("vi-VN", {hour12: false}) + " MMT (Live)";
    }
    console.log(`✅ [Dept Assign] Đồng bộ Live thành công ${count} đầu việc phòng ban từ Google Sheets!`);
  } catch(e) {
    console.error("❌ [Dept Assign] Refresh error:", e);
  } finally {
    if (btn) btn.innerHTML = '<i class="fa-solid fa-rotate"></i> Đồng bộ Dữ liệu Live';
  }
};

document.addEventListener("DOMContentLoaded", function() {
  const deptTabBtn = document.querySelector('button[onclick*="dept-assign-panel"]');
  if (deptTabBtn) {
    const origOnClick = deptTabBtn.getAttribute('onclick') || '';
    if (!origOnClick.includes('refreshDeptAssignLive')) {
      deptTabBtn.setAttribute('onclick', origOnClick + '; window.refreshDeptAssignLive();');
    }
  }
});
</script>
"""
        content = content.replace("</body>", dept_script + "\n</body>")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def main():
    logger.info("Starting Ghế BI-WO-SYNC (Toa WO Detail, BOD Assign & Dept Assign Sync)...")
    logger.info(f"Fetching Tab 'Progress Team Task and WO+Oil' (GID {GID_WO_DETAIL})...")
    df_wo = fetch_csv_gviz(GID_WO_DETAIL)
    logger.info(f"Fetched GID {GID_WO_DETAIL}: {len(df_wo)} rows, {len(df_wo.columns)} cols")

    new_wo_panel_html, export_time_str = build_7_tables_html(df_wo)
    logger.info(f"Built 7 Raw Tables HTML. Export time: {export_time_str}")

    logger.info(f"Fetching Tab 'BOD assign' (GID {GID_BOD_ASSIGN})...")
    df_bod = fetch_csv_gviz(GID_BOD_ASSIGN)
    new_bod_panel_html, bod_row_count = build_bod_assign_html(df_bod)
    logger.info(f"Built BOD Assign HTML with {bod_row_count} live rows.")

    logger.info(f"Fetching Tab 'Input task' (GID {GID_INPUT_TASK})...")
    df_dept = fetch_csv_gviz(GID_INPUT_TASK)
    new_dept_panel_html, dept_row_count = build_dept_assign_html(df_dept)
    logger.info(f"Built Dept Assign HTML with {dept_row_count} live rows.")

    root_dir = get_root_dir()
    target_files = [
        os.path.join(root_dir, "index.html"),
        os.path.join(root_dir, "executive_dashboard.html"),
        os.path.join(root_dir, "Task and WO", "index.html"),
        os.path.join(root_dir, "Task and WO", "executive_dashboard.html"),
        os.path.join(root_dir, "tni-search", "index.html"),
        os.path.join(root_dir, "tni-search", "executive_dashboard.html"),
    ]

    updated_count = 0
    for tf in target_files:
        if update_html_file(tf, new_wo_panel_html, new_bod_panel_html, new_dept_panel_html, export_time_str):
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

    with open(os.path.join(cache_dir, "dept_assign_cache.json"), "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now(TZ_MM).strftime("%d/%m/%Y %H:%M:%S MMT"),
            "rows_count": dept_row_count,
            "html": new_dept_panel_html
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[Ghế BI-WO-SYNC] Hoàn tất đồng bộ {updated_count} files HTML với {bod_row_count} dòng BOD Assign, {dept_row_count} dòng Dept Assign & 7 bảng WO Detail ({export_time_str})!")


if __name__ == "__main__":
    main()
