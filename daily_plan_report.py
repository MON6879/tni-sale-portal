"""
daily_plan_report.py
====================
Collects "Daily Plan" messages from Team groups, stores in Google Sheet,
and sends summary reports to each team group + CONTROL.

3 modes via --mode argument:
  eod     (17:00) — EOD Plan vs Actual results + Plan Tomorrow status
  update  (21:00) — Updated Plan Tomorrow status (refresh)
  morning (07:00) — Forward TL's plan content + 3D/7D/1M stats + 3-day completion rate

Sheet: 1C8hU8SXpOdq-v6z7iLGoqwDJmO9DYudZ3rhflb7LC8Y
Tab:   "Team leader assign Plan" (GID: 853981745)
  A = REF (auto DP-001)
  B = Date
  C = Team
  D = Daily Plan content (from Telegram)
  E = Daily Report results (from "Daily report and Bussiness" B:S)
  F = Comparison (Plan vs Actual)

Trigger: GitHub Actions daily_reports.yml (plan_eod / plan_update / plan_morning)
Uses: Telethon (read messages) + SEND_BOT (send reports) + Apps Script (sheet I/O)
"""

import argparse
import asyncio
import io
import os
import re
import logging
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetHistoryRequest
from telegram import Bot
from dotenv import load_dotenv
load_dotenv()
from delete_old_helper import delete_old_messages_bot, save_msgids

# ── Logging ─────────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────
API_ID         = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH       = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_STRING = os.environ.get("TELEGRAM_SESSION", "")
SEND_BOT_TOKEN = os.environ.get("SEND_BOT_TOKEN", "")
# Dùng APPS_SCRIPT_URL chung — doPost route "daily_*" → doPostDaily_
MAIN_GAS_FALLBACK = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "").strip()
if not APPS_SCRIPT_URL or "AKfycbzGFdnE" in APPS_SCRIPT_URL:
    APPS_SCRIPT_URL = MAIN_GAS_FALLBACK

MYANMAR_TZ = timezone(timedelta(hours=6, minutes=30))

# ── Spreadsheet for Daily Report (cùng sheet với daily_report_collector.gs) ──
DAILY_SHEET_ID = "1C8hU8SXpOdq-v6z7iLGoqwDJmO9DYudZ3rhflb7LC8Y"
DAILY_REPORT_CSV = (
    f"https://docs.google.com/spreadsheets/d/{DAILY_SHEET_ID}"
    "/gviz/tq?tqx=out:csv&sheet=Daily+report+and+Bussiness"
)

# ── Telegram Groups ────────────────────────────────────────────
from tni_config import TELEGRAM_GROUPS, GROUP_NAMES
GROUPS = {k: v for k, v in TELEGRAM_GROUPS.items() if k != "CONTROL"}
CONTROL_CHAT_ID = TELEGRAM_GROUPS["CONTROL"]

# Team number → group key  (dùng để map nhân viên)
# Lấy team từ sheet "Task remain" col A hoặc "ID Telegram" tab
TEAM_SHEET_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8"
TEAM_SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{TEAM_SHEET_ID}"
    "/export?format=csv&gid=133591305"
)

# ── Helpers ─────────────────────────────────────────────────────

def myanmar_now() -> datetime:
    return datetime.now(MYANMAR_TZ)


def normalize_date_str(s: str) -> str:
    """Normalize any date string to DD/MM/YYYY."""
    if not s:
        return ""
    s = str(s).strip().replace(".", "/")
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', s)
    if m:
        d, mon, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if len(y) == 2:
            y = "20" + y
        return f"{d:02d}/{mon:02d}/{y}"
    return s


def is_daily_plan_msg(text: str) -> bool:
    """
    Nhận dạng tin plan linh hoạt từ Team Leader / User:
    - Có chứa 'Daily Plan:' hoặc 'Plan for' hoặc chữ 'plan' đi cùng ngày tháng (DD/MM/YYYY hoặc D/M/YYYY)
    - CHỈ loại bỏ các bản tin Báo cáo tự động do Bot phát ra (Auto Report, Daily Result, Plan vs Actual, EOD Summary...)
    """
    if not text:
        return False
    text_l = text.lower()

    # 🛑 LOẠI BỎ CÁC BẢN TIN BÁO CÁO TỰ ĐỘNG (Report 1-4, Refuel Plan, BOD, Auto Report...)
    if any(kw in text_l for kw in (
        "5.1 report", "5. report", "4. report", "4 report", "report 4", "refuel plan",
        "report 1", "report 2", "report 3", "refuel plan 4", "submission history",
        "3-day completion rate", "comparison of plan for", "auto report", "plan stats:",
        "report — daily plan", "crosscheck", "plan tomorrow status", "plan vs actual",
        "eod summary", "shows detailed site assignments", "tasks grouped by department",
        "recent plans", "plans for ", "plan updated", "plan saved", "ref:", "ref:dp-",
        "đã lưu", "tni personal find task", "ft result daily", "personal find task",
        "find task + wo", "team leader: submitted", "plan content:", "overall: no data",
        "submitted ✓", "submitted v", "not yet submitted", "daily plan & results",
        "tni auto report", "tni team"
    )):
        return False

    # Bắt buộc chứa từ khóa Plan chuẩn của Team Leader và ngày tháng
    has_plan_keyword = any(kw in text_l for kw in (
        "daily plan", "plan for", "plan:", "hot task", "kế hoạch", "plan "
    ))
    has_date = bool(re.search(r'\b\d{1,2}[\/\.]\d{1,2}[\/\.]\d{2,4}\b', text))
    return has_plan_keyword and has_date


def clean_plan_content(content: str) -> str:
    """Dọn dẹp nội dung plan, loại bỏ toàn bộ tiêu đề/chân tin nhắn tự động của bot nếu lỡ bị dính."""
    if not content:
        return ""
    clean_lines = []
    for line in content.splitlines():
        line_l = line.lower().strip()
        if any(kw in line_l for kw in (
            "submission history", "3-day completion rate", "plan saved — ref:",
            "5.1 report", "5. report", "team leader: submitted", "plan content:",
            "overall: no data", "overall:", "submitted ✓", "submitted v", "submitted✓",
            "not yet submitted", "tni auto report", "📝 plan for", "📝 plan",
            "plan for", "3-day", "7day:", "month:"
        )):
            continue
        # Skip date/time stamp lines like "📅 05/08/2026 | 🕐 11:28" or "🗓️ ... | 🕐 ..."
        if re.search(r'(?:📅|🗓).*(?:🕐|\|.*\d{2}:\d{2})', line):
            continue
        # Skip separator lines like "━━━━━━━"
        if re.match(r'^[━─═\-]{3,}$', line_l):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()


def parse_daily_plan(text: str) -> dict | None:
    """
    Parse một tin plan (liệt linh hoạt) thành {date, team, content}.
    """
    if not text:
        return None

    # First clean away any nested bot report headers/footers
    cleaned_text = clean_plan_content(text)
    text_to_parse = cleaned_text if cleaned_text else text

    lines = text_to_parse.strip().split("\n")
    if not lines:
        return None

    # Extract date: Ưu tiên tìm theo 'Daily Plan:' hoặc 'Plan for', sau đó mới tìm bất kỳ ngày nào
    date_str = ""
    date_match = re.search(r'(?:daily\s*plan|plan\s*for)[:\s]+(\d{1,2}[\/\.]\d{1,2}[\/\.]\d{2,4})', text_to_parse, re.IGNORECASE)
    if not date_match:
        date_match = re.search(r'(\d{1,2}[\/\.]\d{1,2}[\/\.]\d{2,4})', text_to_parse)
    if date_match:
        date_str = normalize_date_str(date_match.group(1))
    else:
        date_str = myanmar_now().strftime("%d/%m/%Y")

    # Extract team: tìm Team + số trong dòng đầu hoặc toàn bộ text
    team_str = ""
    team_line_idx = 0

    # Ưu tiên tìm trong dòng đầu (dạng 'Team04', 'Team 4', 'T4')
    team_match_first = re.search(
        r'\b(Team\s*0?([1-5]))', lines[0], re.IGNORECASE
    )
    if team_match_first:
        team_str = team_match_first.group(1).strip()
        team_line_idx = 0
    else:
        # Tìm trong các dòng tiếp theo
        for i, line in enumerate(lines[1:], start=1):
            team_match = re.match(r'^\s*(Team\s*0?[1-5])\s*$', line.strip(), re.IGNORECASE)
            if team_match:
                team_str = team_match.group(1).strip()
                team_line_idx = i
                break
        if not team_str:
            team_match2 = re.search(r'(Team\s*0?[1-5])', text_to_parse, re.IGNORECASE)
            if team_match2:
                team_str = team_match2.group(1).strip()

    # Content: lấy mọi thứ sau dòng header
    start_idx = max(1, team_line_idx + 1 if team_line_idx > 0 else 1)
    content_lines = []
    for i in range(start_idx, len(lines)):
        line = lines[i].strip()
        if not content_lines and not line:
            continue
        content_lines.append(lines[i])

    content = "\n".join(content_lines).strip()
    content = clean_plan_content(content)

    if not date_str and not team_str:
        return None

    return {
        "date": date_str,
        "team": team_str or "Unknown",
        "content": content or text_to_parse,
    }


