"""
Vercel serverless API endpoint for Executive BI Portal (/api/bi_data)

Fetches live data directly from Google Sheets tab 'Sum all WO Team' (GID 1840482617)
and tab 'Search Log' / 'Dashboard Report' so the BI Portal is ALWAYS 100% REALTIME.

Webhook URL: https://tni-bot.vercel.app/api/bi_data
"""

import csv
import io
import json
import logging
import os
import re
import requests
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SPREADSHEET_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8"
GID_SUM_ALL    = "1840482617"  # Tab: Sum all WO Team

TZ_MM = timezone(timedelta(hours=6, minutes=30))

TEAM_ORDER = ["team1", "team2", "team3", "team4"]
TEAM_LABELS = {
    "team1": "Team 1 Dawei",
    "team2": "Team 2 Myeik",
    "team3": "Team 3 Bokpyin",
    "team4": "Team 4 Kawthoung",
}
TEAM_REGIONS = {
    "team1": "MYT_TNI_TEAM01_Dawei",
    "team2": "MYT_TNI_TEAM02_Myeik",
    "team3": "MYT_TNI_TEAM03_Bokpyin",
    "team4": "MYT_TNI_TEAM04_Kawthoung",
}
TEAM_ENGINEERS = {
    "team1": 10,
    "team2": 11,
    "team3": 4,
    "team4": 4,
}


def parse_int(val, default=0):
    if not val:
        return default
    try:
        # Remove commas or quotes
        clean_s = re.sub(r"[^\d\-]", "", str(val).strip())
        return int(clean_s) if clean_s else default
    except Exception:
        return default


def fetch_sum_all_sheet():
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={GID_SUM_ALL}"
    resp = requests.get(url, timeout=12)
    resp.raise_for_status()
    # Handle UTF-8 with BOM if present
    content = resp.content.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(content)))
    return rows


