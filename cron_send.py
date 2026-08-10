"""
cron_send.py — GitHub Actions Cron Job: gửi task remain + management report.
Dùng 3 bot theo dải row trong sheet Task remain (gid=133591305):
  Row 4-32:  @TNIREPORTTASK_BOT        (nhân viên)
  Row 33-59: SEND_BOT                  (team leaders)
  Row 60-74: SEND_BOT + compiled report (management)
  Row 75-87: @TNITECHINICALDEPREPORT_BOT (technical dept)
"""
import asyncio, io, logging, os, re, requests, pandas as pd
from datetime import datetime, timezone, timedelta
from telegram import Bot
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
from delete_old_helper import delete_old_messages_bot, save_msgids, delete_by_title_telethon

load_dotenv()
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

SEND_BOT_TOKEN          = os.getenv("SEND_BOT_TOKEN", "")
REPORT_TASK_BOT_TOKEN   = os.getenv("REPORT_TASK_BOT_TOKEN", "")
TECHNICAL_DEP_BOT_TOKEN = os.getenv("TECHNICAL_DEP_BOT_TOKEN", "")
MAIN_GAS_FALLBACK   = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
APPS_SCRIPT_URL   = os.getenv("APPS_SCRIPT_URL", "").strip()
if not APPS_SCRIPT_URL or "AKfycbzGFdnE" in APPS_SCRIPT_URL:
    APPS_SCRIPT_URL = MAIN_GAS_FALLBACK
TELEGRAM_API_ID         = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH       = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION        = os.getenv("TELEGRAM_SESSION", "")

SPREADSHEET_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8"
# Dùng gviz/tq thay vì export?format=csv — export trả 307 redirect từ GitHub Actions
SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
    "/gviz/tq?tqx=out:csv&gid=133591305"
)
STAFF_SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
    "/gviz/tq?tqx=out:csv&gid=1684930643"
)
CONFIG_SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
    "/gviz/tq?tqx=out:csv&gid=1236389870"
)
TZ_MM = timezone(timedelta(hours=6, minutes=30))
HEADER_ROWS = 3  # rows 1-3 là header (row 3 có 'export sms')
COL_A, COL_B, COL_C, COL_D, COL_E = 0, 1, 2, 3, 4

# ── Group Chat IDs của 4 team (từ botlookup_relay.py) ───────────
from tni_config import TELEGRAM_GROUPS
TEAM_GROUPS = {
    "MYT_TNI_TEAM01_Dawei":     TELEGRAM_GROUPS["T1"],
    "MYT_TNI_TEAM02_Myeik":     TELEGRAM_GROUPS["T2"],
    "MYT_TNI_TEAM03_Bokpyin":   TELEGRAM_GROUPS["T3"],
    "MYT_TNI_TEAM04_Kawthoung": TELEGRAM_GROUPS["T4"],
}
TEAM_ICON = {
    "MYT_TNI_TEAM01_Dawei":     "1️⃣",
    "MYT_TNI_TEAM02_Myeik":     "2️⃣",
    "MYT_TNI_TEAM03_Bokpyin":   "3️⃣",
    "MYT_TNI_TEAM04_Kawthoung": "4️⃣",
}
TEAM_SHORT = {
    "MYT_TNI_TEAM01_Dawei":     "Team1 Dawei",
    "MYT_TNI_TEAM02_Myeik":     "Team2 Myeik",
    "MYT_TNI_TEAM03_Bokpyin":   "Team3 Bokpyin",
    "MYT_TNI_TEAM04_Kawthoung": "Team4 Kawthoung",
}
# Icon vuông màu cho Technical Dept (mỗi dept 1 màu cố định)
EMP_ICONS = ["🟧","🟦","🟩","🟨","🟥","🟣","⬜","🟧","🟦","🟩","🟨","🟥"]


def safe(row, idx):
    try:
        v = row.iloc[idx]
        s = "" if pd.isna(v) else str(v).strip()
        return "" if s.lower() in ("nan", "none", "") else s
    except Exception:
        return ""