def normalize_team(team_str: str) -> str:
    """Normalize team string to group key (T1, T2, T3, T4)."""
    t = team_str.upper().replace(" ", "")
    if "1" in t: return "T1"
    if "2" in t: return "T2"
    if "5" in t: return "T2"  # Team 5 merged into Team 2
    if "3" in t: return "T3"
    if "4" in t: return "T4"
    return ""


def extract_tni_codes(text: str) -> set:
    """Extract all TNIxxxx site codes from text and convert to uppercase."""
    if not text:
        return set()
    return set(code.upper() for code in re.findall(r'TNI\d{3,5}(?:_\d+)?', text, re.IGNORECASE))


def is_employee_in_cell(emp: dict, cell_value: str) -> bool:
    """Fuzzy match employee name or username inside a cell value."""
    if not cell_value:
        return False
    cell_lower = cell_value.lower()
    
    # 1. Check Name
    name = emp.get("name", "").strip()
    if name and name != "-":
        name_clean = re.sub(r'[\s._]', '', name).lower()
        cell_clean = re.sub(r'[\s._]', '', cell_lower)
        if name_clean in cell_clean:
            return True
            
    # 2. Check Username (sys_name)
    sys_name = emp.get("sys_name", "").strip()
    if sys_name and sys_name != "-":
        sys_clean = sys_name.lower()
        if sys_clean.startswith("myt_"):
            sys_clean = sys_clean[4:]
        sys_clean = re.sub(r'[\s._]', '', sys_clean)
        cell_clean = re.sub(r'[\s._]', '', cell_lower)
        if sys_clean in cell_clean:
            return True
            
    return False



# Mỗi category một màu vuông cố định — trùng tên category = trùng màu
CATEGORY_SQUARES = {
    "admin":        "🟦",   # xanh dương
    "asset":        "🟧",   # cam
    "m&e":          "🟩",   # xanh lá
    "pm":           "🟨",   # vàng
    "cm":           "🟥",   # đỏ
    "construction": "🟣",   # tím
    "noc":          "⬛",   # đen
    "technical":    "🟦",   # xanh dương
    "site":         "🟩",   # xanh lá
}


def colorize_bullets(text: str) -> str:
    """Thay dau bullet bang vuong mau theo category."""
    if not text:
        return text

    def replace_bullet(m):
        cat_raw = m.group(1).strip()
        cat_lo  = cat_raw.lower()
        for key, sq in CATEGORY_SQUARES.items():
            if key in cat_lo:
                return f"{sq} [{cat_raw}]"
        return f"▪️ [{cat_raw}]"  # fallback vuông nhỏ

    return re.sub(r'•\s*\[([^\]]+)\]', replace_bullet, text)


# ── Apps Script calls ───────────────────────────────────────────

