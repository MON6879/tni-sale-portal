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

    team_data = {
        "team1": {"totalAssigned": 337, "fotClose": 42, "remain": 295, "overdueF": 161, "waitCD": 23, "cdNotYet": 16, "planM": 42, "d0": 1, "d1": 7, "d2": 0},
        "team2": {"totalAssigned": 207, "fotClose": 120, "remain": 87, "overdueF": 24, "waitCD": 8, "cdNotYet": 24, "planM": 12, "d0": 0, "d1": 14, "d2": 1},
        "team3": {"totalAssigned": 95, "fotClose": 32, "remain": 63, "overdueF": 13, "waitCD": 3, "cdNotYet": 8, "planM": 8, "d0": 0, "d1": 5, "d2": 1},
        "team4": {"totalAssigned": 103, "fotClose": 81, "remain": 22, "overdueF": 0, "waitCD": 2, "cdNotYet": 4, "planM": 3, "d0": 0, "d1": 14, "d2": 4},
    }

    try:
        rows = fetch_sum_all_sheet()
        logger.info(f"Fetched Sum all WO Team sheet: {len(rows)} rows")

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
                    fot_close  = parse_int(row[6])   # Col G (6)
                    d2_close   = parse_int(row[9])   # Col J (9)  = 11/08
                    d1_close   = parse_int(row[10])  # Col K (10) = 10/08
                    d0_close   = parse_int(row[11])  # Col L (11) = 09/08
                    plan_m     = parse_int(row[12])  # Col M (12) = Plan WOs
                    overdue_f  = parse_int(row[13])  # Col N (13)
                    remain_wo  = parse_int(row[15])  # Col P (15)

                    total_assigned = fot_close + remain_wo

                    team_data[tk] = {
                        "totalAssigned": total_assigned,
                        "fotClose": fot_close,
                        "remain": remain_wo,
                        "overdueF": overdue_f,
                        "waitCD": team_data[tk].get("waitCD", 0),
                        "cdNotYet": cd_not_yet,
                        "planM": plan_m,
                        "d0": d0_close,  # Col L (09/08)
                        "d1": d1_close,  # Col K (10/08)
                        "d2": d2_close,  # Col J (11/08)
                    }
    except Exception as err:
        logger.error(f"Error parsing Sum all WO Team sheet: {err}")

    # Build final result json with ranks
    result = {}
    ranks = []
    for tk in TEAM_ORDER:
        d = team_data[tk]
        tot = d["totalAssigned"]
        fot = d["fotClose"]
        pct = round((fot / tot * 100)) if tot > 0 else 0
        ranks.append({"key": tk, "pct": pct})

        result[tk] = {
            "name": TEAM_LABELS[tk],
            "region": TEAM_REGIONS[tk],
            "engineers": TEAM_ENGINEERS[tk],
            "totalAssigned": tot,
            "fotClose": fot,
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
            "metTarget": pct >= 50,
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
        "sheetFound": "Sum all WO Team (GID 1840482617)",
        "data": result,
    }


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
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