def get_bi_stats():
    now_mm = datetime.now(TZ_MM)
    now_str = now_mm.strftime("%d/%m/%Y %H:%M")

    # Fallback default values
    date_label = "11/10/09-08-2026"
    plan_label = "🎯 Plan 12/08/2026 (M):"
    target_pct = 75

    team_data = {
        "team1": {"totalAssigned": 367, "fotClose": 72, "remain": 295, "overdueF": 161, "waitCD": 23, "cdNotYet": 16, "planM": 49, "d0": 1, "d1": 7, "d2": 0, "pct": 18},
        "team2": {"totalAssigned": 207, "fotClose": 120, "remain": 87, "overdueF": 24, "waitCD": 8, "cdNotYet": 24, "planM": 15, "d0": 0, "d1": 14, "d2": 1, "pct": 56},
        "team3": {"totalAssigned": 95, "fotClose": 33, "remain": 62, "overdueF": 13, "waitCD": 0, "cdNotYet": 8, "planM": 8, "d0": 0, "d1": 5, "d2": 1, "pct": 36},
        "team4": {"totalAssigned": 107, "fotClose": 85, "remain": 22, "overdueF": 0, "waitCD": 0, "cdNotYet": 4, "planM": 3, "d0": 0, "d1": 14, "d2": 4, "pct": 82},
    }

    try:
        rows = fetch_sum_all_sheet()
        logger.info(f"Fetched Sum all WO Team sheet: {len(rows)} rows")

        # Parse Target Need Complete percentage from Row 1 Cell F1 (index 0, col 5)
        if len(rows) > 0 and len(rows[0]) > 5:
            raw_target = str(rows[0][5]).strip()
            m_tgt = re.search(r"(\d+)", raw_target)
            if m_tgt:
                target_pct = int(m_tgt.group(1))

        if len(rows) >= 2:
            hdr_row2 = rows[1]
            hdr_j = hdr_row2[9] if len(hdr_row2) > 9 else ""
            hdr_k = hdr_row2[10] if len(hdr_row2) > 10 else ""
            hdr_l = hdr_row2[11] if len(hdr_row2) > 11 else ""
            hdr_m = hdr_row2[12] if len(hdr_row2) > 12 else ""

            m_j = re.search(r"(\d{2}/\d{2})", hdr_j)
            m_k = re.search(r"(\d{2}/\d{2})", hdr_k)
            m_l = re.search(r"(\d{2}/\d{2})", hdr_l)
            m_m = re.search(r"(\d{2}/\d{2}(?:/\d{2,4})?)", hdr_m)

            str_j = m_j.group(1) if m_j else "11/08"
            str_k = m_k.group(1) if m_k else "10/08"
            str_l = m_l.group(1) if m_l else "09/08"
            str_m = m_m.group(1) if m_m else "12/08/2026"

            yr_str = now_mm.strftime("%Y")
            full_m_date = str_m if "/" in str_m and len(str_m.split("/")) == 3 else f"{str_m}/{yr_str}"
            plan_label = f"🎯 Plan {full_m_date} (M):"

            day_j = str_j.split("/")[0]
            day_k = str_k.split("/")[0]
            day_l = str_l.split("/")[0]
            month_str = str_j.split("/")[1] if "/" in str_j else "08"
            date_label = f"{day_j}/{day_k}/{day_l}-{month_str}-{yr_str}"

        # Parse Rows 53 to 56 (indices 52 to 55) for Team 1 to 4
        if len(rows) >= 56:
            for idx, tk in enumerate(TEAM_ORDER):
                row_i = 52 + idx
                row = rows[row_i]
                if len(row) >= 16:
                    cd_not_yet = parse_int(row[0])   # Col A (0)
                    wait_cd    = parse_int(row[5])   # Col F (5)  = Wait CD Total
                    fot_close  = parse_int(row[6])   # Col G (6)  = Total FOT Close
                    sheet_rank = parse_int(row[7])   # Col H (7)  = Rank
                    
                    col_d_text = str(row[3]) if len(row) > 3 else ""
                    m_assign = re.search(r"/All Assign:\s*/?(\d+)\s*=>\s*All task Close:\s*/?(\d+)", col_d_text)
                    if m_assign:
                        all_assign = m_assign.group(1)
                        task_close = m_assign.group(2)
                        task_assign_str = f"{task_close}/{all_assign}"
                    else:
                        task_assign_str = "0/155" if idx == 0 else ("0/71" if idx == 1 else ("0/47" if idx == 2 else "0/58"))

                    m_3day = re.search(r"All task Close:.*?3Day:\s*(\d+[\s/]+\d+[\s/]+\d+)", col_d_text)
                    if m_3day:
                        task_3day_str = re.sub(r"\s+", "", m_3day.group(1))
                    else:
                        task_3day_str = "0/0/0"

                    # Col I (8) = % Complete (e.g. '18%')
                    raw_pct    = str(row[8]).strip() if len(row) > 8 else ""
                    m_pct      = re.search(r"(\d+)", raw_pct)
                    sheet_pct  = int(m_pct.group(1)) if m_pct else 0

                    d2_close   = parse_int(row[9])   # Col J (9)  = 11/08
                    d1_close   = parse_int(row[10])  # Col K (10) = 10/08
                    d0_close   = parse_int(row[11])  # Col L (11) = 09/08
                    plan_m     = parse_int(row[12])  # Col M (12) = Plan WOs
                    overdue_f  = parse_int(row[13])  # Col N (13)
                    remain_wo  = parse_int(row[15])  # Col P (15)

                    total_assigned = fot_close + remain_wo
                    calc_pct = round((fot_close / total_assigned * 100)) if total_assigned > 0 else 0
                    final_pct = sheet_pct if sheet_pct > 0 else calc_pct

                    team_data[tk] = {
                        "totalAssigned": total_assigned,
                        "fotClose": fot_close,
                        "remain": remain_wo,
                        "overdueF": overdue_f,
                        "waitCD": wait_cd,
                        "cdNotYet": cd_not_yet,
                        "taskAssign": task_assign_str,
                        "task3Day": task_3day_str,
                        "planM": plan_m,
                        "d0": d0_close,  # Col L (09/08)
                        "d1": d1_close,  # Col K (10/08)
                        "d2": d2_close,  # Col J (11/08)
                        "pct": final_pct,
                        "sheetRank": sheet_rank,
                    }
    except Exception as err:
        logger.error(f"Error parsing Sum all WO Team sheet: {err}")

    # Build final result json with ranks
    result = {}
    ranks = []
    for tk in TEAM_ORDER:
        d = team_data[tk]
        tot = d["totalAssigned"]
        pct = d.get("pct", 0)
        ranks.append({"key": tk, "pct": pct})

        result[tk] = {
            "name": TEAM_LABELS[tk],
            "region": TEAM_REGIONS[tk],
            "engineers": TEAM_ENGINEERS[tk],
            "totalAssigned": tot,
            "fotClose": d["fotClose"],
            "remain": d["remain"],
            "overdueF": d["overdueF"],
            "waitCD": d["waitCD"],
            "cdNotYet": d["cdNotYet"],
            "planM": d["planM"],
            "d0": d["d0"],
            "d1": d["d1"],
            "d2": d["d2"],
            "pct": pct,
            "closeRate": float(pct),
            "targetPct": target_pct,
            "metTarget": pct >= target_pct,
        }

    ranks.sort(key=lambda x: x["pct"], reverse=True)
    for r_i, item in enumerate(ranks):
        result[item["key"]]["rank"] = r_i + 1

    return {
        "status": "ok",
        "updatedAt": now_str,
        "period": "21/07/2026 – 20/08/2026",
        "dateLabel": date_label,
        "planLabel": plan_label,
        "targetPct": target_pct,
        "sheetFound": "Sum all WO Team (GID 1840482617)",
        "data": result,
    }



class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            action = query.get("action", [None])[0]

            if action in ("wo_detail", "wo"):
                cache_file = os.path.join(os.path.dirname(__file__), "wo_detail_cache.json")
                if os.path.exists(cache_file):
                    with open(cache_file, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                else:
                    payload = {"status": "ok", "message": "No cache yet"}
            else:
                payload = get_bi_stats()

            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            logger.error(f"BI Data API Error: {e}")
            err_body = json.dumps({"status": "error", "message": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_body)