def call_apps_script(payload: dict, timeout: int = 30) -> dict:
    """Call Apps Script and return JSON response."""
    if not APPS_SCRIPT_URL:
        logger.warning("APPS_SCRIPT_URL not set")
        return {}
    try:
        resp = requests.post(APPS_SCRIPT_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Apps Script error: {e}")
        return {}


def store_daily_plan(date, team, content, daily_report="", comparison="") -> dict:
    """Store a daily plan entry in Google Sheet via Apps Script."""
    return call_apps_script({
        "action": "store_daily_plan",
        "date": date,
        "team": team,
        "content": content,
        "daily_report": daily_report,
        "comparison": comparison,
    }, timeout=30)


def get_daily_plans() -> list:
    """Get all daily plan entries from Google Sheet."""
    data = call_apps_script({"action": "get_daily_plans"}, timeout=60)
    if data.get("status") != "ok":
        logger.warning(f"get_daily_plans failed: {data.get('message', 'unknown')}")
        return []
    return data.get("plans", [])


def get_report_data() -> dict:
    """Get employee/leader stats từ Apps Script (rank, close%, WO remain, task close)."""
    data = call_apps_script({"action": "get_report_data"}, timeout=120)
    if data.get("status") != "ok":
        logger.warning(f"get_report_data failed: {data.get('message', 'unknown')}")
        return {}
    return data


def get_team_leaders() -> dict:
    """Reads GID 133591305 and returns dict mapping team key to leader IDs."""
    fallback = {
        "T1": "6859790680",
        "T2": "6555381983",
        "T3": "6710667362",
        "T4": "6867087612"
    }
    leaders = {}
    for k, v in fallback.items():
        leaders[k] = [v]
        
    try:
        resp = requests.get(TEAM_SHEET_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str, on_bad_lines="skip")
        
        for idx in range(3, min(len(df), 59)):
            row = df.iloc[idx]
            team = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ""
            username = str(row.iloc[2]).strip() if not pd.isna(row.iloc[2]) else ""
            tg_id = str(row.iloc[4]).strip() if len(row) > 4 and not pd.isna(row.iloc[4]) else ""
            if tg_id.endswith(".0"): tg_id = tg_id[:-2]
            
            if "leader" in username.lower():
                tk = team.upper()
                if "TEAM01" in tk or "TEAM1" in tk: tk = "T1"
                elif "TEAM02" in tk or "TEAM2" in tk or "TEAM05" in tk or "TEAM5" in tk: tk = "T2"
                elif "TEAM03" in tk or "TEAM3" in tk: tk = "T3"
                elif "TEAM04" in tk or "TEAM4" in tk: tk = "T4"
                else: tk = ""
                
                if tk and tg_id and tg_id != "-" and tg_id.lower() != "nan":
                    if tg_id not in leaders[tk]:
                        leaders[tk].append(tg_id)
    except Exception as e:
        logger.error(f"Error loading team leaders from sheet: {e}")
        
    return leaders


def get_unified_employees() -> list:
    """
    Loads employees from TEAM_SHEET_URL and merges with stats from get_report_data().
    """
    employees = []
    try:
        resp = requests.get(TEAM_SHEET_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str, on_bad_lines="skip")
        
        for idx in range(3, min(len(df), 59)):
            row = df.iloc[idx]
            team = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ""
            name = str(row.iloc[1]).strip() if not pd.isna(row.iloc[1]) else ""
            username = str(row.iloc[2]).strip() if not pd.isna(row.iloc[2]) else ""
            tg_id = str(row.iloc[4]).strip() if len(row) > 4 and not pd.isna(row.iloc[4]) else ""
            if tg_id.endswith(".0"): tg_id = tg_id[:-2]
            
            if not name and not username: continue
            
            tk = team.upper()
            if "TEAM01" in tk or "TEAM1" in tk: tk = "T1"
            elif "TEAM02" in tk or "TEAM2" in tk or "TEAM05" in tk or "TEAM5" in tk: tk = "T2"
            elif "TEAM03" in tk or "TEAM3" in tk: tk = "T3"
            elif "TEAM04" in tk or "TEAM4" in tk: tk = "T4"
            else: tk = ""
            
            employees.append({
                "team": tk,
                "name": name,
                "sys_name": username,
                "telegram_id": tg_id,
                "rank": 17,
                "close_pct": 0,
                "wo_remain": 0,
                "assign_remain": 0,
                "wo_d0": 0, "wo_d1": 0, "wo_d2": 0,
                "assign_month_close": 0
            })
    except Exception as e:
        logger.error(f"Error loading unified employees from sheet: {e}")
        
    try:
        report_data = get_report_data()
        stats_map = {str(emp.get("chat_id", "")).replace(".0", ""): emp for emp in report_data.get("employees", [])}
        
        for emp in employees:
            tid = emp["telegram_id"]
            if tid in stats_map:
                s = stats_map[tid]
                emp["rank"] = s.get("rank", emp["rank"])
                emp["close_pct"] = s.get("close_pct", emp["close_pct"])
                emp["wo_remain"] = s.get("wo_remain", emp["wo_remain"])
                emp["assign_remain"] = s.get("assign_remain", emp["assign_remain"])
                emp["wo_d0"] = s.get("wo_d0", emp["wo_d0"])
                emp["wo_d1"] = s.get("wo_d1", emp["wo_d1"])
                emp["wo_d2"] = s.get("wo_d2", emp["wo_d2"])
                emp["assign_month_close"] = s.get("assign_month_close", emp["assign_month_close"])
    except Exception as e:
        logger.error(f"Error merging employee stats: {e}")
        
    return employees





def build_emp_compact_line(emp: dict, daily_counts: dict | None = None) -> str:
    """Format single line stats for employee."""
    name      = emp.get("name", "?")
    sys_name  = emp.get("sys_name", "")
    tg_id     = str(emp.get("telegram_id", emp.get("tg_id", ""))).replace(".0", "")
    rank      = emp.get("rank", 0)
    close_pct = emp.get("close_pct", 0)
    wo_d0     = emp.get("wo_d0", 0)
    wo_d1     = emp.get("wo_d1", 0)
    wo_d2     = emp.get("wo_d2", 0)
    wo_remain = emp.get("wo_remain", 0)
    assign_mo = emp.get("assign_month_close", 0)

    # Tên hiển thị: Name-sys_name
    display_name = f"{name}-{sys_name}" if sys_name else name

    # Màu theo 3day WO
    color = "🟢" if (wo_d0 > 0 or wo_d1 > 0 or wo_d2 > 0) else "🔴"

    # Daily result counts (số lần nộp daily report)
    dr_part = ""
    if daily_counts and tg_id and tg_id in daily_counts:
        dc = daily_counts[tg_id]
        dr_part = (
            f" | Daily:{dc['d2']}/{dc['d1']}/{dc['d0']} "
            f"7D:{dc['d7']} M:{dc['month']}"
        )

    return (
        f"{color} {display_name}: rank:{rank} | Close:{close_pct}% "
        f"<{wo_d2}/{wo_d1}/{wo_d0}> | WO remain:{wo_remain} "
    )


def parse_assigned_tni_per_person(plan_text: str, team_emps: list) -> dict:
    """Parses plan text and maps employee tg_id to assigned TNI codes."""
    assigned = {}
    emp_patterns = []
    for emp in team_emps:
        names_to_try = []
        username = str(emp.get("sys_name", emp.get("username", ""))).lower()
        if username.startswith("myt_"):
            username = username[4:]
        username = re.sub(r'\d+', '', username)
        if username:
            names_to_try.append(username.replace(".", " "))
            names_to_try.append(username.replace(".", ""))
        disp_name = str(emp.get("name", "")).lower()
        if disp_name:
            names_to_try.append(disp_name)
        names_to_try = list(set(n.strip() for n in names_to_try if n.strip()))
        if names_to_try:
            names_to_try.sort(key=len, reverse=True)
            pattern_str = r'\b(?:' + '|'.join(re.escape(n) for n in names_to_try) + r')\b'
            emp_patterns.append((emp, re.compile(pattern_str, re.IGNORECASE)))
            
    for line in plan_text.splitlines():
        line = line.strip()
        if not line: continue
        matches = []
        for emp, pattern in emp_patterns:
            for match in pattern.finditer(line):
                matches.append((match.start(), match.end(), emp))
        if not matches: continue
        matches.sort(key=lambda x: (x[0], x[1]))
        for i in range(len(matches)):
            start_pos = matches[i][0]
            end_pos = matches[i+1][0] if i + 1 < len(matches) else len(line)
            segment = line[start_pos:end_pos]
            tni_codes = extract_tni_codes(segment)
            if tni_codes:
                tg_id = str(matches[i][2].get("telegram_id", matches[i][2].get("tg_id", ""))).replace(".0", "")
                assigned.setdefault(tg_id, set()).update(tni_codes)
    return assigned


def get_employee_completed_tni_today_detailed(df_report, target_date: str, employees: list) -> dict:
    """Extracts all completed TNI codes today per employee."""
    completed = {}
    if df_report is None or df_report.empty:
        return completed
        
    name_idx = 1
    fullname_idx = 1
    date_idx = 2
    tg_idx = 17
    for col_idx, col_name in enumerate(df_report.columns):
        c_lower = col_name.lower().strip()
        if "tên nhân viên" in c_lower and not ".1" in c_lower:
            name_idx = col_idx
        elif "full name" in c_lower:
            fullname_idx = col_idx
        elif "daily report" in c_lower and not ":" in c_lower:
            date_idx = col_idx
        elif "telegram id" in c_lower:
            tg_idx = col_idx
            
    for idx, row in df_report.iterrows():
        date_cell = str(row.iloc[date_idx]).strip() if not pd.isna(row.iloc[date_idx]) else ""
        tg_id = str(row.iloc[tg_idx]).strip() if len(row) > tg_idx and not pd.isna(row.iloc[tg_idx]) else ""
        emp_name = str(row.iloc[name_idx]).strip() if not pd.isna(row.iloc[name_idx]) else ""
        fullname_val = str(row.iloc[fullname_idx]).strip() if len(row) > fullname_idx and not pd.isna(row.iloc[fullname_idx]) else ""
        search_name = f"{emp_name} {fullname_val}".strip()
        
        if emp_name.lower() in ("nan", "none", ""): emp_name = ""
        if not emp_name:
            continue

        if not date_cell or date_cell.lower() in ("nan", "none", ""):
            continue

        norm_target = normalize_date_str(target_date)
        norm_cell   = normalize_date_str(date_cell)
        if not norm_cell or norm_cell != norm_target:
            continue
            
        matched_tg_ids = set()
        if tg_id and tg_id.lower() not in ("nan", "none", ""):
            cid = tg_id.replace(".0", "") if tg_id.endswith(".0") else tg_id
            matched_tg_ids.add(cid)
            
        for emp in employees:
            emp_tg_id = str(emp.get("telegram_id", "")).strip()
            if emp_tg_id and is_employee_in_cell(emp, search_name):
                matched_tg_ids.add(emp_tg_id)
                
        # Extract TNI codes
        row_tni_details = {}
        for col_i in range(date_idx + 1, tg_idx):
            if col_i >= len(row):
                continue
            val = row.iloc[col_i]
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            # Bỏ qua các lệnh bot: CLEAR TNI..., T1waitcd, v.v.
            if re.match(r'^clear\b', val_str, re.IGNORECASE):
                continue
            codes = extract_tni_codes(val_str)
            if codes:
                # Dùng tiêu đề TNIxxxx từ nội dung cell thay vì tên cột sheet
                # Ví dụ: "TNI0295 maintenance:" → header = "TNI0295 maintenance"
                # Chỉ áp dụng khi cell có dạng TNIxxxx + text mô tả (không phải danh sách nhiều TNI)
                tni_heading_match = re.match(r'(TNI\d{3,5}\s+[^\n]+)', val_str, re.IGNORECASE)
                if tni_heading_match and len(codes) == 1:
                    # Cell có 1 TNI code với mô tả, dùng toàn bộ phần đầu làm tiêu đề
                    raw_heading = tni_heading_match.group(1).strip().rstrip(':').strip()
                    col_header = raw_heading
                elif len(codes) == 1:
                    # Cell chỉ có 1 TNI code đơn thuần, dùng chính code đó làm tiêu đề
                    col_header = list(codes)[0].upper()
                else:
                    # Cell có nhiều TNI code (danh sách), dùng tên cột sheet
                    col_header = df_report.columns[col_i]
                for code in codes:
                    row_tni_details[code.upper()] = col_header
                    
        for cid in matched_tg_ids:
            emp_details = completed.setdefault(cid, {})
            for code, col_header in row_tni_details.items():
                emp_details[code] = col_header
                
    return completed


# ── Daily Report data from Sheet ────────────────────────────────

def get_team_member_mapping() -> dict:
    """Read Team All Find sheet to map telegram_id to team group key."""
    mapping = {}
    try:
        resp = requests.get(TEAM_SHEET_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str, on_bad_lines="skip")

        TEAM_PATTERNS = {
            "TEAM01": "T1", "TEAM 1": "T1", "TEAM1": "T1",
            "TEAM02": "T2", "TEAM 2": "T2", "TEAM2": "T2",
            "TEAM05": "T2", "TEAM 5": "T2", "TEAM5": "T2",
            "TEAM03": "T3", "TEAM 3": "T3", "TEAM3": "T3",
            "TEAM04": "T4", "TEAM 4": "T4", "TEAM4": "T4",
        }

        for idx in range(3, min(len(df), 59)):  # rows 4-59
            row = df.iloc[idx]
            col_a = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ""
            col_e = str(row.iloc[4]).strip() if not pd.isna(row.iloc[4]) else ""
            if col_a.lower() in ("nan", "none", ""): continue
            if col_e.lower() in ("nan", "none", ""): continue

            cid = col_e.replace(".0", "") if col_e.endswith(".0") else col_e
            team_str = col_a.upper()
            for pattern, gk in TEAM_PATTERNS.items():
                if pattern in team_str:
                    mapping[cid] = gk
                    break

        logger.info(f"  📋 Team mapping: {len(mapping)} members loaded")
    except Exception as e:
        logger.error(f"Team mapping error: {e}")
    return mapping


def get_daily_reports_from_sheet(target_date: str) -> dict:
    """
    Read "Daily report and Bussiness" tab B:S via CSV export.
    Returns: { "T1": [report_texts], "T2": [...], ... }

    target_date: DD/MM/YYYY format to filter by
    """
    team_reports = {"T1": [], "T2": [], "T3": [], "T4": []}

    try:
        # Get team member → team mapping
        team_map = get_team_member_mapping()

        # Read Daily report sheet
        resp = requests.get(DAILY_REPORT_CSV, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=0, dtype=str, on_bad_lines="skip")

        if df.empty:
            logger.info("  📭 Daily report sheet is empty")
            return team_reports, None

        logger.info(f"  📊 Daily report rows: {len(df)}")

        # Find column indices dynamically
        name_idx = 1
        date_idx = 2
        tg_idx = 17
        for col_idx, col_name in enumerate(df.columns):
            c_lower = col_name.lower().strip()
            if "tên nhân viên" in c_lower and not ".1" in c_lower:
                name_idx = col_idx
            elif "daily report" in c_lower and not ":" in c_lower:
                date_idx = col_idx
            elif "telegram id" in c_lower:
                tg_idx = col_idx

        for idx, row in df.iterrows():
            emp_name = str(row.iloc[name_idx]).strip() if not pd.isna(row.iloc[name_idx]) else ""
            date_cell = str(row.iloc[date_idx]).strip() if not pd.isna(row.iloc[date_idx]) else ""
            tg_id = str(row.iloc[tg_idx]).strip() if len(row) > tg_idx and not pd.isna(row.iloc[tg_idx]) else ""

            if emp_name.lower() in ("nan", "none", ""): emp_name = ""
            if tg_id.lower() in ("nan", "none", ""): tg_id = ""

            # Require employee name and valid date
            if not emp_name:
                continue

            if not date_cell or date_cell.lower() in ("nan", "none", ""):
                continue

            # Filter by date — convert all dot dates (dd.mm.yyyy) to slash format (dd/mm/yyyy)
            norm_target = normalize_date_str(target_date)
            norm_cell   = normalize_date_str(date_cell)
            if not norm_cell or norm_cell != norm_target:
                continue

            # Determine team from telegram ID
            cid = tg_id.replace(".0", "") if tg_id.endswith(".0") else tg_id
            team_key = team_map.get(cid, "")

            if not team_key:
                continue

            # Build report text from all non-empty fields
            parts = [f"👤 {emp_name}:" if emp_name else ""]
            start_col = date_idx + 1
            end_col = tg_idx
            for col_idx in range(start_col, min(end_col, len(row))):
                val = str(row.iloc[col_idx]).strip() if not pd.isna(row.iloc[col_idx]) else ""
                if val and val.lower() not in ("nan", "none"):
                    header_name = df.columns[col_idx] if col_idx < len(df.columns) else f"Col{col_idx}"
                    parts.append(f"  {header_name}: {val}")

            report_text = "\n".join(p for p in parts if p)
            if report_text.strip():
                team_reports[team_key].append(report_text)

    except Exception as e:
        logger.error(f"Daily report read error: {e}")
        return team_reports, None

    return team_reports, df


def get_employee_report_counts(employees: list) -> dict:
    """
    Đếm số lần nhân viên nộp daily result theo Telegram ID và Tên nhân viên/Full Name.
    Cú pháp daily report: dòng đầu = "Daily report: DD/MM/YYYY"

    Returns:
      { tg_id_str: {"d0":n, "d1":n, "d2":n, "d7":n, "month":n} }
    """
    counts: dict[str, dict] = {}
    now = myanmar_now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    d1_start    = today - timedelta(days=1)
    d2_start    = today - timedelta(days=2)
    d7_start    = today - timedelta(days=7)
    month_start = today - timedelta(days=30)

    DATE_FMTS = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d")

    def parse_date_cell(raw: str) -> datetime | None:
        raw = raw.strip()
        # Cố gắng parse nhiều định dạng
        for fmt in DATE_FMTS:
            try:
                return datetime.strptime(raw[:len(fmt)+2], fmt).replace(tzinfo=MYANMAR_TZ)
            except Exception:
                pass
        # Tìm pattern DD/MM/YYYY trong chuỗi
        m = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', raw)
        if m:
            for fmt in ("%d/%m/%Y", "%d/%m/%y"):
                try:
                    return datetime.strptime(m.group(1), fmt).replace(tzinfo=MYANMAR_TZ)
                except Exception:
                    pass
        return None

    try:
        resp = requests.get(DAILY_REPORT_CSV, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=0, dtype=str, on_bad_lines="skip")
        if df.empty:
            return counts

        # Find column indices dynamically
        name_idx = 1
        fullname_idx = 1
        date_idx = 2
        tg_idx = 17
        for col_idx, col_name in enumerate(df.columns):
            c_lower = col_name.lower().strip()
            if "tên nhân viên" in c_lower and not ".1" in c_lower:
                name_idx = col_idx
            elif "full name" in c_lower:
                fullname_idx = col_idx
            elif "daily report" in c_lower and not ":" in c_lower:
                date_idx = col_idx
            elif "telegram id" in c_lower:
                tg_idx = col_idx

        for _, row in df.iterrows():
            date_raw = str(row.iloc[date_idx]).strip() if not pd.isna(row.iloc[date_idx]) else ""
            tg_raw   = str(row.iloc[tg_idx]).strip() if len(row) > tg_idx and not pd.isna(row.iloc[tg_idx]) else ""
            emp_name = str(row.iloc[name_idx]).strip() if not pd.isna(row.iloc[name_idx]) else ""
            fullname_val = str(row.iloc[fullname_idx]).strip() if len(row) > fullname_idx and not pd.isna(row.iloc[fullname_idx]) else ""
            search_name = f"{emp_name} {fullname_val}".strip()

            if date_raw.lower() in ("nan", "none", ""): continue
            dt    = parse_date_cell(date_raw)
            if not dt: continue

            day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            
            matched_tg_ids = set()
            if tg_raw and tg_raw.lower() not in ("nan", "none", ""):
                cid = tg_raw.replace(".0", "") if tg_raw.endswith(".0") else tg_raw
                matched_tg_ids.add(cid)
                
            for emp in employees:
                emp_tg_id = str(emp.get("telegram_id", "")).strip()
                if emp_tg_id and is_employee_in_cell(emp, search_name):
                    matched_tg_ids.add(emp_tg_id)

            for tg_id in matched_tg_ids:
                rec = counts.setdefault(tg_id, {"d0": 0, "d1": 0, "d2": 0, "d7": 0, "month": 0})
                if day >= month_start: rec["month"] += 1
                if day >= d7_start:    rec["d7"]    += 1
                if day >= today:       rec["d0"]    += 1
                elif day >= d1_start:  rec["d1"]    += 1
                elif day >= d2_start:  rec["d2"]    += 1

        logger.info(f"  📊 Daily report counts: {len(counts)} employees tracked")
    except Exception as e:
        logger.error(f"Employee report count error: {e}")

    return counts


def build_comparison(plan_content: str, report_texts: list) -> dict:
    """
    Compare Daily Plan vs Daily Report.
    Extract TNI site codes from both, calculate done/remaining.
    Returns: { plan_count, done_count, remain_count, pct, missing_sites, comparison_text }
    """
    # Extract TNI codes from plan
    plan_codes = extract_tni_codes(plan_content)

    # Extract TNI codes from all reports
    report_all_text = "\n".join(report_texts)
    report_codes = extract_tni_codes(report_all_text)

    plan_count = len(plan_codes)
    if plan_count == 0:
        return {
            "plan_count": 0, "done_count": 0, "remain_count": 0, "pct": 0,
            "missing_sites": [], "comparison_text": "No stations in plan"
        }

    # Sites in plan that also appear in reports = done
    done_codes = plan_codes & report_codes
    missing_codes = plan_codes - report_codes
    done_count = len(done_codes)
    remain_count = len(missing_codes)
    pct = round(done_count / plan_count * 100) if plan_count > 0 else 0

    comp_lines = [
        f"📋 Plan: {plan_count} stations",
        f"✅ Done: {done_count} stations ({pct}%)",
        f"⏳ Remaining: {remain_count} stations",
    ]
    if missing_codes:
        comp_lines.append(f"Missing: {', '.join(sorted(missing_codes))}")

    return {
        "plan_count": plan_count,
        "done_count": done_count,
        "remain_count": remain_count,
        "pct": pct,
        "missing_sites": sorted(missing_codes),
        "comparison_text": "\n".join(comp_lines),
    }


# ── Telegram message scanning ──────────────────────────────────

async def scan_group_for_plans(client, chat_id: int, since_utc: datetime, leader_id: str = None) -> list:
    """Scan a Telegram group for 'Daily Plan' messages since given UTC time."""
    plans = []
    try:
        history = await client(GetHistoryRequest(
            peer=chat_id, limit=200,
            offset_date=None, offset_id=0,
            max_id=0, min_id=0, add_offset=0, hash=0,
        ))
        for msg in history.messages:
            if msg.date < since_utc:
                break
            # Collect any daily plan in group (not restricted to specific leader IDs)
            if msg.message and is_daily_plan_msg(msg.message):
                parsed = parse_daily_plan(msg.message)
                if parsed:
                    dt_mm = msg.date.astimezone(MYANMAR_TZ) if msg.date.tzinfo else \
                        msg.date.replace(tzinfo=timezone.utc).astimezone(MYANMAR_TZ)
                    parsed["msg_date"] = dt_mm
                    parsed["msg_id"] = msg.id
                    plans.append(parsed)
    except Exception as e:
        logger.error(f"Scan group {chat_id} error: {e}")
    return plans


def fmt_sent_at(val) -> str:
    if not val:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y %H:%M")
    return str(val)


# ── Stats building ─────────────────────────────────────────────

def parse_plan_date(date_str: str) -> datetime | None:
    """Parse various date string formats to datetime."""
    if not date_str:
        return None
    # 1. Try DD/MM/YYYY
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=MYANMAR_TZ)
        except ValueError:
            continue
            
    # 2. Try parsing long string: e.g. "Fri Jun 26 2026 00:00:00 GMT+0630"
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    parts = date_str.split()
    if len(parts) >= 4:
        mon = parts[1].lower()[:3]
        if mon in months:
            try:
                day = int(parts[2])
                month = months[mon]
                year = int(parts[3])
                dt = datetime(year, month, day)
                return dt.replace(tzinfo=MYANMAR_TZ)
            except ValueError:
                pass
                
    # 3. Try searching for DD/MM/YYYY inside the string
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', date_str)
    if m:
        try:
            d, m_part, y = m.groups()
            if len(y) == 2: y = "20" + y
            dt = datetime(int(y), int(m_part), int(d))
            return dt.replace(tzinfo=MYANMAR_TZ)
        except ValueError:
            pass
            
    return None