def call_apps_script(payload, timeout=30):
    """Call Apps Script and return JSON response."""
    if not APPS_SCRIPT_URL:
        return {}
    try:
        resp = requests.post(APPS_SCRIPT_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Apps Script error: {e}")
        return {}


def get_asset_stats():
    """Get asset stats from Apps Script."""
    data = call_apps_script({"action": "get_asset_stats"}, timeout=120)
    if data.get("status") != "ok":
        logger.warning(f"get_asset_stats failed: {data.get('message', 'unknown')}")
        return {}
    return data


def get_report_data():
    """Get search stats from Apps Script (employees, leaders, teamSummary, grandTotal)."""
    data = call_apps_script({"action": "get_report_data"}, timeout=120)
    if data.get("status") != "ok":
        logger.warning(f"get_report_data failed: {data.get('message', 'unknown')}")
        return {}
    return data


def build_search_summary(now_str, report_data):
    """Build search stats summary with 3-day/7-day/month per team + grand total."""
    team_summary = report_data.get("teamSummary", [])
    grand = report_data.get("grandTotal", {})
    if not team_summary:
        return ""

    TEAM_SHORT = {
        "MYT_TNI_TEAM01_Dawei": "Team1(Dawei)",
        "MYT_TNI_TEAM02_Myeik": "Team2(Myeik)",
        "MYT_TNI_TEAM03_Bokpyin": "Team3(Bokpyin)",
        "MYT_TNI_TEAM04_Kawthoung": "Team4(Kawthoung)",
    }

    lines = [f"🔍 Search Stats – {now_str}"]
    for ts in team_summary:
        t_key = ts.get("team", "")
        if t_key not in TEAM_SHORT:
            continue  # Bỏ qua các team test/không hợp lệ
        tm = TEAM_SHORT[t_key]
        lines.append(
            f"🏷️ {tm}: "
            f"3Day:{ts.get('d2',0)}/{ts.get('d1',0)}/{ts.get('today',0)} "
            f"7Day:{ts.get('week',0)} Month:{ts.get('month',0)}"
        )
    lines.append(
        f"📊 Total: "
        f"3Day:{grand.get('d2',0)}/{grand.get('d1',0)}/{grand.get('today',0)} "
        f"7Day:{grand.get('week',0)} Month:{grand.get('month',0)}"
    )
    return "\n".join(lines)


def get_note_from_sheet() -> str:
    """Read H1:H5 from Config tab (GID 1236389870) — Note column is H (index 7)."""
    try:
        resp = requests.get(CONFIG_SHEET_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str, on_bad_lines="skip")
        
        note_lines = []
        for r_idx in range(0, min(5, len(df))):
            if len(df.columns) > 7:
                val = str(df.iloc[r_idx].iloc[7]).strip() if not pd.isna(df.iloc[r_idx].iloc[7]) else ""
                if val and val.lower() not in ("nan", "none", ""):
                    note_lines.append(val)
        return "\n".join(note_lines)
    except Exception as e:
        logger.error(f"Error fetching Note from Config sheet: {e}")
        return ""


def get_control_note_from_sheet() -> str:
    """Read H1:H3 from Config tab (GID 1236389870)."""
    try:
        resp = requests.get(CONFIG_SHEET_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str, on_bad_lines="skip")
        
        note_lines = []
        for r_idx in range(0, min(3, len(df))):
            if len(df.columns) > 7:
                val = str(df.iloc[r_idx].iloc[7]).strip() if not pd.isna(df.iloc[r_idx].iloc[7]) else ""
                if val and val.lower() not in ("nan", "none", ""):
                    note_lines.append(val)
        return "\n".join(note_lines)
    except Exception as e:
        logger.error(f"Error fetching Control Note from Config sheet: {e}")
        return ""


def get_current_cycle_str() -> str:
    now = datetime.now(TZ_MM)
    if now.day <= 20:
        end_date = now.replace(day=20)
        prev_month = now.month - 1
        prev_year = now.year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        start_date = now.replace(year=prev_year, month=prev_month, day=21)
    else:
        start_date = now.replace(day=21)
        next_month = now.month + 1
        next_year = now.year
        if next_month == 13:
            next_month = 1
            next_year += 1
        end_date = now.replace(year=next_year, month=next_month, day=20)
        
    return f"{start_date.strftime('%d/%m/%y')}-{end_date.strftime('%d/%m/%y')}"


def get_no_id_members(bot_token: str = "") -> dict:
    """
    Đọc Staff sheet (gid=1684930643):
    - Col A (index 0): Telegram user_id (nếu trống = chưa có ID)
    - Col F (index 5): Tên nhân viên
    - Col N (index 13): Team assignment (nếu có nội dung = đang trong team)

    Trả về dict: team_key -> {
        "no_id":       [name, ...],   # chưa có ID Telegram
        "not_in_group":[name, ...],   # có ID nhưng chưa join group
    }
    """
    try:
        resp = requests.get(
            STAFF_SHEET_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str, on_bad_lines="skip")
    except Exception as e:
        logger.warning(f"get_no_id_members: cannot fetch Staff sheet: {e}")
        return {}

    # Mapping col N → team_key (và group chat_id để check membership)
    # Map col M values: 'Team 01' -> team_key (Team 05 gộp vào Team 2)
    TEAM_N_MAP = {
        "Team 01": ("MYT_TNI_TEAM01_Dawei",     TELEGRAM_GROUPS["T1"]),
        "Team 02": ("MYT_TNI_TEAM02_Myeik",     TELEGRAM_GROUPS["T2"]),
        "Team 03": ("MYT_TNI_TEAM03_Bokpyin",   TELEGRAM_GROUPS["T3"]),
        "Team 04": ("MYT_TNI_TEAM04_Kawthoung", TELEGRAM_GROUPS["T4"]),
        "Team 05": ("MYT_TNI_TEAM02_Myeik",     TELEGRAM_GROUPS["T2"]),  # Team 5 ⇒ Team 2
    }

    # Collect: no_id và candidates cần check
    no_id_map:   dict = {}   # team_key -> [name]
    check_list:  list = []   # [(name, user_id_int, team_key, group_chat_id)]

    for idx_r, row in df.iterrows():
        if idx_r == 0:
            continue  # bỏ qua header row
        try:
            col_a   = str(row.iloc[0]).strip()  if not pd.isna(row.iloc[0])  else ""
            col_f   = str(row.iloc[5]).strip()  if not pd.isna(row.iloc[5])  else ""
            col_m   = str(row.iloc[12]).strip() if not pd.isna(row.iloc[12]) else ""
            col_n_s = str(row.iloc[13]).strip() if not pd.isna(row.iloc[13]) else ""
        except (IndexError, Exception):
            continue

        # Chỉ lấy NV khi col N (index 13) TRỐNG — nếu có Probation/Resign thì bỏ
        if col_n_s and col_n_s.lower() not in ("nan", ""):
            continue
        # col M phải có team info
        if not col_m or col_m.lower() in ("nan", ""):
            continue
        # col F phải có tên
        if not col_f or col_f.lower() in ("nan", ""):
            continue

        # Xác định team từ col_m — exact match với 'Team 01'...'Team 05'
        team_key = None; group_cid = None
        if col_m in TEAM_N_MAP:
            team_key, group_cid = TEAM_N_MAP[col_m]
        if not team_key:
            continue

        # Phân loại
        id_clean = col_a.replace(".0", "").strip() if col_a else ""
        # Đọc cột L (index 11) = Position
        try:
            col_l = str(row.iloc[11]).strip() if not pd.isna(row.iloc[11]) else ""
        except (IndexError, Exception):
            col_l = ""
        is_leader = col_l.upper() == "FOT TEAM LEADER"

        if not id_clean or id_clean.lower() in ("nan", "", "0"):
            # Chưa có ID
            no_id_map.setdefault(team_key, []).append(col_f)
        else:
            # Có ID → xếp vào danh sách cần check group
            try:
                check_list.append((col_f, int(id_clean), team_key, group_cid, is_leader))
            except ValueError:
                pass

    # Check group membership qua getChatMember
    not_in_group_map: dict = {}
    if bot_token and check_list:
        for name, uid, tk, gcid, is_leader in check_list:
            try:
                r = requests.get(
                    f"https://api.telegram.org/bot{bot_token}/getChatMember",
                    params={"chat_id": gcid, "user_id": uid},
                    timeout=8,
                )
                data = r.json()
                status = data.get("result", {}).get("status", "")
                if status in ("left", "kicked", ""):
                    not_in_group_map.setdefault(tk, []).append(name)
            except Exception:
                pass  # bỏ qua nếu lỗi network

    # Gom has_id theo team — luu ca ten (col F) va uid (Telegram ID)
    has_id_map: dict = {}
    leaders_map: dict = {}  # team_key -> [{name, uid}]
    for name, uid, tk, gcid, is_leader in check_list:
        has_id_map.setdefault(tk, []).append({"name": name, "uid": str(uid)})
        if is_leader:
            leaders_map.setdefault(tk, []).append({"name": name, "uid": str(uid)})

    all_teams = set(list(no_id_map.keys()) + list(not_in_group_map.keys()) + list(has_id_map.keys()) + list(leaders_map.keys()))
    return {
        tk: {
            "no_id":        no_id_map.get(tk, []),
            "not_in_group": not_in_group_map.get(tk, []),
            "has_id":       has_id_map.get(tk, []),
            "leaders":      leaders_map.get(tk, []),
        }
        for tk in all_teams
    }


def build_team_search_section(team_key: str, report_data: dict, now_str: str = "", no_id_members: dict | None = None) -> str:
    """Build search stats section for a specific team — tính Total từ teamSummary GAS (chính xác)."""
    if not team_key:
        return ""

    cycle_str = get_current_cycle_str()

    # Ưu tiên dùng teamSummary từ GAS — đã tính sẵn, đồng nhất với dữ liệu GAS
    d0_total = d1_total = d2_total = w_total = m_total = 0
    found_summary = False
    for ts in report_data.get("teamSummary", []):
        if ts.get("team", "") == team_key:
            d2_total = ts.get('d2', 0)
            d1_total = ts.get('d1', 0)
            d0_total = ts.get('today', 0)
            w_total  = ts.get('week', 0)
            m_total  = ts.get('month', 0)
            found_summary = True
            break

    # Fallback: nếu không có teamSummary thì tính từ searchStats + Staff UIDs
    if not found_summary:
        raw_search_stats = report_data.get("searchStats", {})
        if no_id_members:
            team_info = no_id_members.get(team_key, {})
            for item in team_info.get("has_id", []):
                uid = item.get("uid", "") if isinstance(item, dict) else ""
                if uid:
                    s = raw_search_stats.get(uid, {})
                    d0_total += s.get("today", 0)
                    d1_total += s.get("d1", 0)
                    d2_total += s.get("d2", 0)
                    w_total  += s.get("week", 0)
                    m_total  += s.get("month", 0)

    return (
        f"🔍 Search TNIxxxx click here @SEARCHTNITASKWOBOT "
        f"and Start if New FT write /myid : {now_str}\n"
        f"   Total: 3Day: {d2_total} /{d1_total} /{d0_total}  7Day: /{w_total}  Month: /{m_total} ({cycle_str})"
    )



# ── Team Leader search stats ──────────────────────────────────────────────────
def build_tl_search_section(team_key: str, report_data: dict, no_id_members: dict | None = None) -> str:
    """Hiển thị stats search của Team Leader (FOT Team Leader) — đặt trước phần NV."""
    if not team_key or not no_id_members:
        return ""

    team_info = no_id_members.get(team_key, {})
    leaders = team_info.get("leaders", [])
    if not leaders:
        return ""

    raw_search_stats = report_data.get("searchStats", {})
    raw_by_name = report_data.get("searchStatsByName", {})

    # Sort A-Z theo tên
    leaders_sorted = sorted(leaders, key=lambda x: x.get("name", ""))

    lines = ["👑 Team Leader Search: T1 | T1notclose | T1waitcd @SEARCHTNITASKWOBOT"]
    for tl in leaders_sorted:
        name = tl.get("name", "?")
        uid = tl.get("uid", "")
        s = raw_search_stats.get(uid, {}) if uid else {}
        if not s and name:
            short = name.strip().split()[0].lower()
            s = raw_by_name.get(short, {})
        d0 = s.get("today", 0)
        d1 = s.get("d1", 0)
        d2 = s.get("d2", 0)
        w  = s.get("week", 0)
        m  = s.get("month", 0)
        if d0 > 0:
            icon = "✅"   # search hôm nay
        elif d1 > 0 or d2 > 0:
            icon = "🟡"   # có search gần đây nhưng không phải hôm nay
        else:
            icon = "❌"   # 3 ngày không search
        lines.append(f"  {icon} {name}: 3Day: {d2} /{d1} /{d0}  7Day: /{w}  Month: /{m}")

    return "\n".join(lines)


def build_no_search_list(team_key: str, report_data: dict, no_id_members: dict | None = None) -> str:
    """
    3 phần trong search section theo team:
    1. Search Stats  — NV có ID: ai đã/chưa search TNIxxxx hôm nay
    2. Not in Group  — NV có ID nhưng chưa join nhóm Telegram
    3. No ID         — NV chưa có ID Telegram
    """
    if not team_key:
        return ""

    result_lines = []

    # ══ PHẦN 1: Search Stats — match Search Log UserID → Staff Sheet UserID → tên col F ══
    # searchStats từ GAS: { "userId": {today, d1, d2, week, month}, ... }
    raw_search_stats = report_data.get("searchStats", {})

    # Lấy danh sách NV có ID từ Staff sheet (col F) — list of {name, uid}
    staff_has_id: list = []
    if no_id_members:
        team_info_temp = no_id_members.get(team_key, {})
        staff_has_id = list(team_info_temp.get("has_id", []))

    # Fallback: nếu Staff sheet không trả has_id thì dùng report_data employees
    if not staff_has_id:
        all_members = list(report_data.get("employees", [])) + list(report_data.get("leaders", []))
        team_members_fb = [e for e in all_members if e.get("team", "") == team_key]
        seen_fb: dict = {}
        for e in team_members_fb:
            nm2 = e.get("name", "?")
            if nm2 not in seen_fb:
                seen_fb[nm2] = e
        staff_has_id = [{"name": e.get("name", "?"), "uid": str(e.get("chat_id", ""))} for e in seen_fb.values()]

    # Lấy danh sách Not in Group + No ID để loại khỏi Part 1
    exclude_names = set()
    if no_id_members:
        ti = no_id_members.get(team_key, {})
        exclude_names.update(ti.get("not_in_group", []))
        exclude_names.update(ti.get("no_id", []))

    if staff_has_id:
        not_searched_count = 0
        search_lines = []
        raw_by_name = report_data.get("searchStatsByName", {})  # fallback: key = short name lowercase
        def _get_name(item):
            return item["name"] if isinstance(item, dict) else item
        def _get_uid(item):
            return item.get("uid", "") if isinstance(item, dict) else ""
        def _lookup_search(uid: str, full_name: str) -> dict:
            """Lookup search stats: primary = UID, fallback = short name from searchStatsByName."""
            s = raw_search_stats.get(uid, {}) if uid else {}
            if not s and full_name:
                short = full_name.strip().split()[0].lower()
                s = raw_by_name.get(short, {})
            return s
        seen_names = set()
        for item in sorted(staff_has_id, key=lambda x: _get_name(x)):
            name = _get_name(item)
            uid = _get_uid(item)
            if name in seen_names:
                continue
            seen_names.add(name)
            # Bỏ qua người Not in Group hoặc No ID — hiển thị riêng ở Part 2/3
            if name in exclude_names:
                continue
            # Match trực tiếp bằng UserID từ GAS searchStats, fallback theo tên
            s = _lookup_search(uid, name)
            d0 = s.get("today", 0)
            d1 = s.get("d1", 0)
            d2 = s.get("d2", 0)
            w  = s.get("week", 0)
            m  = s.get("month", 0)
            if d0 > 0:
                icon = "✅"   # xanh: search hôm nay
            elif d1 > 0 or d2 > 0:
                icon = "🟡"   # vàng: có search gần đây nhưng không phải hôm nay
            else:
                icon = "❌"   # đỏ: 3 ngày không search
            if d0 == 0:
                not_searched_count += 1
            search_lines.append(f"  {icon} {name}: 3Day: {d2} /{d1} /{d0}  7Day: /{w}  Month: /{m}")

        result_lines.append(
            f"🔍 Part 1 — Search Stats ({not_searched_count} not searched today):"
        )
        result_lines.extend(search_lines)

    # ══ PHẦN 2 & 3: từ Staff sheet ══
    if no_id_members:
        team_info = no_id_members.get(team_key, {})

        # Phần 2 — Có ID nhưng chưa join Group
        not_in_group = sorted(set(team_info.get("not_in_group", [])))
        if not_in_group:
            result_lines.append(
                f"👥 Part 2 — Not in Group ({len(not_in_group)} members):"
            )
            for nm in not_in_group:
                result_lines.append(f"  ⚠️ {nm}: Not in Group")

        # Phần 3 — Chưa có ID Telegram
        no_id_list = sorted(set(team_info.get("no_id", [])))
        if no_id_list:
            result_lines.append(
                f"🆔 Part 3 — No ID Telegram ({len(no_id_list)} members):"
            )
            for nm in no_id_list:
                result_lines.append(f"  ❓ {nm}: Not Have ID telegram")

    return "\n".join(result_lines) if result_lines else ""



ACTION_SQUARES = {
    "export": "🟦",
    "import": "🟩",
    "return": "🟨",
    "transfer": "🟧",
    "collect": "🟪",
}

def get_action_square(at_name: str) -> str:
    clean = str(at_name).lower()
    for k, sq in ACTION_SQUARES.items():
        if k in clean:
            return sq
    return "🟦"

def build_asset_msg(now_str, asset_data):
    """Build compact asset stats message with 3-day/7-day/month."""
    if not asset_data.get("actionTypes"):
        return ""

    action_types = asset_data.get("actionTypes", [])
    teams = asset_data.get("teams", [])
    stats = asset_data.get("stats", {})
    grand = asset_data.get("grandTotal", {})

    TEAM_SHORT = {
        "MYT_TNI_TEAM01_Dawei": "Team1(Dawei)",
        "MYT_TNI_TEAM02_Myeik": "Team2(Myeik)",
        "MYT_TNI_TEAM03_Bokpyin": "Team3(Bokpyin)",
        "MYT_TNI_TEAM04_Kawthoung": "Team4(Kawthoung)",
    }

    def fmt(s):
        """Total /Done — space trước / để Telegram tự highlight xanh"""
        return f"{s.get('total',0)} /{s.get('done',0)}"

    def fmt_period(s):
        return (
            f"3Day: {s.get('d2',0)} /{s.get('done_d2',0)}"
            f" | {s.get('d1',0)} /{s.get('done_d1',0)}"
            f" | {s.get('d0',0)} /{s.get('done_d0',0)}"
            f"  7Day: {s.get('d6',0)} /{s.get('done_d6',0)}"
            f"  Month: {s.get('d15',0)} /{s.get('done_d15',0)}"
        )

    PERIOD_KEYS = ["d0","d1","d2","d6","d15","done_d0","done_d1","done_d2","done_d6","done_d15"]

    lines = [f"3.1 Asset progress for material – {now_str}", "━━━━━━━━━━━━━━━━━━━━"]

    for tm in teams:
        tm_short = TEAM_SHORT.get(tm, tm)
        lines.append(f"🏷️ {tm_short}:")
        for at in action_types:
            sq = get_action_square(at)
            val = fmt(stats.get(at,{}).get(tm,{}))
            lines.append(f"   {sq} {at}: {val}")
        team_total = {k: 0 for k in PERIOD_KEYS}
        for at in action_types:
            s = stats.get(at, {}).get(tm, {})
            for k in PERIOD_KEYS:
                team_total[k] += s.get(k, 0)
        lines.append(f"   📅 {fmt_period(team_total)}")

    # Grand total
    lines.append(f"📊 Total:")
    for at in action_types:
        sq = get_action_square(at)
        val = fmt(grand.get(at,{}))
        lines.append(f"   {sq} {at}: {val}")

    # Grand period
    g_period = {k: 0 for k in PERIOD_KEYS}
    for at in action_types:
        g = grand.get(at, {})
        for k in PERIOD_KEYS:
            g_period[k] += g.get(k, 0)
    lines.append(f"📅 Total  {fmt_period(g_period)}")

    return "\n".join(lines)


def build_team_asset_section(team_key: str, asset_data: dict) -> str:
    """Build asset stats section for a specific team."""
    if not asset_data.get("actionTypes") or not team_key:
        return ""

    action_types = asset_data.get("actionTypes", [])
    stats = asset_data.get("stats", {})
    PERIOD_KEYS = ["d0","d1","d2","d6","d15","done_d0","done_d1","done_d2","done_d6","done_d15"]

    key_lines = []
    has_data = False
    for at in action_types:
        ts = stats.get(at, {}).get(team_key, {})
        total = ts.get("total", 0)
        done = ts.get("done", 0)
        if total > 0 or done > 0:
            has_data = True
        sq = get_action_square(at)
        key_lines.append(f"   {sq} {at}: {total} /{done}")

    if not has_data:
        return ""

    # Period breakdown
    team_total = {k: 0 for k in PERIOD_KEYS}
    for at in action_types:
        s = stats.get(at, {}).get(team_key, {})
        for k in PERIOD_KEYS:
            team_total[k] += s.get(k, 0)

    cycle_str = get_current_cycle_str()
    period_line = (
        f"3Day: {team_total.get('d2',0)}/{team_total.get('d1',0)}/{team_total.get('d0',0)}"
        f"  7Day: {team_total.get('d6',0)}"
        f"  Month: {team_total.get('d15',0)} ({cycle_str})"
    )

    return (
        f"📦 3.1 Asset progress for material:\n" +
        "\n".join(key_lines) + "\n" +
        f"   📅 {period_line}"
    )


def build_team_asset_msg(team_key, now_str, asset_data):
    """Build asset stats message for a single team."""
    if not asset_data.get("actionTypes") or not team_key:
        return ""

    action_types = asset_data.get("actionTypes", [])
    stats = asset_data.get("stats", {})
    
    TEAM_SHORT = {
        "MYT_TNI_TEAM01_Dawei": "Team1(Dawei)",
        "MYT_TNI_TEAM02_Myeik": "Team2(Myeik)",
        "MYT_TNI_TEAM03_Bokpyin": "Team3(Bokpyin)",
        "MYT_TNI_TEAM04_Kawthoung": "Team4(Kawthoung)",
    }
    t_name = TEAM_SHORT.get(team_key, team_key)

    def fmt(s):
        """Total /Done — space trước / để Telegram tự highlight xanh"""
        return f"{s.get('total',0)} /{s.get('done',0)}"

    def fmt_period(s):
        return (
            f"3Day: {s.get('d2',0)} /{s.get('done_d2',0)}"
            f" | {s.get('d1',0)} /{s.get('done_d1',0)}"
            f" | {s.get('d0',0)} /{s.get('done_d0',0)}"
            f"  7Day: {s.get('d6',0)} /{s.get('done_d6',0)}"
            f"  Month: {s.get('d15',0)} /{s.get('done_d15',0)}"
        )

    PERIOD_KEYS = ["d0","d1","d2","d6","d15","done_d0","done_d1","done_d2","done_d6","done_d15"]

    key_lines = []
    for at in action_types:
        sq = get_action_square(at)
        val = fmt(stats.get(at,{}).get(team_key,{}))
        key_lines.append(f"   {sq} {at}: {val}")
    
    # Calculate period totals for this team
    team_total = {k: 0 for k in PERIOD_KEYS}
    for at in action_types:
        s = stats.get(at, {}).get(team_key, {})
        for k in PERIOD_KEYS:
            team_total[k] += s.get(k, 0)

    lines = [
        f"3.1 Asset progress for material – {t_name} – {now_str}",
        "━━━━━━━━━━━━━━━━━━━━"
    ] + key_lines + [
        f"   📅 {fmt_period(team_total)}"
    ]
    return "\n".join(lines)


INPUT_TASK_URL = (
    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
    "/gviz/tq?tqx=out:csv&gid=1755404595"
)


def get_input_task_summary(today: datetime) -> str:
    """
    Đọc sheet Input task (gid=1755404595) và tổng hợp theo từng Dep:
      Admin: Assign: 2 | Progress 0/0/0 7day: 0  Month 0 | Not yet confirm: 1
    """
    try:
        # Fetch với retry
        resp = None
        for attempt in range(3):
            try:
                resp = requests.get(
                    INPUT_TASK_URL,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=20,
                )
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt == 2:
                    raise e
                    
        df = pd.read_csv(
            io.StringIO(resp.text),
            header=0,  # dòng 1 là header
            dtype=str,
            on_bad_lines="skip",
        )
        df.columns = [c.strip() for c in df.columns]
        
        COL_DEP = 1
        COL_DONE = 9
        COL_CONF = 12
        
        # Mốc thời gian (loại bỏ tzinfo để so sánh với ngày parse từ csv)
        today = today.replace(tzinfo=None)
        day1 = today - timedelta(days=1)
        day2 = today - timedelta(days=2)
        day3 = today - timedelta(days=3)
        day7 = today - timedelta(days=7)
        
        def parse_date(val):
            if pd.isna(val):
                return None
            val_str = str(val).strip()
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    return datetime.strptime(val_str.split()[0], fmt)
                except ValueError:
                    continue
            return None

        stats = {}
        for _, row in df.iterrows():
            dep = str(row.iloc[COL_DEP]).strip() if not pd.isna(row.iloc[COL_DEP]) else ""
            if not dep or dep.lower() in ("", "nan", "dep assign", "sum"):
                continue
                
            j_val = row.iloc[COL_DONE]
            j_date = parse_date(j_val)
            j_date_str = str(j_val).strip() if not pd.isna(j_val) else ""
            
            m_val = row.iloc[COL_CONF]
            m_conf = str(m_val).strip() if not pd.isna(m_val) else ""
            is_confirmed = m_conf != "" and m_conf != "0"
            
            if dep not in stats:
                stats[dep] = {
                    "assign": 0,
                    "done_d3": 0,
                    "done_d2": 0,
                    "done_d1": 0,
                    "done_7d": 0,
                    "done_month": 0,
                    "not_yet_confirm": 0
                }
                
            s = stats[dep]
            s["assign"] += 1
            
            if j_date_str != "":
                # Chỉ tính các task có ngày hoàn thành nằm trong tháng hiện tại
                is_in_month = (j_date is not None) and (j_date.year == today.year) and (j_date.month == today.month)
                
                if is_confirmed:
                    if j_date is not None:
                        if j_date.date() == day3.date():
                            s["done_d3"] += 1
                        elif j_date.date() == day2.date():
                            s["done_d2"] += 1
                        elif j_date.date() == day1.date():
                            s["done_d1"] += 1
                        
                        if j_date >= day7:
                            s["done_7d"] += 1
                        if is_in_month:
                            s["done_month"] += 1
                else:
                    if is_in_month:
                        s["not_yet_confirm"] += 1
                        
        if not stats:
            return ""
            
        # Trái tim màu cố định cho mỗi Dep (9 màu, đồng cỡ)
        DEP_SQUARES = {
            "admin": "💙", "asset": "💚", "cm": "💛", "fbb": "🧡",
            "finance": "💜", "hr": "❤️", "m&e": "🤎", "manager": "🤍",
            "pm": "🖤", "transmission": "💙", "construction": "🧡",
            "construction projects": "🧡", "noc": "🖤", "technical": "💙",
        }
        lines = ["📋 Input Task by Dep:"]
        for dep in sorted(stats.keys()):
            s = stats[dep]
            progress = f"{s['done_d3']}/{s['done_d2']}/{s['done_d1']}"
            sq = DEP_SQUARES.get(dep.lower().strip(), "▪️")
            lines.append(
                f"  {sq} {dep}: Assign: {s['assign']} | Progress {progress} 7day: {s['done_7d']}  Month {s['done_month']} | Not yet confirm: {s['not_yet_confirm']}"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"get_input_task_summary failed: {e}")
        return ""


def get_input_task_detail(today: datetime) -> list:
    """
    Đọc sheet Input task (gid=1755404595) và build chi tiết theo Dep → Team → Loại task.
    Trả về list[str] — mỗi Dep là 1 message riêng.

    Format:
      🟡 CM 06/07/2026
      Team 01
      Request Export material : total : 28  Progress 3 day: 0/0/0, 7 day: 0, Month: 0
      Team 02
      Request Export material : total : 14  Progress 3 day: 0/0/0, 7 day: 0, Month: 0
    """
    # Chấm tròn màu cố định cho Dep
    DEP_CIRCLES = {
        "admin": "🔵", "asset": "🟢", "cm": "🟡", "fbb": "🟠",
        "finance": "🟣", "hr": "🔴", "m&e": "🟤", "manager": "⚪",
        "pm": "⚫", "transmission": "🔵", "construction": "🟠",
        "construction projects": "🟠", "noc": "⚫", "technical": "🔵",
    }
    try:
        resp = None
        for attempt in range(3):
            try:
                resp = requests.get(
                    INPUT_TASK_URL,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=20,
                )
                resp.raise_for_status()
                break
            except Exception as e:
                if attempt == 2:
                    raise e

        df = pd.read_csv(
            io.StringIO(resp.text),
            header=0,
            dtype=str,
            on_bad_lines="skip",
        )
        df.columns = [c.strip() for c in df.columns]

        # Cột: B(1)=Dep assign, D(3)=Task type, F(5)=Team, J(9)=Date complete, M(12)=Confirm
        COL_DEP = 1
        COL_TASK = 3
        COL_TEAM = 5
        COL_DONE = 9

        today_naive = today.replace(tzinfo=None)
        day0 = today_naive.date()
        day1 = (today_naive - timedelta(days=1)).date()
        day2 = (today_naive - timedelta(days=2)).date()
        day7 = (today_naive - timedelta(days=7))
        date_str = today.strftime("%d/%m/%Y")

        def parse_date(val):
            if pd.isna(val):
                return None
            val_str = str(val).strip()
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    return datetime.strptime(val_str.split()[0], fmt)
                except ValueError:
                    continue
            return None

        # Nhóm theo (dep, team, task_type) → {total, d0, d1, d2, d7, month}
        groups = {}
        for _, row in df.iterrows():
            if len(row) < 10:
                continue
            dep = str(row.iloc[COL_DEP]).strip() if not pd.isna(row.iloc[COL_DEP]) else ""
            if not dep or dep.lower() in ("", "nan", "dep assign", "sum"):
                continue
            task_type = str(row.iloc[COL_TASK]).strip() if not pd.isna(row.iloc[COL_TASK]) else ""
            if not task_type or task_type.lower() in ("nan", ""):
                continue

            # Team — thử cột F(5), fallback cột G(6)
            team = ""
            if len(row) > COL_TEAM and not pd.isna(row.iloc[COL_TEAM]):
                team = str(row.iloc[COL_TEAM]).strip()
            if (not team or team.lower() in ("nan", "")) and len(row) > 6 and not pd.isna(row.iloc[6]):
                team = str(row.iloc[6]).strip()
            if not team or team.lower() in ("nan", ""):
                team = "Office"

            j_date = parse_date(row.iloc[COL_DONE]) if len(row) > COL_DONE else None

            key = (dep, team, task_type)
            if key not in groups:
                groups[key] = {"total": 0, "d0": 0, "d1": 0, "d2": 0, "d7": 0, "month": 0}

            g = groups[key]
            g["total"] += 1

            if j_date is not None:
                jd = j_date.date()
                if jd == day0:
                    g["d0"] += 1
                elif jd == day1:
                    g["d1"] += 1
                elif jd == day2:
                    g["d2"] += 1
                if j_date >= day7:
                    g["d7"] += 1
                if jd.year == day0.year and jd.month == day0.month:
                    g["month"] += 1

        if not groups:
            return []

        # Sắp xếp và nhóm theo Dep → Team → Task type
        dep_data = {}
        for (dep, team, task_type), g in groups.items():
            if dep not in dep_data:
                dep_data[dep] = {}
            if team not in dep_data[dep]:
                dep_data[dep][team] = []
            dep_data[dep][team].append((task_type, g))

        # Build messages — mỗi Dep là 1 message
        messages = []
        for dep in sorted(dep_data.keys()):
            circle = DEP_CIRCLES.get(dep.lower().strip(), "▪️")
            lines = [f"{circle} {dep} {date_str}"]

            teams = dep_data[dep]
            for team in sorted(teams.keys()):
                lines.append(team)
                for task_type, g in sorted(teams[team], key=lambda x: x[0]):
                    progress = f"{g['d2']}/{g['d1']}/{g['d0']}"
                    lines.append(
                        f"{task_type} : total : {g['total']}  Progress 3 day: {progress}, "
                        f"7 day: {g['d7']}, Month: {g['month']}"
                    )
            messages.append("\n".join(lines))

        return messages
    except Exception as e:
        logger.warning(f"get_input_task_detail failed: {e}")
        return []

def build_asset_progress_summary(content: str) -> str:
    """
    Chèn dòng tổng hợp ngay SAU header section (vd: "CM 06/06/2026").
    Thêm chấm tròn màu cho mỗi Dep header.

    Input (cú pháp cũ):
      CM 06/06/2026
      Team 01
      Request Export material : total : 28  Progress 3 day: 0/0/0, 7 day: 0, Month: 0
      Team 02
      Request Export material : total : 14  Progress 3 day: 0/0/0, 7 day: 0, Month: 0
      ...

    Output:
      🟡 CM 06/06/2026
      📊 Tổng: Total:61 | 3day:0/0/0 | 7day:0 | Month:0
      Team 01
      Request Export material : total : 28  Progress 3 day: 0/0/0, 7 day: 0, Month: 0
      ...
    """
    # Chấm tròn màu cố định cho Dep header (Technical Dep report)
    DEP_CIRCLES = {
        "admin": "🔵", "asset": "🟢", "cm": "🟡", "fbb": "🟠",
        "finance": "🟣", "hr": "🔴", "m&e": "🟤", "manager": "⚪",
        "pm": "⚫", "transmission": "🔵", "construction": "🟠",
        "construction projects": "🟠", "noc": "⚫", "technical": "🔵",
    }
    # Pattern nhận biết dòng data có số liệu: "total : X  Progress 3 day: a/b/c, 7 day: d, Month: e"
    data_pat = re.compile(
        r'total\s*:\s*(\d+).*?3\s*day\s*:\s*(\d+)/(\d+)/(\d+).*?7\s*day\s*:\s*(\d+).*?Month\s*:\s*(\d+)',
        re.IGNORECASE,
    )
    # Pattern nhận biết header section: dòng có dạng "WordWord DD/MM/YYYY"
    header_pat = re.compile(
        r'^([A-Za-z&/]+(?:\s[A-Za-z&/]+)?)\s+\d{2}/\d{2}/\d{4}\s*$',
        re.MULTILINE,
    )

    lines = content.splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        hm = header_pat.match(line.strip())
        if hm:
            # Thêm chấm tròn màu cho header
            dep_name = hm.group(1).strip()
            circle = DEP_CIRCLES.get(dep_name.lower(), "")
            if circle:
                result.append(f"{circle} {line.strip()}")
            else:
                result.append(line)
            # Gom các dòng dữ liệu của section này (đến header tiếp theo hoặc hết)
            j = i + 1
            section_lines = []
            while j < len(lines):
                if header_pat.match(lines[j].strip()):
                    break
                section_lines.append(lines[j])
                j += 1
            # Tính tổng
            t_total = d3a = d3b = d3c = d7 = d_month = 0
            for sl in section_lines:
                m = data_pat.search(sl)
                if m:
                    t_total  += int(m.group(1))
                    d3a      += int(m.group(2))
                    d3b      += int(m.group(3))
                    d3c      += int(m.group(4))
                    d7       += int(m.group(5))
                    d_month  += int(m.group(6))
            if t_total > 0 or d7 > 0 or d_month > 0:
                result.append(
                    f"📊 Summary: Total:{t_total} | 3day:{d3a}/{d3b}/{d3c} | 7day:{d7} | Month:{d_month}"
                )
            # Thêm các dòng section vào kết quả
            result.extend(section_lines)
            i = j
        else:
            result.append(line)
            i += 1

    return "\n".join(result)
def parse_tl_metrics(text: str) -> dict:
    """
    Trích các chỉ số chính từ cột D của Team Leader để build bảng so sánh.
    Input: "Team leader 1 Rank: /4 => Close: /10.8% ..."
    """
    if not text:
        return {}

    def _num(pattern, default="?"):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    # Team number
    m_tl = re.search(r'Team\s*leader\s*(\d+)', text, re.IGNORECASE)
    team_num = m_tl.group(1) if m_tl else "?"

    rank       = _num(r'Rank:\s*/?([\d]+)')
    close_pct  = _num(r'Close:\s*/?([\d.]+)%')
    hit_target = "/LostTARGET" not in text

    wo_month   = _num(r'=\s*/?([\d]+)\s*WO Close')
    wo_7day    = _num(r'7day:\s*/?([\d]+)\s*Close')
    # 3Day: d2 /d1 /d0
    m_3d = re.search(r'3Day:\s*(\d+)\s*/?(\d+)\s*/?(\d+)', text)
    three_day  = f"{m_3d.group(1)}/{m_3d.group(2)}/{m_3d.group(3)}" if m_3d else "?/?/?"

    wo_remain  = _num(r'/?([\d]+)\s*WO Remain')
    overdue    = _num(r'/NOT\s*/Close:\s*/?([\d]+)')

    task_assign = _num(r'All Assign:\s*/?([\d]+)')
    task_close  = _num(r'All task Close:\s*/?([\d]+)')

    # Extract Target % from sheet text (e.g. /Target25%, /Target50%, /Target75%)
    m_target = re.search(r'/Target\s*(\d+)%', text, re.IGNORECASE)
    target_pct = float(m_target.group(1)) if m_target else 50.0
    warn_pct = round(target_pct * 0.6) if target_pct != 50 else 30.0

    # Phân loại màu sắc và icon trạng thái chuẩn theo đúng Target đọc được từ Sheet:
    # 🟢 >=Target%Hit (đạt target)
    # 🟡 >=Warn%     (gần đạt target)
    # 🔴 <Warn%Lost  (lost target)
    try:
        pct_val = float(close_pct)
    except Exception:
        pct_val = 0.0

    if pct_val >= target_pct:
        color = "🟢"
        tgt_icon = "✅"
    elif pct_val >= warn_pct:
        color = "🟡"
        tgt_icon = "🟡"
    else:
        color = "🔴"
        tgt_icon = "🛑"

    return {
        "team_num":   team_num,
        "rank":       rank,
        "close_pct":  close_pct,
        "target_pct": target_pct,
        "warn_pct":   warn_pct,
        "color":      color,
        "tgt_icon":   tgt_icon,
        "hit_target": hit_target,
        "wo_month":   wo_month,
        "wo_7day":    wo_7day,
        "three_day":  three_day,
        "wo_remain":  wo_remain,
        "overdue":    overdue,
        "task_assign": task_assign,
        "task_close":  task_close,
        "full_text":   text.strip(),
    }


def build_tl_comparison(metrics_list: list, now_str: str) -> str:
    """
    Tạo bảng so sánh TL từ danh sách metrics. Gửi vào CONTROL.
    Thứ tự: bảng tóm tắt đầu, sau đó chi tiết đầy đủ cột D từng TL.
    """
    if not metrics_list:
        return ""

    # Lấy Target % động từ dữ liệu Sheet (VD: 50%, 75%...)
    target_val = 50
    warn_val = 30
    for m in metrics_list:
        if m.get("target_pct"):
            target_val = int(m["target_pct"])
            warn_val = int(m.get("warn_pct", 30))
            break

    lines = [
        f"📋 4. Report — TL Comparison — {now_str}",
        f"📌 Target: {target_val}% WO Close",
        "━" * 22,
        # Header bảng
        f"{'T':<3} {'Rk':<4} {'Close%':<9} {'Mo':>4} {'7D':>4} {'3Day':>7} {'Rem':>5} {'OVD':>5} {'Task A/C':>9}",
        "─" * 52,
    ]

    for m in metrics_list:
        tgt = m.get("tgt_icon", "✅" if m["hit_target"] else "🛑")
        lines.append(
            f"{m['color']}T{m['team_num']:<2} "
            f"#{m['rank']:<3} "
            f"{m['close_pct']:>5}%{tgt} "
            f"{m['wo_month']:>4} "
            f"{m['wo_7day']:>4} "
            f"{m['three_day']:>7} "
            f"{m['wo_remain']:>5} "
            f"{m['overdue']:>5} "
            f"{m['task_assign']:>4}/{m['task_close']:<4}"
        )

    lines.append("─" * 52)
    lines.append(f"🟢 >={target_val}%Hit 🟡 >={warn_val}% 🔴 <{warn_val}%Lost")
    lines.append("━" * 22)

    # Chi tiết đầy đủ cột D từng TL
    lines.append("📝 Full Detail per TL:")
    for m in metrics_list:
        lines.append("─" * 22)
        lines.append(f"🟧 Team leader {m['team_num']}:")
        lines.append(m["full_text"])

    lines.append("━" * 22)
    return "\n".join(lines)


def parse_tl(text):
    """Legacy — giữ lại cho Team group report. Trả về full text của TL."""
    return text.strip() if text else ""


def parse_emp_metrics(text: str) -> dict:
    """
    Trích các chỉ số chính từ cột D của NV.
    Format compact gửi vào Team group: một dòng/NV với 🔺 prefix.

    Input: '--myt_aunglwin.phyo = Site:  /15 : TNI... <> Day /13...'
    Output dict: name_short, rank, site, wo_month, wo_7day, three_day,
                 wo_remain, overdue, task_assign, task_close, color
    """
    if not text:
        return {}

    def _num(pattern, default="?"):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    # Tên NV (trước "= Site:")
    m_name = re.search(r'^(\*?[^\n=]+?)\s*=\s*Site:', text.strip())
    raw_name = m_name.group(1).strip() if m_name else "?"

    # Rút gọn tên: chỉ bỏ "--" hoặc "*" đầu dòng, giữ nguyên phần còn lại
    # VD: "--myt_khantchaw.nyo" → "myt_khantchaw.nyo"
    #     "Khant Chaw Nyo-myt_naingmyo.htun" → giữ nguyên
    name_short = raw_name.lstrip("*-").strip()


    site      = _num(r'Site:\s*/?([\d]+)')
    rank      = _num(r'\brank:\s*/?([\d]+)')          # NV: lowercase 'rank'
    close_pct = _num(r'=?Close:\s*/?([\d.]+)%')       # NV: '=Close:'
    wo_month  = _num(r'=\s*/?([\d]+)\s*WO Close')     # giống TL
    wo_7day   = _num(r'7day:\s*/?([\d]+)\s*Close')
    wo_remain = _num(r'/?([\d]+)\s*WO Remain')
    overdue   = _num(r'/NOT\s*/Close:\s*/?([\d]+)')
    task_assign = _num(r'Task assign:\s*/?([\d]+)')    # NV: 'Task assign'
    task_close  = _num(r'Task Close Month:\s*/?([\d]+)')

    # 3Day WO (lấn xuất hiện đầu tiên = WO, không phải Task)
    m_3d = re.search(r'3Day:\s*(\d+)\s*/?(\d+)\s*/?(\d+)', text, re.IGNORECASE)
    three_day = f"{m_3d.group(1)}/{m_3d.group(2)}/{m_3d.group(3)}" if m_3d else "?/?/?"

    # Màu tam giác: dùng LostTARGET flag từ sheet
    if "/LostTARGET" in text:
        color = "🔺"  # tam giác đỏ — Lost Target
    elif "/HitTARGET" in text:
        color = "🔹"  # hình thỏ xành — Hit Target
    else:
        try:
            color = "🔹" if float(close_pct) >= 50 else "🔺"
        except Exception:
            color = "🔸"  # fallback

    return {
        "name_short":   name_short,
        "site":         site,
        "rank":         rank,
        "close_pct":    close_pct,
        "color":        color,
        "wo_month":     wo_month,
        "wo_7day":      wo_7day,
        "three_day":    three_day,
        "wo_remain":    wo_remain,
        "overdue":      overdue,
        "task_assign":  task_assign,
        "task_close":   task_close,
    }


def parse_emp(text):
    """
    Trích xuất format ngắn cho báo cáo Control.

    Input (cột D):
      --myt_aunglwin.phyo = Site:  /15 : 'TNI0201: 8KVA+...TNI0055 <> Day: 12 of the month= /1
      WO Close/ 7day: /1 Close => 3Day: 0 /0 /0 =>/23 WO Remain <=> rank: /23 =Close: /4%
      /TARGET50%  /LostTARGET=> /WO /Overdue /FOT /NOT /Close: /17  < + > Task assign: /6
      => Task Close Month: /0 => 3Day Close: 0/0/0 : TNI0035 , ... =>  M&E : 3/P: 0 ...

    Output:
      --myt_aunglwin.phyo = Site: /15 <> Day: 12 of the month= /1 WO Close/ 7day: /1 Close
      => 3Day: 0 /0 /0 =>/23 WO Remain <=> rank: /23 =Close: /4% /TARGET50% /LostTARGET=>
      /WO /Overdue /FOT /NOT /Close: /17 < + > Task assign: /6 => Task Close Month: /0
      => 3Day Close: 0/0/0
    """
    if not text:
        return ""
    text = text.strip()

    # Lấy tên (trước "= Site:")
    m_name = re.search(r'^(\*?[^=\n]+?)\s*=\s*Site:', text)
    if not m_name:
        return text
    name = m_name.group(1).strip()

    # Lấy số site (/15, /0, v.v.)
    m_site = re.search(r'Site:\s*(/?\d+)', text)
    site_num = m_site.group(1) if m_site else "?"

    # Lấy nội dung từ "<>" đến hết "3Day Close: X/X/X" — bỏ danh sách TNI và dep stats cuối
    m_body = re.search(r'(<>.*?3Day Close:\s*\d+/\d+/\d+)', text, re.DOTALL)
    if m_body:
        body = re.sub(r'\s+', ' ', m_body.group(1)).strip()
        return f"{name} = Site: {site_num} {body}"

    # Fallback: trả về tên + site
    return f"{name} = Site: {site_num}"


def format_employee_report(emp: dict, now_str: str, month_days: int) -> str:
    """
    Format báo cáo nhân viên:

    Htoo Aung-myt_tharhtoo.aung11: 7-day results: 0  M: 0 /26 - Site: 11 :
    <>Month 18day :0 /Close 7day: 0 <=> rank: 21 =Close: *0% <0/0/0>
    WO remain : 34 + Assign: 30 => Task Close Month: 0: 0/0/0
    Asset : 3/P: 0  CM : 5/P: 0  M&E : 11/P: 0
    """
    name       = emp.get("name", "")
    sys_name   = emp.get("sys_name", "")
    wo_remain  = emp.get("wo_remain", 0)
    site_rem   = emp.get("site_remain", 0)
    wo_total   = emp.get("wo_total", 0)
    mo_close   = emp.get("wo_month_close", 0)
    wk_close   = emp.get("wo_week_close", 0)
    wo_d0      = emp.get("wo_d0", 0)     # hôm nay
    wo_d1      = emp.get("wo_d1", 0)     # hôm qua
    wo_d2      = emp.get("wo_d2", 0)     # hôm kia
    assign_rem = emp.get("assign_remain", 0)
    assign_mo  = emp.get("assign_month_close", 0)
    close_pct  = emp.get("close_pct", 0)
    rank       = emp.get("rank", 0)
    dep_stats  = emp.get("dep_stats", {})

    # Dòng tiêu đề
    display_name = f"{name}-{sys_name}" if sys_name else name
    line1 = (
        f"*{display_name}*: 7-day results: {wk_close} "
        f" M: {mo_close} /{wo_total} - Site: {site_rem} :"
    )

    # Dòng tháng + rank + close%
    line2 = (
        f"<>Month {month_days}day :{mo_close} /Close 7day: {wk_close} "
        f"<=> rank: {rank} =Close: *{close_pct}% <{wo_d0}/{wo_d1}/{wo_d2}>"
    )

    # Dòng WO + Assign
    # Task Close Month: assign_mo: wo_d0/wo_d1/wo_d2 (tổng close ngày)
    line3 = (
        f"WO remain : {wo_remain} + Assign: {assign_rem} "
        f"=> Task Close Month: {assign_mo}: {wo_d0}/{wo_d1}/{wo_d2}"
    )

    # Dòng dep stats (NV format: "Asset : 3/P: 0")
    dep_parts = []
    for dep, st in dep_stats.items():
        remain = st.get("remain", 0)
        point  = st.get("point", 0)
        dep_parts.append(f"{dep} : {remain}/P: {point}")
    line4 = "  ".join(dep_parts) if dep_parts else ""

    lines = [line1, line2, line3]
    if line4:
        lines.append(line4)
    return "\n".join(lines)


def format_leader_report(ld: dict, now_str: str, month_days: int) -> str:
    """
    Format báo cáo Team Leader:

    Team leader 1: 3-Day Result: 11/0/0/0 <=> rank: 4 =Close: 36%
    WO remain : Month 18day :77/Close 7day: 26 <:>  5/2/2/40 + Assign: *60
    => Team leader task Close: 0  All Task Close: 1 : 0 : 0 : 0
    Asset : TL:6 /13 P:0  CM : TL:0 /14 P:0  M&E : TL:0 /7 P:0
    """
    name          = ld.get("name", "")
    team          = ld.get("team", "")
    member_count  = ld.get("member_count", 0)
    eod_today     = ld.get("eod_today", 0)     # số NV báo cáo hôm nay
    eod_d1        = ld.get("eod_d1", 0)
    eod_d2        = ld.get("eod_d2", 0)
    rank          = ld.get("rank", 0)
    close_pct     = ld.get("close_pct", 0)
    wo_remain     = ld.get("wo_remain", 0)
    mo_close      = ld.get("wo_month_close", 0)
    wk_close      = ld.get("wo_week_close", 0)
    wo_d0         = ld.get("wo_d0", 0)
    wo_d1         = ld.get("wo_d1", 0)
    wo_d2         = ld.get("wo_d2", 0)
    wo_total      = ld.get("wo_total", 0)
    assign_rem    = ld.get("assign_remain", 0)
    tl_close      = ld.get("tl_task_close", 0)
    all_close     = ld.get("all_task_close", [0, 0, 0, 0])
    dep_stats     = ld.get("dep_stats", {})

    # Dòng 1: tên team + EOD report + rank + close%
    line1 = (
        f"{name}: 3-Day Result: {member_count}/{eod_today}/{eod_d1}/{eod_d2} "
        f"<=> rank: {rank} =Close: {close_pct}%"
    )

    # Dòng 2: WO remain + month/week close + daily WO + assign
    all_close_str = " : ".join(str(x) for x in all_close)
    line2 = (
        f"WO remain : Month {month_days}day :{mo_close}/Close 7day: {wk_close} "
        f"<:>  {wo_d0}/{wo_d1}/{wo_d2}/{wo_total} + Assign: *{assign_rem}"
    )

    # Dòng 3: TL task close + All Task Close (4 kỳ tháng)
    line3 = (
        f"=> Team leader task Close: {tl_close}  "
        f"All Task Close: {all_close_str}*"
    )

    # Dòng dep stats (TL format: "Asset : TL:6 /13 P:0")
    dep_parts = []
    for dep, st in dep_stats.items():
        tl_count = st.get("tl_count", 0)
        total    = st.get("total", 0)
        point    = st.get("point", 0)
        dep_parts.append(f"{dep} : TL:{tl_count} /{total} P:{point}")
    line4 = "  ".join(dep_parts) if dep_parts else ""

    lines = [line1, line2, line3]
    if line4:
        lines.append(line4)
    return "\n".join(lines)


def build_summary_header(content: str) -> str:
    """
    (Legacy) Phân tích nội dung cột D và tạo dòng tổng hợp đầu tin nhắn.
    Dùng khi không có dữ liệu từ Apps Script (fallback).
    """
    lines = []
    blocks = re.split(r'\*<OTHER>\*', content)
    for block in blocks:
        name_m = re.search(r'\*([^*]+?)-myt_[^*]+\*:', block)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        d7_m = re.search(r'Close 7day:\s*(\d+)', block)
        d7 = d7_m.group(1) if d7_m else "?"
        month_m = re.search(r'Month \d+day\s*:(\d+)\s*/Close', block)
        month = month_m.group(1) if month_m else "?"
        d3_m = re.search(r'Close:\s*\*?\d+%?\*?\s*<(\d+)/(\d+)/(\d+)>', block)
        if d3_m:
            d3 = f"{d3_m.group(1)}/{d3_m.group(2)}/{d3_m.group(3)}"
        else:
            d3_fb = re.search(r'<(\d+)/(\d+)/(\d+)>', block)
            d3 = f"{d3_fb.group(1)}/{d3_fb.group(2)}/{d3_fb.group(3)}" if d3_fb else "?/?"
        lines.append(f"  • {name}: 3day:{d3} | 7day:{d7} | Month:{month}")

    if not lines:
        return ""
    return "📊 WO hoàn thành:\n" + "\n".join(lines)


async def send_msg(bot, cid, text, label="", parse_mode=None, reply_to=None):
    """Send message, handle >4096 char limit.
    Splits by newlines first, then by MAX chars if a single line is too long.
    """
    MAX = 4000

    def chunk_text(t):
        """Split text into parts <= MAX chars, preserving newlines where possible."""
        parts, current = [], ""
        for line in t.split("\n"):
            # If a single line itself is too long, break it by char count
            while len(line) > MAX:
                segment = line[:MAX]
                if current:
                    parts.append(current)
                    current = ""
                parts.append(segment)
                line = line[MAX:]
            # Normal line
            if len(current) + len(line) + 1 > MAX:
                parts.append(current)
                current = line
            else:
                current += ("\n" if current else "") + line
        if current:
            parts.append(current)
        return parts

    kwargs = {"chat_id": cid, "text": text}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    if reply_to:
        kwargs["reply_to_message_id"] = reply_to

    msg_ids = []  # Collect message_ids from sent messages
    try:
        if len(text) <= MAX:
            sent = await bot.send_message(**kwargs)
            msg_ids.append(sent.message_id)
        else:
            for p in chunk_text(text):
                if p.strip():
                    kw = {"chat_id": cid, "text": p}
                    if parse_mode:
                        kw["parse_mode"] = parse_mode
                    if reply_to:
                        kw["reply_to_message_id"] = reply_to
                    sent = await bot.send_message(**kw)
                    msg_ids.append(sent.message_id)
                    await asyncio.sleep(0.3)
        logger.info(f"✅ {label} → {cid}")
        return True, msg_ids
    except Exception as e:
        logger.error(f"❌ {label} → {cid}: {e}")
        return False, msg_ids


async def main():
    now = datetime.now(TZ_MM)
    now_str = now.strftime("%d/%m/%Y %H:%M")
    logger.info(f"🚀 Cron send start – {now_str}")

    # ── 1. Read full sheet ──
    resp = requests.get(SHEET_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str, on_bad_lines="skip")
    logger.info(f"Sheet: {len(df)} total rows (including headers)")

    # ── 2. Collect team leader content + employee content ──
    team_leader_content = []
    all_rows = []  # (sheet_row, content, chat_id)

    for idx, row in df.iterrows():
        sheet_row = idx + 1  # 1-indexed
        if sheet_row <= HEADER_ROWS:
            continue  # skip headers

        content = safe(row, COL_D)
        cid_raw = safe(row, COL_E)
        col_c = safe(row, COL_C)
        col_b = safe(row, COL_B)

        cid = cid_raw[:-2] if cid_raw.endswith(".0") else cid_raw

        # Collect team leader content for management report
        if col_c and "team leader" in col_c.lower() and content:
            team_name = safe(row, COL_A) or col_b or "Unknown"
            team_leader_content.append({"team": team_name, "name": col_b, "content": content})

        is_team_row = 4 <= sheet_row <= 59
        is_tech_row = 75 <= sheet_row <= 87
        if not is_team_row and not is_tech_row and (not cid or cid == "-" or not cid.lstrip("-").isdigit()):
            continue

        all_rows.append((sheet_row, content, cid, col_c, safe(row, COL_A), col_b))

    # ── 3. Get asset stats ──
    asset_data = get_asset_stats()
    asset_msg = build_asset_msg(now_str, asset_data)

    # ── 4. Get search/report stats ──
    report_data = get_report_data()
    search_msg = build_search_summary(now_str, report_data)

    # DEBUG: check searchStats
    ss_keys = list(report_data.get("searchStats", {}).keys())
    logger.info(f"DEBUG searchStats keys ({len(ss_keys)}): {ss_keys[:5]}")

    # ── 4b. Staff sheet: NV chưa có ID / chưa vào Group ──
    no_id_members = get_no_id_members(bot_token=SEND_BOT_TOKEN or "")
    logger.info(f"Staff check: {sum(len(v.get('no_id',[]))+len(v.get('not_in_group',[])) for v in no_id_members.values())} issue(s) found")
    month_days = report_data.get("month_days", 0)
    leaders_data = report_data.get("leaders", [])

    # ── 5. Fetch Input Task summary + detail ──
    input_task_summary = get_input_task_summary(now)
    logger.info("Input task summary: OK" if input_task_summary else "Input task summary: empty")
    input_task_detail = get_input_task_detail(now)
    logger.info(f"Input task detail: {len(input_task_detail)} dept messages")

    # ── 5a. Fetch Note from Config G1:G5 ──
    note_text = get_note_from_sheet()
    if note_text:
        logger.info("Note fetched successfully from Config sheet")
    else:
        logger.info("No Note found or error fetching Note")

    # ── 5b. Fetch Control Note from Config H1:H3 ──
    control_note = get_control_note_from_sheet()
    if control_note:
        logger.info("Control Note fetched successfully from Config sheet")
    else:
        logger.info("No Control Note found or error fetching Control Note")

    # ── 5.5 Team→employees mapping (dùng khi gửi riêng lẻ cho TL) ──
    TEAM_BY_NUMBER = {
        1: "MYT_TNI_TEAM01_Dawei",
        2: "MYT_TNI_TEAM02_Myeik",
        3: "MYT_TNI_TEAM03_Bokpyin",
        4: "MYT_TNI_TEAM04_Kawthoung",
        5: "MYT_TNI_TEAM02_Myeik",  # Team 5 nhập chung Team 2 (Myeik)
    }
    team_to_employees: dict = {}
    for _e in report_data.get("employees", []):
        team_to_employees.setdefault(_e.get("team", ""), []).append(_e)

    # ── 6. Build management report: TL summaries + Technical Dept only ──
    # BOD/Manager chỉ nhận TL Reports + Technical Dept
    mgmt_parts = [
        f"📋 4. Report — Daily EOD Task & Stats — Summary",
        f"📅 {now_str}",
        f"📌 Today's EOD summary of tasks completed, close rate, rank, asset and search stats.",
        "━━━━━━━━━━━━━━━━━━━━"
    ]
    # search_msg và asset_msg gửi KÈM với mgmt_report
    if search_msg:
        mgmt_parts.append("━" * 20)
        mgmt_parts.append(search_msg)
    if asset_msg:
        mgmt_parts.append("━" * 20)
        mgmt_parts.append(asset_msg)
    # CONTROL NOTE đã được bỏ khỏi tin bot và phát riêng bằng @phongha79
    mgmt_report = "\n".join(mgmt_parts)

    # Chat ID nhóm "5 TNI TECHNICA DEP CONTROL SITE"
    CONTROL_CHAT_ID = "-5251698940"

    # ── 7. Send messages ──
    ok = fail = 0

    # Reverse mapping GID → team key (dùng cho asset lookup)
    GID_TO_TEAM = {v: k for k, v in TEAM_GROUPS.items()}

    groups = {}  # token -> [(sheet_row, message, cid, label)]
    team_messages = {}  # target_gid -> list of (prefix, name, content, is_tl)
    tech_messages = []  # list of (name, content) for tech dept

    def get_target_group(team_str: str):
        if not team_str: return None
        ts = team_str.upper()
        if "TEAM01" in ts or "TEAM 1" in ts or "TEAM1" in ts: return TELEGRAM_GROUPS["T1"]
        if "TEAM02" in ts or "TEAM 2" in ts or "TEAM2" in ts or "TEAM05" in ts or "TEAM 5" in ts or "TEAM5" in ts: return TELEGRAM_GROUPS["T2"]
        if "TEAM03" in ts or "TEAM 3" in ts or "TEAM3" in ts: return TELEGRAM_GROUPS["T3"]
        if "TEAM04" in ts or "TEAM 4" in ts or "TEAM4" in ts: return TELEGRAM_GROUPS["T4"]
        return None

    for sheet_row, content, cid, col_c, col_a_val, col_b in all_rows:
        # ── 2 điều kiện bắt buộc (rows 4-59): Cột A có tên team VÀ Cột D có nội dung ──
        if 4 <= sheet_row <= 59:
            if not col_a_val:
                logger.debug(f"  Skip row{sheet_row}: Cột A trống (không có tên team)")
                continue
            if not content:
                logger.debug(f"  Skip row{sheet_row}: Cột D trống (không có nội dung)")
                continue

        # ── Rows 4-59: Gom FT + TL vào Group Team ──
        if 4 <= sheet_row <= 59:
            is_tl = 33 <= sheet_row <= 59 and bool(col_c and "team leader" in col_c.lower())

            if is_tl:
                # Team Leader (rows 33-59): xác định team từ SỐ trong Cột C
                # Cột C = "Team leader 1" / "Team leader 2" / ...
                m_tl = re.search(r'team\s*leader\s*(\d+)', col_c, re.IGNORECASE)
                tl_num = int(m_tl.group(1)) if m_tl else 0
                team_val = TEAM_BY_NUMBER.get(tl_num, col_a_val)
            else:
                # Nhân viên (rows 4-32): xác định team từ Cột A
                team_val = col_a_val

            target_gid = get_target_group(team_val)
            if target_gid:
                if is_tl:
                    # TL: dùng col_c (‘Team leader N’) — cần để xác định team
                    name = col_c or col_b or f"TL row{sheet_row}"
                else:
                    # NV: mỗi dòng sheet = 1 người — dùng row_index làm key duy nhất
                    # Không cần col_c, chỉ cần col_A + col_D có nội dung
                    name = f"nv_{sheet_row}"
                team_messages.setdefault(target_gid, []).append(
                    ("👑" if is_tl else "👤", name, content, is_tl)
                )
            continue

        # ── Rows 60-74: BOD/Management — KHÔNG gửi riêng, xem trên Group ──
        if 60 <= sheet_row <= 74:
            logger.debug(f"  Skip row{sheet_row}: BOD xem trên Group CONTROL SITE")
            continue

        # ── Rows 75-87: Technical Dept — Gộp lại gửi vào CONTROL SITE ──
        if 75 <= sheet_row <= 87:
            if content:
                name = col_b or col_c or f"NV row{sheet_row}"
                tech_messages.append((name, content))
            continue

    # ── 7a. Gộp tin nhắn 4 Team → Báo cáo Consolidated gửi vào Control & Gửi riêng từng Team ──
    if SEND_BOT_TOKEN:
        t_names = {
            "MYT_TNI_TEAM01_Dawei": "Team 1 Dawei",
            "MYT_TNI_TEAM02_Myeik": "Team 2 Myeik",
            "MYT_TNI_TEAM03_Bokpyin": "Team 3 Bokpyin",
            "MYT_TNI_TEAM04_Kawthoung": "Team 4 Kawthoung",
        }
        
        # Dict thu thập metrics từng TL theo thứ tự Team 1-4
        all_tl_metrics = []   # list[dict] — có thể nhiều TL cùng team (Team 5 ⇒ Team 2)

        # Sắp xếp theo thứ tự Team 1 -> Team 4
        ordered_teams = [
            "MYT_TNI_TEAM01_Dawei",
            "MYT_TNI_TEAM02_Myeik",
            "MYT_TNI_TEAM03_Bokpyin",
            "MYT_TNI_TEAM04_Kawthoung"
        ]

        for team_key in ordered_teams:
            gid = TEAM_GROUPS.get(team_key)
            if not gid:
                continue
            members = team_messages.get(gid, [])
            if not members:
                continue

            t_name = t_names.get(team_key, team_key)
            tl_list = [(p, n, c) for p, n, c, is_tl in members if is_tl]
            ft_list = [(p, n, c) for p, n, c, is_tl in members if not is_tl]

            # Control: chỉ TL, thu thập metrics + full col D
            for prefix, name, content in tl_list:
                if content:
                    m = parse_tl_metrics(content)
                    if m:
                        all_tl_metrics.append(m)

            # ── 2. Tạo báo cáo chi tiết gửi riêng vào từng nhóm Team (giữ nguyên cột D đầy đủ) ──
            team_lines_indiv = [
                f"📋 4. Report — Daily EOD Task & Stats — {t_name}",
                f"📅 {now_str}",
                f"📌 Today's EOD summary of tasks completed, close rate, rank, asset and search stats.",
                "━━━━━━━━━━━━━━━━━━━━"
            ]
            # Note sẽ được gửi riêng dưới tên @phongha79 (Telethon reply) sau khi pin Report 4
            # TL đã có đầy đủ trong Report 4b — không lặp lại ở Report 4

            # NV: parse_emp_metrics → compact 1 dòng với 🔺 prefix
            # Không dedup — mỗi dòng sheet = 1 người (name = nv_ROW — luôn unique)
            emp_rows = []
            for prefix, name, content in ft_list:
                if content:
                    m = parse_emp_metrics(content)
                    if m:
                        emp_rows.append(m)

            if emp_rows:
                team_lines_indiv.append("─" * 20)
                team_lines_indiv.append("👷 FT Staff Summary:")
                # Header gợi nhớ
                team_lines_indiv.append("Name | Rk | Site | Mo | 7D | 3Day | OVD | Task")
                team_lines_indiv.append("─" * 38)
                for em in emp_rows:
                    team_lines_indiv.append(
                        f"{em['color']} {em['name_short']}: "
                        f"Rk/{em['rank']} Site/{em['site']} "
                        f"Mo/{em['wo_month']} 7D/{em['wo_7day']} "
                        f"3D:{em['three_day']} "
                        f"OVD/{em['overdue']} "
                        f"Task:{em['task_assign']}/{em['task_close']}"
                    )

            # Thêm thống kê Asset và Search riêng cho từng Team
            team_asset = build_team_asset_section(team_key, asset_data)
            team_search = build_team_search_section(team_key, report_data, now_str, no_id_members)
            tl_search = build_tl_search_section(team_key, report_data, no_id_members)
            no_search = build_no_search_list(team_key, report_data, no_id_members)


            if team_asset or team_search or tl_search or no_search:
                team_lines_indiv.append("━━━━━━━━━━━━━━━━━━━━")
            if team_asset:
                team_lines_indiv.append(team_asset)
            if team_asset and (team_search or tl_search or no_search):
                team_lines_indiv.append("────────────────────")
            if team_search:
                team_lines_indiv.append(team_search)
            if tl_search:
                team_lines_indiv.append(tl_search)
            if no_search:
                team_lines_indiv.append(no_search)

            # NOTE đã hiển thị ở đầu message — không lặp lại cuối

            team_lines_indiv.append("━━━━━━━━━━━━━━━━━━━━")
            team_lines_indiv.append(f"👥 Total: {len(members)} members")

            team_msg = "\n".join(team_lines_indiv)
            groups.setdefault(SEND_BOT_TOKEN, []).append(
                (0, team_msg, str(gid), "TEAM_GROUP")
            )

            # ── Message 2: Nguyên nội dung cột D (gửi sau bản phân tích) ──
            full_lines = [
                f"📓 4b. Full Report — {t_name}",
                f"📅 {now_str}",
                "━" * 22,
            ]
            # TL full col D
            for prefix, name, content in tl_list:
                if content:
                    full_lines.append(f"🟧 {content}")
                    full_lines.append("─" * 18)
            # NV full col D — không dedup, thêm màu đầu dòng theo LostTARGET
            for prefix, name, content in ft_list:
                if content:
                    nv_color = "🔴" if "/LostTARGET" in content else "🟢"

                    full_lines.append(f"{nv_color} {content}")
                    full_lines.append("─" * 18)
            full_lines.append("━" * 22)

            full_msg = "\n".join(full_lines)
            groups.setdefault(SEND_BOT_TOKEN, []).append(
                (0, full_msg, str(gid), "TEAM_GROUP_FULL")
            )
        # Build và gửi bảng so sánh TL vào CONTROL
        grp_msg = build_tl_comparison(all_tl_metrics, now_str)
        if grp_msg:
            groups.setdefault(SEND_BOT_TOKEN, []).append(
                (0, grp_msg, CONTROL_CHAT_ID, "CONSOLIDATED_EOD")
            )

    # ── 7b. Gộp Tech Dept → Group CONTROL SITE ──
    if (tech_messages or input_task_summary) and SEND_BOT_TOKEN:
        tech_lines = [
            f"📋 1. Report — Technical Dept Task Progress",
            f"📅 {now_str}",
            "━" * 22,
        ]
        if input_task_summary:
            tech_lines.append(input_task_summary)
            tech_lines.append("─" * 22)

        for i, (name, content) in enumerate(tech_messages):
            dept_icon = EMP_ICONS[i % len(EMP_ICONS)]  # Vuông màu cố định theo dept
            tech_lines.append(f"\n{dept_icon} 【{name}】")
            tech_lines.append(content)

        tech_lines.append("\n" + "━" * 22)
        tech_lines.append(f"👥 Total: {len(tech_messages)} members")

        tech_msg = "\n".join(tech_lines)
        groups.setdefault(SEND_BOT_TOKEN, []).append(
            (0, tech_msg, CONTROL_CHAT_ID, "TECH_GROUP")
        )

    # ── 7c. Gửi Input Task Detail (chi tiết Dep→Team→TaskType) → CONTROL ──
    if input_task_detail and SEND_BOT_TOKEN:
        full_detail = "\n\n".join(input_task_detail)
        detail_msg = (
            f"📋 8. Report — Technical Dep Assign to Team\n"
            f"📅 {now_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{full_detail}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Total: {len(input_task_detail)} departments"
        )
        groups.setdefault(SEND_BOT_TOKEN, []).append(
            (0, detail_msg, CONTROL_CHAT_ID, "TECHDEP_DETAIL")
        )

    # ── 7d. Gửi STANDALONE BÁO CÁO 3.1 Asset progress for material → CONTROL & TEAMS ──
    if asset_msg and SEND_BOT_TOKEN:
        logger.info("[Cron] Queuing 3.1 Asset progress for material report...")
        # 1. Bắn tin tổng hợp 3.1 vào CONTROL_CHAT_ID (-5251698940)
        groups.setdefault(SEND_BOT_TOKEN, []).append(
            (0, asset_msg, CONTROL_CHAT_ID, "ASSET_PROGRESS_31")
        )
        # 2. Bắn tin chi tiết cho từng Team (T1, T2, T3, T4)
        for gid, team_key in GID_TO_TEAM.items():
            team_asset_msg = build_team_asset_msg(team_key, now_str, asset_data)
            if team_asset_msg:
                groups.setdefault(SEND_BOT_TOKEN, []).append(
                    (0, team_asset_msg, str(gid), "TEAM_ASSET_PROGRESS_31")
                )

    # ── Mapping chat_id → GAS key để delete-old / save-new ──
    CHATID_TO_KEY = {
        str(TELEGRAM_GROUPS["T1"]): "CRON_TEAM_T1",
        str(TELEGRAM_GROUPS["T2"]): "CRON_TEAM_T2",
        str(TELEGRAM_GROUPS["T3"]): "CRON_TEAM_T3",
        str(TELEGRAM_GROUPS["T4"]): "CRON_TEAM_T4",
    }
    # Key riêng cho Full Report (tin thứ 2 mỗi team)
    CHATID_TO_KEY_FULL = {
        str(TELEGRAM_GROUPS["T1"]): "CRON_TEAM_T1_FULL",
        str(TELEGRAM_GROUPS["T2"]): "CRON_TEAM_T2_FULL",
        str(TELEGRAM_GROUPS["T3"]): "CRON_TEAM_T3_FULL",
        str(TELEGRAM_GROUPS["T4"]): "CRON_TEAM_T4_FULL",
    }

    # ── Delete old messages theo tiêu đề (Telethon) + fallback GAS msg_id ──
    # Telethon scan lịch sử chat → xóa TẤT CẢ tin cũ cùng tiêu đề
    # Fallback: GAS msg_id (xóa tin liền trước nếu Telethon không khả dụng)
    if SEND_BOT_TOKEN and TELEGRAM_SESSION and TELEGRAM_API_ID:
        # Tiêu đề từng loại tin → map (chat_id, title_prefix)
        delete_tasks = []
        for del_cid in CHATID_TO_KEY.keys():
            delete_tasks.append((del_cid, "📋 4. Report — Daily EOD Task & Stats"))
            delete_tasks.append((del_cid, "📓 4b. Full Report"))
        delete_tasks += [
            (str(CONTROL_CHAT_ID), "📋 1. Report — Technical Dept Task Progress"),
            (str(CONTROL_CHAT_ID), "📋 8. Report — Technical Dep Assign to Team"),
            (str(CONTROL_CHAT_ID), "📋 4. Report — TL Comparison"),
            (str(CONTROL_CHAT_ID), "📋 1. BOD"),   # BOD report nếu có
        ]
        try:
            async with TelegramClient(
                StringSession(TELEGRAM_SESSION), TELEGRAM_API_ID, TELEGRAM_API_HASH
            ) as tg_client:
                logger.info("🗑️ Delete old messages by title (Telethon)...")
                for del_cid, title_pfx in delete_tasks:
                    await delete_by_title_telethon(tg_client, SEND_BOT_TOKEN, del_cid, title_pfx)
        except Exception as tg_err:
            logger.warning(f"Telethon delete lỗi, fallback GAS: {tg_err}")
            # Fallback: GAS msg_id delete
            if APPS_SCRIPT_URL:
                for del_cid, del_key in CHATID_TO_KEY.items():
                    delete_old_messages_bot(SEND_BOT_TOKEN, del_cid, APPS_SCRIPT_URL, del_key)
                for del_cid, del_key in CHATID_TO_KEY_FULL.items():
                    delete_old_messages_bot(SEND_BOT_TOKEN, del_cid, APPS_SCRIPT_URL, del_key)
                delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, "CRON_TECHDEP_CONTROL")
                delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, "CRON_TECHDEP_DETAIL")
                delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, "CRON_EOD_CONTROL")
    elif APPS_SCRIPT_URL and SEND_BOT_TOKEN:
        # Fallback nếu không có Telethon session
        for del_cid, del_key in CHATID_TO_KEY.items():
            delete_old_messages_bot(SEND_BOT_TOKEN, del_cid, APPS_SCRIPT_URL, del_key)
        for del_cid, del_key in CHATID_TO_KEY_FULL.items():
            delete_old_messages_bot(SEND_BOT_TOKEN, del_cid, APPS_SCRIPT_URL, del_key)
        delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, "CRON_TECHDEP_CONTROL")
        delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, "CRON_TECHDEP_DETAIL")
        delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, "CRON_EOD_CONTROL")


    # ── Gửi tất cả messages ──
    collected_msgids = {}      # gas_key → list[int]
    pinned_report4_msgids = {}  # str(chat_id) → msg_id — dùng để Telethon reply Note
    for token, items in groups.items():
        bot_name = items[0][3] if items else "BOT"
        logger.info(f"--- {bot_name}: {len(items)} messages ---")
        async with Bot(token=token) as bot:
            for sheet_row, msg, cid, label in items:
                result, msg_ids = await send_msg(bot, cid, msg, f"{label} row{sheet_row}")
                if result:
                    ok += 1
                    # Thu thập msg_id của bản tin 4b/4 để tài khoản @phongha79 reply Note (không gọi pin_chat_message để tránh thông báo hệ thống)
                    if msg_ids and ("4b. Full Report" in msg or "4b." in msg or "4. Report" in msg or "Daily EOD Task" in msg):
                        pinned_report4_msgids[str(cid)] = msg_ids[0]  # collect for Note reply

                    # Xác định GAS key từ label + chat_id
                    if label == "TECH_GROUP":
                        gas_key = "CRON_TECHDEP_CONTROL"
                    elif label == "TECHDEP_DETAIL":
                        gas_key = "CRON_TECHDEP_DETAIL"
                    elif label == "CONSOLIDATED_EOD":
                        gas_key = "CRON_EOD_CONTROL"
                    elif label == "TEAM_GROUP_FULL":
                        gas_key = CHATID_TO_KEY_FULL.get(str(cid), "")
                    else:
                        gas_key = CHATID_TO_KEY.get(str(cid), "")
                    if gas_key and msg_ids:
                        collected_msgids.setdefault(gas_key, []).extend(msg_ids)
                else:
                    fail += 1
                await asyncio.sleep(0.4)

    # ── Save msg_ids mới vào GAS ──
    if APPS_SCRIPT_URL:
        for gas_key, ids in collected_msgids.items():
            save_msgids(APPS_SCRIPT_URL, gas_key, ids)

    logger.info(f"📊 Done: ✅{ok} | ❌{fail}")

    # ── 7d. Gửi NOTE reply dưới tên user @phongha79 (Telethon) ──
    # BẮT BỘC gửi bằng tài khoản user @phongha79 để Telegram API (GetMessageReadParticipantsRequest)
    # đếm được danh sách người đọc cho Report 6 (daily_read_report.py). Tin nhắn từ Bot KHÔNG đếm được người đọc!
    if control_note and TELEGRAM_SESSION and TELEGRAM_API_ID and pinned_report4_msgids:
        try:
            async with TelegramClient(
                StringSession(TELEGRAM_SESSION), TELEGRAM_API_ID, TELEGRAM_API_HASH
            ) as tg_note_client:
                logger.info(f"📝 Gửi Note reply dưới tên user @phongha79 (Telethon) → {len(pinned_report4_msgids)} nhóm...")
                for cid_str, reply_to_id in pinned_report4_msgids.items():
                    try:
                        await tg_note_client.send_message(
                            entity=int(cid_str),
                            message=control_note,
                            reply_to=reply_to_id
                        )
                        logger.info(f"  ✅ Note reply (@phongha79) → {cid_str} (reply_to msg_id: {reply_to_id})")
                        await asyncio.sleep(0.5)
                    except Exception as note_send_err:
                        logger.error(f"  ❌ Note reply (@phongha79) thất bại → {cid_str}: {note_send_err}")
        except Exception as note_client_err:
            logger.error(f"❌ Telethon Note client lỗi: {note_client_err}")
    elif not TELEGRAM_SESSION:
        logger.info("⚠️ TELEGRAM_SESSION not set — skip Note reply (must be sent by Telethon user @phongha79 for Report 6 read tracking)")
    elif not control_note:
        logger.info("No control_note — skip Note reply")
    elif not pinned_report4_msgids:
        logger.info("No pinned Report 4/4b msg_ids — skip Note reply")

    # ── 8. Xóa các tin nhắn asset cũ lẻ loi ở CONTROL SITE & các Team ──
    if SEND_BOT_TOKEN and APPS_SCRIPT_URL:
        logger.info("--- Xóa các tin nhắn asset cũ ---")
        try:
            delete_old_messages_bot(SEND_BOT_TOKEN, -5251698940, APPS_SCRIPT_URL, "CRON_ASSET_CONTROL")
            ASSET_DELETE_RECIPIENTS = {
                "CRON_ASSET_T1": TELEGRAM_GROUPS["T1"],
                "CRON_ASSET_T2": TELEGRAM_GROUPS["T2"],
                "CRON_ASSET_T3": TELEGRAM_GROUPS["T3"],
                "CRON_ASSET_T4": TELEGRAM_GROUPS["T4"],
            }
            for key, cid in ASSET_DELETE_RECIPIENTS.items():
                delete_old_messages_bot(SEND_BOT_TOKEN, cid, APPS_SCRIPT_URL, key)
        except Exception as e:
            logger.error(f"❌ Xóa asset stats cũ thất bại: {e}")

    if mgmt_report and SEND_BOT_TOKEN:
        logger.info("--- Gửi mgmt_report (tổng hợp TL) → CONTROL SITE (-5251698940) ---")
        if APPS_SCRIPT_URL:
            delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, "CRON_MGMT_CONTROL")
        try:
            async with Bot(token=SEND_BOT_TOKEN) as ctrl_bot2:
                result, msg_ids = await send_msg(ctrl_bot2, CONTROL_CHAT_ID, mgmt_report, "CONTROL-mgmt")
                if result and msg_ids and APPS_SCRIPT_URL:
                    save_msgids(APPS_SCRIPT_URL, "CRON_MGMT_CONTROL", msg_ids)
            logger.info("✅ mgmt_report → CONTROL SITE")
        except Exception as e:
            logger.error(f"❌ mgmt_report → CONTROL SITE: {e}")



if __name__ == "__main__":
    asyncio.run(main())