def deduplicate_plans_by_date(plans: list) -> list:
    """
    Tự động khử trùng các bản tin Plan có cùng ngày kế hoạch (plan_date) và cùng team.
    Chỉ giữ lại duy nhất bản tin gửi mới nhất (latest row / latest timestamp),
    nhằm tránh việc Team Leader gửi cập nhật kế hoạch bị nhân đôi tin nhắn hoặc sai số liệu thống kê.
    """
    if not plans:
        return []
    
    latest_map = {}
    for p in plans:
        team = normalize_team(p.get("team", ""))
        dt = parse_plan_date(p.get("date", ""))
        if not dt:
            continue
        date_str = dt.strftime("%Y-%m-%d")
        key = (team, date_str)
        # Telegram messages come in DESCENDING order (newest first).
        # Keep the FIRST occurrence (= newest) and skip later (= older) duplicates.
        if key not in latest_map:
            latest_map[key] = p
        
    return list(latest_map.values())


def build_plan_stats(plans: list, team_filter: str = None) -> dict:
    """Build plan stats from plan list (automatically deduplicated by date)."""
    now = myanmar_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    d1_start = today_start - timedelta(days=1)
    d2_start = today_start - timedelta(days=2)
    d7_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)

    stats = {"d0": 0, "d1": 0, "d2": 0, "d7": 0, "month": 0, "today_plans": []}

    deduped_plans = deduplicate_plans_by_date(plans)

    for p in deduped_plans:
        if team_filter:
            plan_team = normalize_team(p.get("team", ""))
            if plan_team != team_filter:
                continue

        dt = parse_plan_date(p.get("date", ""))
        if not dt:
            continue

        plan_date = dt.replace(hour=0, minute=0, second=0, microsecond=0)

        if plan_date >= month_start:
            stats["month"] += 1
        if plan_date >= d7_start:
            stats["d7"] += 1
        if plan_date >= d2_start and plan_date < d1_start:
            stats["d2"] += 1
        elif plan_date >= d1_start and plan_date < today_start:
            stats["d1"] += 1
        elif plan_date >= today_start:
            stats["d0"] += 1
            stats["today_plans"].append(p)

    return stats


# ── Plan Tomorrow helpers ──────────────────────────────────────

def find_plans_for_date(plans: list, target_date_str: str, team_filter: str = None) -> list:
    """
    Find all plans whose embedded date matches target_date_str (DD/MM/YYYY).
    Optionally filter by team. Automatically deduplicated to return the latest plan.
    """
    results = []
    deduped_plans = deduplicate_plans_by_date(plans)
    for p in deduped_plans:
        if team_filter:
            plan_team = normalize_team(p.get("team", ""))
            if plan_team != team_filter:
                continue
        dt = parse_plan_date(p.get("date", ""))
        if not dt:
            continue
        plan_date_str = dt.strftime("%d/%m/%Y")
        if plan_date_str == target_date_str:
            results.append(p)
    return results


async def scan_plan_tomorrow(client, group_key: str, chat_id: int,
                              target_date_str: str, leader_id: str,
                              since_utc: datetime) -> dict:
    """
    Scan a Telegram group for Plan Tomorrow messages from the Team Leader.
    Returns: {
        "found": bool,
        "sent_time": str (HH:MM),
        "content": str,
        "plan": dict or None
    }
    """
    fallback_result = None
    try:
        history = await client(GetHistoryRequest(
            peer=chat_id, limit=200,
            offset_date=None, offset_id=0,
            max_id=0, min_id=0, add_offset=0, hash=0,
        ))
        for msg in history.messages:
            if msg.date < since_utc:
                break
            if msg.message and is_daily_plan_msg(msg.message):
                parsed = parse_daily_plan(msg.message)
                if parsed:
                    dt_mm = msg.date.astimezone(MYANMAR_TZ) if msg.date.tzinfo else \
                        msg.date.replace(tzinfo=timezone.utc).astimezone(MYANMAR_TZ)
                    candidate = {
                        "found": True,
                        "sent_time": dt_mm.strftime("%d/%m/%Y %H:%M"),
                        "content": clean_plan_content(parsed.get("content", msg.message)),
                        "plan": parsed,
                    }
                    dt = parse_plan_date(parsed.get("date", ""))
                    if dt and dt.strftime("%d/%m/%Y") == target_date_str:
                        return candidate  # Match chính xác ngày mục tiêu
                    # Fallback: Nếu tin nhắn được gửi sau 14:00 MMT và chưa có candidate fallback thì lưu lại
                    if fallback_result is None and dt_mm.hour >= 14:
                        fallback_result = candidate
    except Exception as e:
        logger.error(f"scan_plan_tomorrow {group_key} error: {e}")
    return fallback_result if fallback_result else result


def calc_3day_completion_rate(all_plans: list, team_comparisons: dict,
                               team_reports_all: dict = None) -> dict:
    """
    Tính tỉ lệ hoàn thành kế hoạch 3 ngày gần nhất (không tính hôm nay nếu chưa hết ngày).
    Returns per-team + overall:
    {
      "T1": {"days": [{date, plan_count, done_count, pct}, ...], "total_plan", "total_done", "pct"},
      ...
      "overall": {"total_plan", "total_done", "pct"}
    }
    """
    now = myanmar_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    result = {}
    grand_plan = 0
    grand_done = 0

    for gk in ("T1", "T2", "T3", "T4"):
        team_days = []
        team_plan_total = 0
        team_done_total = 0

        for days_ago in range(3, 0, -1):  # d3, d2, d1 (3 ngày trước hôm nay)
            target_dt = today_start - timedelta(days=days_ago)
            target_str = target_dt.strftime("%d/%m/%Y")

            # Tìm plans cho ngày đó
            day_plans = find_plans_for_date(all_plans, target_str, team_filter=gk)
            if not day_plans:
                team_days.append({"date": target_str, "plan_count": 0, "done_count": 0, "pct": 0, "sent_at": ""})
                continue

            sent_at_str = ""
            for p in day_plans:
                m_at = p.get("msg_date") or p.get("sent_time") or p.get("sent_at")
                if m_at:
                    sent_at_str = fmt_sent_at(m_at)
                    if sent_at_str:
                        break

            # Đếm TNI codes trong plan
            plan_tni = set()
            for p in day_plans:
                plan_tni |= extract_tni_codes(p.get("content", p.get("d", "")))

            plan_count = len(plan_tni)

            # Comparison data — nếu có trong sheet plans (col F)
            done_count = 0
            for p in day_plans:
                comp_text = p.get("comparison", p.get("f", ""))
                if comp_text:
                    done_match = re.search(r'Done:\s*(\d+)', str(comp_text))
                    if done_match:
                        done_count = max(done_count, int(done_match.group(1)))

            pct = round(done_count / plan_count * 100) if plan_count > 0 else 0
            team_days.append({
                "date": target_str,
                "plan_count": plan_count,
                "done_count": done_count,
                "pct": pct,
                "sent_at": sent_at_str
            })
            team_plan_total += plan_count
            team_done_total += done_count

        team_pct = round(team_done_total / team_plan_total * 100) if team_plan_total > 0 else 0
        result[gk] = {
            "days": team_days,
            "total_plan": team_plan_total,
            "total_done": team_done_total,
            "pct": team_pct,
        }
        grand_plan += team_plan_total
        grand_done += team_done_total

    overall_pct = round(grand_done / grand_plan * 100) if grand_plan > 0 else 0
    result["overall"] = {"total_plan": grand_plan, "total_done": grand_done, "pct": overall_pct}

    return result


# ── Send message helper ────────────────────────────────────────

async def send_msg(bot, cid, text, label="", reply_markup=None):
    """Send message with auto-split for >4096 chars. Returns (ok, msg_ids)."""
    MAX = 4000
    sent_ids = []  # collect message_id from each sent message

    def chunk_text(t):
        parts, current = [], ""
        for line in t.split("\n"):
            while len(line) > MAX:
                segment = line[:MAX]
                if current:
                    parts.append(current)
                    current = ""
                parts.append(segment)
                line = line[MAX:]
            if len(current) + len(line) + 1 > MAX:
                parts.append(current)
                current = line
            else:
                current += ("\n" if current else "") + line
        if current:
            parts.append(current)
        return parts

    try:
        chunks = chunk_text(text)
        if len(chunks) == 1:
            result = await bot.send_message(chat_id=cid, text=text, reply_markup=reply_markup, disable_web_page_preview=True)
            sent_ids.append(result.message_id)
        else:
            for i, p in enumerate(chunks):
                if p.strip():
                    markup = reply_markup if i == len(chunks) - 1 else None
                    result = await bot.send_message(chat_id=cid, text=p, reply_markup=markup, disable_web_page_preview=True)
                    sent_ids.append(result.message_id)
                    await asyncio.sleep(0.3)
        logger.info(f"✅ {label} → {cid}")
        return True, sent_ids
    except Exception as e:
        logger.error(f"❌ {label} → {cid}: {e}")
        return False, sent_ids


# ── Main ────────────────────────────────────────────────────────

async def run_eod_or_update(mode: str):
    """Run EOD or update report mode."""
    now = myanmar_now()
    now_str = now.strftime("%d/%m/%Y %H:%M")
    date_str = now.strftime("%d/%m/%Y")
    tomorrow = now + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%d/%m/%Y")

    mode_label = "EOD" if mode == "eod" else "Updated"
    delete_prefix = "PLAN_EOD" if mode == "eod" else "PLAN_UPD"

    logger.info(f"🚀 Daily Plan Report ({mode_label}) start – {now_str}")

    # ── Step 1: Scan Telegram groups for Daily Plan messages ──
    since_utc = (now - timedelta(days=2)).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).astimezone(timezone.utc)

    logger.info("📡 Scanning Telegram groups for Daily Plan messages...")

    # Fetch team leaders to filter plan senders
    leaders = get_team_leaders()
    logger.info(f"  📋 Team leaders loaded for filtering: {leaders}")

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    all_today_plans = {}  # group_key -> list of parsed plans
    plan_tomorrow_status = {}  # group_key -> {found, sent_time, content, plan}

    async with client:
        me = await client.get_me()
        logger.info(f"🔑 Logged in: @{me.username} ({me.first_name})")

        for group_key, chat_id in GROUPS.items():
            logger.info(f"  📡 Scanning {group_key} ({chat_id})...")
            leader_id = leaders.get(group_key)
            plans = await scan_group_for_plans(client, chat_id, since_utc, leader_id=leader_id)
            logger.info(f"     Found {len(plans)} Daily Plan messages")

            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_plans = []
            for p in plans:
                dt = parse_plan_date(p.get("date", ""))
                if dt and dt.replace(hour=0, minute=0, second=0, microsecond=0) >= today_start:
                    today_plans.append(p)

            # ── Deduplicate before storing to Sheet (prevent duplicate rows) ──
            today_plans = deduplicate_plans_by_date(today_plans)

            if today_plans:
                all_today_plans[group_key] = today_plans

            # ── Scan Plan Tomorrow (plan for tomorrow's date) ──
            pt = await scan_plan_tomorrow(
                client, group_key, chat_id,
                target_date_str=tomorrow_str,
                leader_id=leader_id,
                since_utc=since_utc,
            )
            plan_tomorrow_status[group_key] = pt
            logger.info(f"     Plan Tomorrow ({tomorrow_str}): {'✅ Found' if pt['found'] else '❌ Not found'}")

            await asyncio.sleep(0.5)

    # ── Step 2: Get Daily Reports from Sheet for comparison ──
    logger.info("📖 Reading Daily Reports from sheet for comparison...")
    team_reports, df_report_raw = get_daily_reports_from_sheet(date_str)
    for gk, reps in team_reports.items():
        logger.info(f"  {gk}: {len(reps)} report entries today")

    # ── Step 3: Build comparison + store in Sheet ──
    logger.info("📝 Storing plans with comparison in Sheet...")
    team_comparisons = {}  # group_key -> comparison dict
    stored_count = 0

    for group_key, plans in all_today_plans.items():
        for p in plans:
            # Build daily report text for col E
            reports = team_reports.get(group_key, [])
            daily_report_text = "\n\n".join(reports) if reports else ""

            # Build comparison for col F
            comp = build_comparison(p["content"], reports)
            team_comparisons[group_key] = comp

            result = store_daily_plan(
                p["date"], p["team"], p["content"],
                daily_report=daily_report_text,
                comparison=comp["comparison_text"],
            )
            if result.get("status") == "ok":
                dup = result.get("duplicate", False)
                logger.info(f"  {'⏭️ Updated' if dup else '✅ Stored'}: {p['date']} {p['team']} (REF: {result.get('ref', '?')})")
                if not dup:
                    stored_count += 1
            else:
                logger.warning(f"  ❌ Store failed: {result.get('message', 'unknown')}")

    logger.info(f"  📊 Stored {stored_count} new plans")

    # ── Step 4: Read all plans from Sheet for 3Day/7Day/Month stats ──
    logger.info("📖 Reading plan history from Sheet...")
    all_plans = get_daily_plans()
    logger.info(f"  📊 Total plans in sheet: {len(all_plans)}")

    # ── Step 4a: Fallback — nếu Telegram scan không tìm thấy plan của team nào,
    #            lấy từ sheet (all_plans) để đảm bảo team_comparisons luôn có data ──
    for group_key in ("T1", "T2", "T3", "T4"):
        if group_key in team_comparisons:
            continue  # Đã có từ Telegram scan
        # Tìm plan hôm nay trong sheet
        sheet_plans_today = find_plans_for_date(all_plans, date_str, team_filter=group_key)
        if not sheet_plans_today:
            logger.info(f"  ⚠️ {group_key}: No plan found in sheet for {date_str} either")
            continue
        # Dùng plan mới nhất từ sheet
        sp = sheet_plans_today[0]
        comp_text = sp.get("comparison", "")
        if comp_text:
            # Parse comparison text để lấy plan_count/done_count/remain_count
            plan_m  = re.search(r'Plan:\s*(\d+)', comp_text)
            done_m  = re.search(r'Done:\s*(\d+)', comp_text)
            remain_m = re.search(r'Remaining:\s*(\d+)', comp_text)
            plan_cnt   = int(plan_m.group(1))   if plan_m   else 0
            done_cnt   = int(done_m.group(1))   if done_m   else 0
            remain_cnt = int(remain_m.group(1)) if remain_m else max(0, plan_cnt - done_cnt)
            pct = round(done_cnt / plan_cnt * 100) if plan_cnt > 0 else 0
            team_comparisons[group_key] = {
                "plan_count":    plan_cnt,
                "done_count":    done_cnt,
                "remain_count":  remain_cnt,
                "pct":           pct,
                "comparison_text": comp_text,
                "from_sheet":    True,  # đánh dấu nguồn
            }
            # Inject plan vào all_today_plans để stats["today_plans"] có dữ liệu
            all_today_plans.setdefault(group_key, [])
            if not all_today_plans[group_key]:
                all_today_plans[group_key].append(sp)
            logger.info(f"  📋 {group_key}: Loaded plan from sheet (REF: {sp.get('ref', '?')}, comp_text present)")
        else:
            # Không có comparison text, nhưng vẫn inject plan content
            reports = team_reports.get(group_key, [])
            comp = build_comparison(sp.get("content", ""), reports)
            team_comparisons[group_key] = comp
            all_today_plans.setdefault(group_key, [])
            if not all_today_plans[group_key]:
                all_today_plans[group_key].append(sp)
            logger.info(f"  📋 {group_key}: Loaded plan from sheet (REF: {sp.get('ref', '?')}), rebuilt comparison")


    # ── Step 4b: Get employee stats từ Apps Script ──
    logger.info("📊 Fetching employee stats (rank/close/WO remain)...")
    unified_employees = get_unified_employees()
    # Gom nhân viên theo team key
    team_emp_map: dict[str, list] = {}  # "T1"→[emp,...]
    for emp in unified_employees:
        tk = emp.get("team", "")
        if tk in ("T1","T2","T3","T4"):
            team_emp_map.setdefault(tk, []).append(emp)
    logger.info(f"  📋 Employees mapped: { {k: len(v) for k,v in team_emp_map.items()} }")

    # ── Step 4c: Đếm số lần nộp daily result per-person ──
    logger.info("📊 Counting employee daily report submissions...")
    daily_counts = get_employee_report_counts(unified_employees)  # { tg_id: {d0,d1,d2,d7,month} }

    # ── Step 5: Build and send reports ──
    if not SEND_BOT_TOKEN:
        logger.error("SEND_BOT_TOKEN not set — cannot send reports")
        return

    divider = "━" * 30
    sub_divider = "──────────"

    async with Bot(token=SEND_BOT_TOKEN) as bot:
        # ── 5a. Send per-team reports ──
        for group_key, chat_id in GROUPS.items():
            team_name = GROUP_NAMES.get(group_key, group_key)
            stats     = build_plan_stats(all_plans, team_filter=group_key)
            comp      = team_comparisons.get(group_key)
            emps      = team_emp_map.get(group_key, [])  # danh sách nhân viên

            lines = [
                f"📋 5. Report — Daily Plan & Results ({date_str}) — {team_name}",
                f"📅 {date_str}  |  🕐 {now.strftime('%H:%M')}",
                f"📌 Comparison of plan for {date_str} vs actual completed stations.",
                divider,
                f"📊 Plan Stats: 3Day: {stats['d2']}/{stats['d1']}/{stats['d0']} "
                f"| 7Day: {stats['d7']} | Month: {stats['month']}",
            ]

            # ── Phần Team Leader: chỉ đếm TNI + Plan vs Actual ──
            if stats["today_plans"]:
                # Đếm tổng TNI codes trong plan hôm nay
                all_plan_tni = set()
                for tp in stats["today_plans"]:
                    all_plan_tni |= extract_tni_codes(tp.get("content", ""))
                plan_count_tni = len(all_plan_tni)
                lines.append(f"📝 Plan: {plan_count_tni} stations"
                             + (f" ({', '.join(sorted(all_plan_tni))})" if all_plan_tni else ""))
                if comp and comp.get("plan_count", 0) > 0:
                    lines.append("📊 Plan vs Actual:")
                    lines.append(comp["comparison_text"])
            else:
                lines.append("❌ No Daily Plan submitted today")

            # ── Phần Consolidated FT Plan & Actual ──
            emp_completed_details = get_employee_completed_tni_today_detailed(df_report_raw, date_str, emps)
            combined_plan_text = "\n".join(tp.get("content", "") for tp in stats["today_plans"])
            emp_assigned_map = parse_assigned_tni_per_person(combined_plan_text, emps)

            if emps:
                lines.append(divider)
                lines.append(f"📋 FT Plan & Actual Summary ({date_str}):")
                for emp in sorted(emps, key=lambda e: e.get("name", "")):
                    sys_name = emp.get("sys_name", emp.get("username", ""))
                    if sys_name and "team leader" in str(sys_name).lower():
                        continue

                    name = emp.get("name", "")
                    tg_id = str(emp.get("telegram_id", emp.get("tg_id", ""))).replace(".0", "")

                    assigned_set = emp_assigned_map.get(tg_id, set())
                    emp_details = emp_completed_details.get(tg_id, {})
                    completed_set = set(emp_details.keys())
                    done_set = assigned_set & completed_set
                    remain_set = assigned_set - completed_set

                    # Determine report submission status today
                    sent_today = False
                    if daily_counts and tg_id in daily_counts:
                        sent_today = (daily_counts[tg_id].get("d0", 0) > 0)
                    if completed_set:
                        sent_today = True

                    report_status_text = "Sent" if sent_today else "Not sent"

                    # Determine color:
                    # - 🟢 = 100% of plan completed (report sent)
                    # - 🟡 = >0% but <100% completed (report sent)
                    # - 🔴 = Plan assigned, but report not sent (0% completion)
                    # - 🔵 = No plan assigned, but report was sent
                    # - ⚫ = No plan assigned, and report not sent
                    if not assigned_set:
                        color = "🔵" if sent_today else "⚫"
                    else:
                        if sent_today:
                            pct = int((len(done_set) / len(assigned_set)) * 100)
                            color = "🟢" if pct == 100 else "🟡"
                        else:
                            color = "🔴"

                    display_name = f"{name}-{sys_name}" if sys_name else name
                    lines.append(f"{color} {display_name}")

                    if assigned_set:
                        pct = int((len(done_set) / len(assigned_set)) * 100)
                        lines.append(f"   • Plan: {', '.join(sorted(assigned_set))}")
                        lines.append(f"   • Completed: {', '.join(sorted(done_set)) if done_set else 'None'} (Done: {len(done_set)}/{len(assigned_set)}, {pct}%)")
                        if remain_set:
                            lines.append(f"   • Remaining: {', '.join(sorted(remain_set))}")
                        
                        # Khác biệt so với kế hoạch được giao
                        diff_set = completed_set - assigned_set
                        if diff_set:
                            header_to_codes = {}
                            for code in sorted(diff_set):
                                header = emp_details.get(code, "Report")
                                header_to_codes.setdefault(header, []).append(code)
                            
                            diff_items = []
                            for header, codes in header_to_codes.items():
                                diff_items.append(f"{header}: {', '.join(codes)}")
                            lines.append(f"   • Different from Plan: {'; '.join(diff_items)}")
                    else:
                        lines.append("   • Plan: None")
                        if completed_set:
                            header_to_codes = {}
                            for code in sorted(completed_set):
                                header = emp_details.get(code, "Report")
                                header_to_codes.setdefault(header, []).append(code)
                            
                            completed_items = []
                            for header, codes in header_to_codes.items():
                                completed_items.append(f"{header}: {', '.join(codes)}")
                            lines.append(f"   • Completed: {'; '.join(completed_items)}")

                    lines.append(f"   • Report: {report_status_text}")

                    dr_part = "3Day: 0/0/0 | 7Day: 0 | Month: 0"
                    if daily_counts and tg_id in daily_counts:
                        dc = daily_counts[tg_id]
                        d0_val = max(dc.get("d0", 0), 1) if completed_set else dc.get("d0", 0)
                        d7_val = max(dc.get("d7", 0), 1) if completed_set else dc.get("d7", 0)
                        m_val  = max(dc.get("month", 0), 1) if completed_set else dc.get("month", 0)
                        dr_part = f"3Day: {dc.get('d2', 0)}/{dc.get('d1', 0)}/{d0_val} | 7Day: {d7_val} | Month: {m_val}"
                    elif completed_set:
                        dr_part = "3Day: 0/0/1 | 7Day: 1 | Month: 1"
                    lines.append(f"   • Submission Stats: {dr_part}")

            # ── Plan Tomorrow section ──
            lines.append(divider)
            pt = plan_tomorrow_status.get(group_key, {"found": False})
            lines.append(f"📝 Plan Tomorrow ({tomorrow_str}):")
            if pt["found"]:
                sent_str = fmt_sent_at(pt.get("sent_time"))
                if sent_str:
                    lines.append(f"✅ Team Leader: Submitted ✓ (sent at {sent_str})")
                else:
                    lines.append(f"✅ Team Leader: Submitted ✓")
            else:
                lines.append("❌ Team Leader: Not yet submitted")
            lines.append(divider)

            msg = "\n".join(lines)
            delete_key = f"{delete_prefix}_{group_key}"
            delete_old_messages_bot(SEND_BOT_TOKEN, chat_id, APPS_SCRIPT_URL, delete_key)
            ok, msg_ids = await send_msg(bot, chat_id, msg, f"PLAN-{mode_label}-{group_key}")
            if ok and msg_ids:
                save_msgids(APPS_SCRIPT_URL, delete_key, msg_ids)
            await asyncio.sleep(0.5)

        # ── 5b. Send consolidated report to CONTROL ──
        ctrl_lines = [
            f"📋 5. Report — Daily Plan & Results ({date_str}) — Summary",
            f"📅 {date_str}  |  🕐 {now.strftime('%H:%M')}",
            f"📌 Comparison of plan for {date_str} vs actual completed stations.",
            divider,
        ]

        total_d0 = total_d1 = total_d2 = total_d7 = total_month = 0
        total_plan = total_done = total_remain = 0
        team_today_contents = []

        for group_key in ("T1", "T2", "T3", "T4"):
            team_name = GROUP_NAMES.get(group_key, group_key)
            stats = build_plan_stats(all_plans, team_filter=group_key)
            comp = team_comparisons.get(group_key)

            total_d0 += stats["d0"]
            total_d1 += stats["d1"]
            total_d2 += stats["d2"]
            total_d7 += stats["d7"]
            total_month += stats["month"]

            ctrl_lines.append(f"🏷️ {team_name}:")

            if comp and stats["d0"] > 0:
                ctrl_lines.append(
                    f"   Plan: {comp['plan_count']} | Done: {comp['done_count']} "
                    f"({comp['pct']}%) | Remain: {comp['remain_count']}"
                )
                total_plan += comp["plan_count"]
                total_done += comp["done_count"]
                total_remain += comp["remain_count"]
            elif stats["d0"] > 0:
                ctrl_lines.append("   ✅ Plan submitted today")
            else:
                ctrl_lines.append("   ❌ No plan today")

            ctrl_lines.append(
                f"   3Day: {stats['d2']}/{stats['d1']}/{stats['d0']} "
                f"| 7Day: {stats['d7']} | Month: {stats['month']}"
            )

            # Collect today's content
            if stats["today_plans"]:
                for tp in stats["today_plans"]:
                    team_today_contents.append((team_name, tp.get("content", "")))

        ctrl_lines.append(divider)

        # Grand totals
        total_pct = round(total_done / total_plan * 100) if total_plan > 0 else 0
        if total_plan > 0:
            ctrl_lines.append(
                f"📊 Total: Plan: {total_plan} | Done: {total_done} "
                f"({total_pct}%) | Remain: {total_remain}"
            )
        ctrl_lines.append(
            f"📊 3Day: {total_d2}/{total_d1}/{total_d0} "
            f"| 7Day: {total_d7} | Month: {total_month}"
        )

        # Today's plan contents
        if team_today_contents:
            ctrl_lines.append("")
            ctrl_lines.append(f"📝 Plans for {date_str}:")
            for team_name, content in team_today_contents:
                ctrl_lines.append(sub_divider)
                ctrl_lines.append(f"🏷️ {team_name}:")
                ctrl_lines.append(colorize_bullets(content))  # • [Admin] → vuông màu

        # ── Plan Tomorrow summary for CONTROL ──
        ctrl_lines.append(divider)
        ctrl_lines.append(f"📝 Plan Tomorrow ({tomorrow_str}):")
        for group_key in ("T1", "T2", "T3", "T4"):
            team_name = GROUP_NAMES.get(group_key, group_key)
            pt = plan_tomorrow_status.get(group_key, {"found": False})
            if pt["found"]:
                sent_str = fmt_sent_at(pt.get("sent_time"))
                if sent_str:
                    ctrl_lines.append(f"   ✅ {team_name}: Submitted ✓ (sent at {sent_str})")
                else:
                    ctrl_lines.append(f"   ✅ {team_name}: Submitted ✓")
            else:
                ctrl_lines.append(f"   ❌ {team_name}: Not yet submitted")

        ctrl_lines.append(divider)

        ctrl_msg = "\n".join(ctrl_lines)
        ctrl_delete_key = f"{delete_prefix}_CONTROL"
        delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, ctrl_delete_key)
        ok, msg_ids = await send_msg(bot, CONTROL_CHAT_ID, ctrl_msg, f"PLAN-{mode_label}-CONTROL")
        if ok and msg_ids:
            save_msgids(APPS_SCRIPT_URL, ctrl_delete_key, msg_ids)

    logger.info(f"🎉 Daily Plan Report ({mode_label}) complete – {myanmar_now().strftime('%H:%M')}")


async def run_morning():
    """Run morning report mode."""
    now = myanmar_now()
    now_str = now.strftime("%d/%m/%Y %H:%M")
    # Sau 14:00 MMT trong ngày → Tự động nhảy cộng +1 ngày để làm Plan cho ngày mai
    if now.hour >= 14:
        target_date = now + timedelta(days=1)
    else:
        target_date = now
    date_str = target_date.strftime("%d/%m/%Y")
    delete_prefix = "PLAN_MRN"

    logger.info(f"🚀 Daily Plan Report (Morning) start – {now_str}")

    # Scan for today's plan (sent yesterday or early morning with date = today)
    since_utc = (now - timedelta(days=2)).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).astimezone(timezone.utc)

    leaders = get_team_leaders()
    logger.info(f"  📋 Team leaders loaded: {leaders}")

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    plan_today_status = {}  # group_key -> {found, sent_time, content, plan}

    async with client:
        me = await client.get_me()
        logger.info(f"🔑 Logged in: @{me.username} ({me.first_name})")

        for group_key, chat_id in GROUPS.items():
            logger.info(f"  📡 Scanning {group_key} for today's plan ({date_str})...")
            leader_id = leaders.get(group_key)

            pt = await scan_plan_tomorrow(
                client, group_key, chat_id,
                target_date_str=date_str,  # Today's date
                leader_id=leader_id,
                since_utc=since_utc,
            )
            plan_today_status[group_key] = pt
            logger.info(f"     Plan today ({date_str}): {'✅ Found' if pt['found'] else '❌ Not found'}")
            await asyncio.sleep(0.5)

    # Read plan history from Sheet for stats
    logger.info("📖 Reading plan history from Sheet...")
    all_plans = get_daily_plans()
    logger.info(f"  📊 Total plans in sheet: {len(all_plans)}")

    # ── Fallback: nếu Telegram scan không tìm thấy plan hôm nay,
    #              thử lấy từ sheet (all_plans) ──
    for group_key in list(GROUPS.keys()):
        pt = plan_today_status.get(group_key, {"found": False})
        if pt["found"]:
            continue
        sheet_plans_today = find_plans_for_date(all_plans, date_str, team_filter=group_key)
        if sheet_plans_today:
            sp = sheet_plans_today[0]
            plan_today_status[group_key] = {
                "found": True,
                "sent_time": fmt_sent_at(sp.get("msg_date", "")),  # có thể trống nếu chỉ có từ sheet
                "content": sp.get("content", ""),
                "plan": sp,
                "from_sheet": True,
            }
            logger.info(f"  📋 {group_key}: Plan found in sheet (REF: {sp.get('ref', '?')}) — using as fallback")

    # Build 3-day completion rate
    logger.info("📊 Calculating 3-day completion rate...")
    completion_rate = calc_3day_completion_rate(all_plans, {})

    if not SEND_BOT_TOKEN:
        logger.error("SEND_BOT_TOKEN not set — cannot send reports")
        return

    divider = "━" * 30

    async with Bot(token=SEND_BOT_TOKEN) as bot:
        # ── Per-team morning reports ──
        for group_key, chat_id in GROUPS.items():
            team_name = GROUP_NAMES.get(group_key, group_key)
            stats = build_plan_stats(all_plans, team_filter=group_key)
            pt = plan_today_status.get(group_key, {"found": False})
            # Adjust stats if today's plan is found but not yet stored in sheet
            if pt["found"] and stats["d0"] == 0:
                stats["d0"] = 1
                stats["d7"] += 1
                stats["month"] += 1
            cr = completion_rate.get(group_key, {"days": [], "total_plan": 0, "total_done": 0, "pct": 0})

            lines = [
                f"📋 5.1 Report — Plan ({date_str}) — {team_name}",
                f"📅 {date_str}  |  🕐 {now.strftime('%H:%M')}",
                divider,
            ]

            # Plan today status
            lines.append(f"📝 Plan for {date_str}:")
            if pt["found"]:
                sent_at = fmt_sent_at(pt.get("sent_time", ""))
                if sent_at:
                    lines.append(f"✅ Team Leader: Submitted ✓ (sent at {sent_at})")
                else:
                    lines.append(f"✅ Team Leader: Submitted ✓ (recorded in sheet)")
                lines.append("")
                lines.append("📋 Plan Content:")
                plan_content = clean_plan_content(pt["content"])
                if len(plan_content) > 1500:
                    plan_content = plan_content[:1500].rsplit("\n", 1)[0] + "\n... [see full plan in group]"
                lines.append(colorize_bullets(plan_content))
            else:
                lines.append("⚠️ Team Leader: NOT SUBMITTED (Deadline: before 07:00)")

            # Submission history
            lines.append(divider)
            lines.append(
                f"📊 Submission History: 3Day: {stats['d2']}/{stats['d1']}/{stats['d0']} "
                f"| 7Day: {stats['d7']} | Month: {stats['month']}"
            )

            # 3-day completion rate
            lines.append("")
            lines.append("📈 3-Day Completion Rate:")
            for day_info in cr["days"]:
                sent_info = f" (sent at {day_info['sent_at']})" if day_info.get("sent_at") else ""
                if day_info["plan_count"] > 0:
                    lines.append(
                        f"   {day_info['date']}: Plan {day_info['plan_count']}{sent_info} "
                        f"→ Done {day_info['done_count']} ({day_info['pct']}%)"
                    )
                else:
                    lines.append(f"   {day_info['date']}: No plan")

            if cr["total_plan"] > 0:
                lines.append(
                    f"   Overall: {cr['total_done']}/{cr['total_plan']} = {cr['pct']}%"
                )
            else:
                lines.append("   Overall: No data")

            lines.append(divider)

            msg = "\n".join(lines)
            delete_key = f"{delete_prefix}_{group_key}"
            delete_old_messages_bot(SEND_BOT_TOKEN, chat_id, APPS_SCRIPT_URL, delete_key)
            ok, msg_ids = await send_msg(bot, chat_id, msg, f"PLAN-MRN-{group_key}")
            if ok and msg_ids:
                save_msgids(APPS_SCRIPT_URL, delete_key, msg_ids)
            await asyncio.sleep(0.5)

        # ── CONTROL consolidated morning report ──
        ctrl_lines = [
            f"📋 5.1 Report — Plan ({date_str}) — Summary",
            f"📅 {date_str}  |  🕐 {now.strftime('%H:%M')}",
            divider,
        ]

        for group_key in ("T1", "T2", "T3", "T4"):
            team_name = GROUP_NAMES.get(group_key, group_key)
            pt = plan_today_status.get(group_key, {"found": False})
            stats = build_plan_stats(all_plans, team_filter=group_key)
            # Adjust stats if today's plan is found but not yet stored in sheet
            if pt["found"] and stats["d0"] == 0:
                stats["d0"] = 1
                stats["d7"] += 1
                stats["month"] += 1
            cr = completion_rate.get(group_key, {"days": [], "total_plan": 0, "total_done": 0, "pct": 0})

            ctrl_lines.append(f"🏷️ {team_name}:")
            if pt["found"]:
                sent_at = fmt_sent_at(pt.get("sent_time", ""))
                if sent_at:
                    ctrl_lines.append(f"   ✅ Plan Submitted ✓ (sent at {sent_at})")
                else:
                    ctrl_lines.append("   ✅ Plan Submitted ✓ (recorded in sheet)")
            else:
                ctrl_lines.append("   ⚠️ NOT SUBMITTED (Deadline: before 07:00)")
            ctrl_lines.append(
                f"   3Day: {stats['d2']}/{stats['d1']}/{stats['d0']} "
                f"| 7Day: {stats['d7']} | Month: {stats['month']}"
            )
            if cr["total_plan"] > 0:
                ctrl_lines.append(
                    f"   📈 Completion: {cr['total_done']}/{cr['total_plan']} = {cr['pct']}%"
                )

        ctrl_lines.append(divider)

        # Overall completion rate
        overall_cr = completion_rate.get("overall", {"total_plan": 0, "total_done": 0, "pct": 0})
        if overall_cr["total_plan"] > 0:
            ctrl_lines.append(
                f"📊 Overall 3-Day Completion: "
                f"{overall_cr['total_done']}/{overall_cr['total_plan']} = {overall_cr['pct']}%"
            )

        # Today's plan contents
        has_any_plan = any(plan_today_status.get(gk, {}).get("found", False) for gk in ("T1", "T2", "T3", "T4"))
        if has_any_plan:
            ctrl_lines.append("")
            ctrl_lines.append(f"📝 Plans for {date_str}:")
            for group_key in ("T1", "T2", "T3", "T4"):
                pt = plan_today_status.get(group_key, {"found": False})
                if pt["found"]:
                    team_name = GROUP_NAMES.get(group_key, group_key)
                    ctrl_lines.append("──────────")
                    ctrl_lines.append(f"🏷️ {team_name}:")
                    ctrl_lines.append(colorize_bullets(clean_plan_content(pt["content"])))

        ctrl_lines.append(divider)

        ctrl_msg = "\n".join(ctrl_lines)
        ctrl_delete_key = f"{delete_prefix}_CONTROL"
        delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, ctrl_delete_key)
        ok, msg_ids = await send_msg(bot, CONTROL_CHAT_ID, ctrl_msg, "PLAN-MRN-CONTROL")
        if ok and msg_ids:
            save_msgids(APPS_SCRIPT_URL, ctrl_delete_key, msg_ids)

    logger.info(f"🎉 Daily Plan Report (Morning) complete – {myanmar_now().strftime('%H:%M')}")


async def main():
    parser = argparse.ArgumentParser(description="Daily Plan Report — 3 modes")
    parser.add_argument(
        "--mode",
        choices=["eod", "update", "morning"],
        default="eod",
        help="Report mode: eod (17:00), update (21:00), morning (07:00)",
    )
    args = parser.parse_args()

    logger.info(f"📌 Mode: {args.mode}")

    if args.mode in ("eod", "update"):
        await run_eod_or_update(args.mode)
    elif args.mode == "morning":
        await run_morning()


if __name__ == "__main__":
    asyncio.run(main())

