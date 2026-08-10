"""
Vercel webhook handler — TNI Search Bot + Daily Report
Bot: @SEARCHTNITASKWOBOT
URL: https://tni-bot.vercel.app/api/search_bot

Chức năng:
  - TNI lookup: gõ mã TNI → tra Site/Task/WO
  - Daily report: tin nhắn có chữ 'daily' → lưu vào Sheet
  - Ảnh: gửi kèm báo cáo → lưu Drive qua GAS
  - /daily → gửi mẫu báo cáo
"""
import os, re, io, json, html, time, asyncio, logging, requests, threading, sys
import pandas as pd
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

# ── SSOT Engine Import ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from tni_search_core import classify_query, is_duplicate_search
except ImportError:
    try:
        from api.tni_search_core import classify_query, is_duplicate_search
    except ImportError:
        classify_query = None
        is_duplicate_search = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
BOT_VERSION = "v4.0"

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN                 = os.environ.get("TELEGRAM_TOKEN", "").strip().strip("\ufeff")
TELEGRAM_SECRET_TOKEN = os.environ.get("TELEGRAM_SECRET_TOKEN", "").strip().strip("\ufeff")
DAILY_APPS_SCRIPT_URL = os.environ.get("DAILY_APPS_SCRIPT_URL", "").strip().strip("\ufeff")
APPS_SCRIPT_URL       = os.environ.get("APPS_SCRIPT_URL", "").strip().strip("\ufeff")
SPREADSHEET_ID        = os.environ.get("SPREADSHEET_ID", "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8").strip().strip("\ufeff")
SD_SPREADSHEET_ID     = "1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow"
BASE_URL              = (
    f"https://docs.google.com/spreadsheets/d/"
    f"{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid="
)
SD_BASE_URL           = (
    f"https://docs.google.com/spreadsheets/d/"
    f"{SD_SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid="
)
GID_SITE       = "1095689918"
GID_TASK       = "1755404595"
GID_WO         = "1429089905"
GID_INFO       = "171059303"   # Tab: Name Site / Site / Cable / Gpon / DIA
GID_TEAM_SUM   = "893574714"   # Tab: Tên Sum WO (Team Leader search)
GID_TL_WAITCD  = "1110926116"  # Tab: Team leader Wait CD + Not Close
GID_SITE_CLEAR = "610944071"   # Tab: Search Site Clear
GID_STAFF      = "1684930643"  # Tab: Staff — col A=Telegram ID, row 1=headers (mysite/mycable/...)

TZ_MM    = timezone(timedelta(hours=6, minutes=30))   # Myanmar UTC+6:30
MAX_LEN  = 4096
TG_API   = f"https://api.telegram.org/bot{TOKEN if TOKEN else 'MISSING'}"

# ── Daily fields cache ─────────────────────────────────────────────────────────
DAILY_FIELDS_DEFAULT = [
    "Daily result",
    "Transportation Used",
    "Full Name",
    "Detail WO",
    "Detail task",
    "Name Site rescue",
    "Name Cell rescue",
    "Resuce Cable",
    "Name and detail Site repair alarm",
    "Name Site follow partner refuel",
    "Other task",
    "Name and detail Site go busines trip start go",
    "Name and detail Site go busines trip end go",
    "Km moto bike start",
    "Km moto bike the end",
]
DAILY_FIELDS_TTL = 600
_daily_fields: list = []
_daily_fields_ts: float = 0.0

def send_daily_template(chat_id: int) -> None:
    now_mm = datetime.now(TZ_MM)
    date_str = now_mm.strftime("%d/%m/%Y")
    template = (
        f"Daily result: {date_str}\n"
        f"Transportation Used:\n"
        f"Full Name:\n"
        f"Detail WO:\n"
        f"Detail task:\n"
        f"Name Site rescue:\n"
        f"Name Cell rescue:\n"
        f"Resuce Cable:\n"
        f"Name and detail Site repair alarm:\n"
        f"Name Site follow partner refuel:\n"
        f"Other task:\n"
        f"Name and detail Site go busines trip start go:\n"
        f"Name and detail Site go busines trip end go:\n"
        f"Km moto bike start:\n"
        f"Km moto bike the end:"
    )
    tg_send(chat_id, template)

# ── Sheet cache ────────────────────────────────────────────────────────────────
_cache_ts: float = 0.0
CACHE_TTL: float = 120.0

# ── split_messages PHẢI đứng trước tg_send ────────────────────────────────────
def split_messages(text: str) -> list:
    """Tách text thành các chunk ≤ MAX_LEN ký tự, cắt theo dòng."""
    chunks, current = [], ""
    for line in text.split("\n"):
        candidate = (current + "\n" + line) if current else line
        if len(candidate) <= MAX_LEN:
            current = candidate
        else:
            if current:
                chunks.append(current)
            while len(line) > MAX_LEN:
                chunks.append(line[:MAX_LEN])
                line = line[MAX_LEN:]
            current = line
    if current:
        chunks.append(current)
    return chunks or [""]

# ── Telegram helpers ───────────────────────────────────────────────────────────
def tg_send(chat_id, text, parse_mode="HTML"):
    """Gửi tin nhắn Telegram, tự chia chunk nếu quá dài."""
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN missing")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for chunk in split_messages(text):
        try:
            r = requests.post(url, json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }, timeout=30)
            if not r.ok:
                logger.error(f"tg_send error: {r.text[:200]}")
        except Exception as ex:
            logger.error(f"tg_send exception: {ex}")

def tg_get_file(file_id: str) -> str | None:
    """Lấy file_path từ Telegram file_id."""
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TOKEN}/getFile",
            params={"file_id": file_id}, timeout=10
        ).json()
        return r.get("result", {}).get("file_path")
    except Exception as ex:
        logger.error(f"tg_get_file: {ex}")
        return None



# ── Staff & Sheet helpers ──────────────────────────────────────────────────────
_staff_df_cache = None
_staff_df_ts: float = 0.0

def get_staff_df():
    """Lấy Staff sheet — ưu tiên đọc từ data_cache.json (0.001s), fallback Google Sheets."""
    global _staff_df_cache, _staff_df_ts
    now = time.time()
    if _staff_df_cache is not None and (now - _staff_df_ts) < CSV_CACHE_TTL:
        return _staff_df_cache

    # ── Fast path: data_cache.json (GitHub Actions build mỗi 5 phút) ──
    cache_path = os.path.join(os.path.dirname(__file__), "data_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as cf:
                cache_data = json.load(cf)
            staff_rows = cache_data.get("staff_rows")
            built_at_str = cache_data.get("built_at", "")
            if staff_rows and built_at_str:
                from datetime import datetime as _dt, timezone as _tz
                built_ts = _dt.strptime(built_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_tz.utc).timestamp()
                age_min = (time.time() - built_ts) / 60
                if age_min < 30:   # Dùng file nếu cache mới hơn 30 phút
                    _staff_df_cache = pd.DataFrame(staff_rows, dtype=str)
                    _staff_df_ts    = time.time()
                    logger.info(f"Loaded staff from data_cache.json (age={age_min:.1f}m) — {len(_staff_df_cache)} rows")
                    return _staff_df_cache
        except Exception as fe:
            logger.warning(f"data_cache.json staff load error: {fe}")

    # ── Fallback: fetch từ Google Sheets (~3-5s) ──
    df = fetch_single_csv(GID_STAFF)
    if df is not None:
        _staff_df_cache = df
        _staff_df_ts    = now
    return _staff_df_cache


def load_all_sheets():
    """Warm-up: tải song song 2 sheet chính vào cache."""
    with ThreadPoolExecutor(max_workers=2) as ex:
        ex.submit(fetch_single_csv, GID_INFO)
        ex.submit(fetch_single_csv, GID_TEAM_SUM)

def get_staff_data(user_id: int, field_name: str | None = None) -> str:
    """Tra cứu dữ liệu cá nhân từ Staff sheet theo Telegram user_id."""
    def e(s): return html.escape(str(s))
    df = get_staff_df()
    if df is None or df.empty:
        return "❌ Staff sheet empty."
    headers = df.iloc[0]
    data    = df.iloc[1:]
    sid     = str(user_id).strip()
    col_a   = data.iloc[:, 0].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    matched = data[col_a == sid]
    if matched.empty:
        return f"❌ No data for your ID.\nYour ID: <code>{e(sid)}</code>"
    row = matched.iloc[0]

    def clean(v: str) -> str:
        return "" if v.lower() in ("nan", "none", "", "#n/a", "#na", "#ref!", "#value!") else v

    if field_name is None:
        results = []
        for ci in range(len(headers)):
            h = str(headers.iloc[ci]).strip()
            if h.lower().startswith("my") and h.lower() not in ("nan", "none", ""):
                val = clean(safe(row, ci))
                results.append(f"• <b>{e(h)}:</b> {e(val) if val else '—'}")
        if not results:
            return "ℹ️ No 'my*' columns found."
        return "👤 <b>My Stats</b>\n━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(results) + "\n━━━━━━━━━━━━━━━━━━━━"
    else:
        for ci in range(len(headers)):
            if str(headers.iloc[ci]).strip().lower() == field_name.lower():
                val = clean(safe(row, ci))
                if not val:
                    return f"ℹ️ <b>{e(field_name)}:</b> (empty)"
                return f"📊 <b>{e(field_name)}:</b>\n{e(val)}"
        return f"❌ Column '<b>{e(field_name)}</b>' not found."

# ── Log search (fire-and-forget background) ────────────────────────────────────
def log_search_bg(user_name: str, user_id: int, tni_code: str):
    """Ghi log tìm kiếm vào GAS (background thread, không block)."""
    if not APPS_SCRIPT_URL:
        return
    now_mm = datetime.now(TZ_MM)
    payload = {
        "action":    "log_search",
        "user_name": user_name,
        "user_id":   str(user_id),
        "tni_code":  tni_code,
        "date":      now_mm.strftime("%Y-%m-%d"),
        "time":      now_mm.strftime("%H:%M"),
    }
    def _post():
        try:
            requests.post(APPS_SCRIPT_URL, json=payload, timeout=20)
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True).start()

# ── Team lookups ───────────────────────────────────────────────────────────────
GID_TL_SUM = GID_TEAM_SUM  # alias

def _lookup_sheet_col(gid: str, col_match_idx: int, match_val: str, col_result_idx: int) -> list:
    """Generic: tìm rows theo col_match_idx == match_val, trả về col_result_idx."""
    df = fetch_single_csv(gid)
    if df is None or df.empty:
        return []
    results = []
    for _, row in df.iterrows():
        cell = safe(row, col_match_idx).upper()
        if cell == match_val.upper():
            val = safe(row, col_result_idx)
            if val:
                results.append(val)
    return results

def lookup_team(team_code: str) -> list:
    """Tra cứu TL team summary (GID_TEAM_SUM col B=team_code, col H=content)."""
    df = fetch_single_csv(GID_TEAM_SUM)
    if df is None or df.empty:
        return [f"❌ No data for {html.escape(team_code)}"]
    results = []
    for _, row in df.iterrows():
        col_b = safe(row, 1).strip().upper()
        if col_b.startswith(team_code.upper()):
            col_h = safe(row, 7)
            if col_h:
                results.append(col_h.strip().lstrip("~ ").strip())
    if not results:
        return [f"❌ No data found for team <b>{html.escape(team_code)}</b>"]
    return [split_messages(r)[0] for r in results]

def lookup_notclose(team_code: str) -> list:
    """Tra cứu WO Not Close (GID_TL_WAITCD col H='T1notclose', col I=nội dung)."""
    df = fetch_single_csv(GID_TL_WAITCD)
    if df is None or df.empty:
        return [f"\u274c No data for {html.escape(team_code)} not close"]
    target = f"{team_code}notclose".lower()
    results = []
    for _, row in df.iterrows():
        col_h = safe(row, 7).strip().lower()   # col H = category label
        if col_h == target:
            col_i = safe(row, 8)               # col I = formatted content
            if col_i:
                results.append(col_i.strip())
    if not results:
        return [f"\u274c No Not Close data for <b>{html.escape(team_code)}</b>"]
    return [split_messages(r)[0] for r in results]

def lookup_waitcd(team_code: str) -> list:
    """Tra cứu WO Wait CD (GID_TL_WAITCD col H='T1waitcd', col I=nội dung)."""
    df = fetch_single_csv(GID_TL_WAITCD)
    if df is None or df.empty:
        return [f"\u274c No data for {html.escape(team_code)} wait CD"]
    target = f"{team_code}waitcd".lower()
    results = []
    for _, row in df.iterrows():
        col_h = safe(row, 7).strip().lower()   # col H = category label
        if col_h == target:
            col_i = safe(row, 8)               # col I = formatted content
            if col_i:
                results.append(col_i.strip())
    if not results:
        return [f"\u274c No Wait CD data for <b>{html.escape(team_code)}</b>"]
    return [split_messages(r)[0] for r in results]

# ── Site Access Template ───────────────────────────────────────────────────────
def get_site_access_template(site_id: str = "TNI0401", date_str: str = None) -> str:
    if not site_id or site_id.startswith("/"):
        site_id = "TNI0401"
    if not date_str:
        date_str = datetime.now(TZ_MM).strftime("%d/%m/%Y")
    return (
        f"Site access format\n"
        f"Site ID: {site_id}\n"
        f"Towerco ID: OCK\n"
        f"Contact Me: Khant Chaw Nyo\n"
        f"Contact No: 09688433214\n"
        f"NRC NO: 6/KaTaNa(N)114981\n"
        f"Mail add: Khantchaw.nyo@vcm.com.mm\n"
        f"Date: {date_str}\n"
        f"Activity Detail: Site down check\n"
        f"Activity Start time: 2 PM\n"
        f"Activity End Time: 4 PM"
    )

# ── Bot menu commands ──────────────────────────────────────────────────────────
def setup_bot_menu_commands():
    """Cài đặt menu lệnh cho bot."""
    commands = [
        {"command": "request_enter_site", "description": "Request enter Site towerco format"},
        {"command": "mysite",       "description": "All Site you control"},
        {"command": "mycable",      "description": "All your cable route"},
        {"command": "mydia",        "description": "All your customer DIA"},
        {"command": "myolt",        "description": "All Site have OLT"},
        {"command": "mysn",         "description": "All SN you control"},
        {"command": "mydata",       "description": "All your personal stats"},
        {"command": "daily",        "description": "Daily Result template"},
        {"command": "daily_result", "description": "Daily Result template"},
        {"command": "plan",         "description": "Daily plan template"},
        {"command": "help",         "description": "Show help menu"},
    ]
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setMyCommands",
            json={"commands": commands}, timeout=10
        )
    except Exception as ex:
        logger.error(f"setup_bot_menu_commands: {ex}")

# ── ULTRA-FAST HIGH-PERFORMANCE SEARCH ENGINE (Parallel + SWR + O(1) Hash Indexing) ──
from concurrent.futures import ThreadPoolExecutor

_csv_cache = {}
_csv_cache_ts = {}
CSV_CACHE_TTL = 120  # 2 phút cache sống

_tni_info_index = {}
_tni_team_sum_index = {}
_index_last_built = 0.0
_index_building = False

def fetch_single_csv(gid: str, is_sd: bool = False) -> pd.DataFrame | None:
    cache_key = f"{'sd_' if is_sd else ''}{gid}"
    cached = _csv_cache.get(cache_key)
    if cached is not None and (time.time() - _csv_cache_ts.get(cache_key, 0)) < CSV_CACHE_TTL:
        return cached
    base = SD_BASE_URL if is_sd else BASE_URL
    url = base + str(gid)
    hdrs = {"User-Agent": "Mozilla/5.0"}
    for attempt in range(1, 3):
        try:
            resp = requests.get(url, headers=hdrs, timeout=8, allow_redirects=True)
            resp.raise_for_status()
            content = resp.content.decode("utf-8", errors="replace")
            df = pd.read_csv(io.StringIO(content), header=None, dtype=str, on_bad_lines="skip")
            _csv_cache[cache_key] = df
            _csv_cache_ts[cache_key] = time.time()
            return df
        except Exception as ex:
            logger.warning(f"fetch_single_csv retry {attempt}/2 [gid={gid}]: {ex}")
            if attempt < 2:
                time.sleep(0.5)
    return _csv_cache.get(cache_key)

def safe(row, idx: int) -> str:
    if idx < len(row):
        val = str(row.iloc[idx]).strip()
        if val.lower() != "nan" and val != "-":
            return val
    return ""

def build_search_indexes(force: bool = False):
    global _tni_info_index, _tni_team_sum_index, _index_last_built, _index_building
    now = time.time()

    if not force and _tni_info_index and (now - _index_last_built) < CSV_CACHE_TTL:
        return
    if _index_building:
        return
    _index_building = True
    try:
        # ── 1. Fast path: data_cache.json ──
        cache_path = os.path.join(os.path.dirname(__file__), "data_cache.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as cf:
                    cache_data = json.load(cf)
                info_data = cache_data.get("info", {})
                team_data = cache_data.get("team", {})
                if info_data or team_data:
                    _tni_info_index = info_data
                    _tni_team_sum_index = team_data
                    _index_last_built = time.time()
                    logger.info(f"Loaded index from data_cache.json — Info:{len(_tni_info_index)}, Team:{len(_tni_team_sum_index)}")
                    if not force:
                        return
            except Exception as fe:
                logger.warning(f"data_cache.json load error: {fe}")

        # ── 2. Fallback: fetch trực tiếp từ Google Sheets (~3-5s) ──
        logger.info("Fetching fresh index from Google Sheets...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_info = executor.submit(fetch_single_csv, GID_INFO)
            f_team = executor.submit(fetch_single_csv, GID_TEAM_SUM)
            df_info = f_info.result()
            df_team = f_team.result()

        new_info_idx = {}
        if df_info is not None and not df_info.empty:
            rows = df_info.iloc[1:] if len(df_info) > 1 else df_info
            for _, row in rows.iterrows():
                col_a = safe(row, 0).upper().strip()
                if not col_a: continue
                code_part = col_a.split(":")[0].strip()
                if code_part not in new_info_idx:   # Ưu tiên lấy dòng mới nhất ở trên cùng
                    new_info_idx[code_part] = {
                        "site": safe(row, 1),
                        "cable": safe(row, 2),
                        "gpon": safe(row, 3),
                        "dia": safe(row, 4)
                    }

        new_team_idx = {}
        if df_team is not None and not df_team.empty:
            for _, row in df_team.iterrows():
                col_b = safe(row, 1).strip().upper()
                if not col_b: continue
                col_h = safe(row, 7)
                if col_h and col_b not in new_team_idx:   # Ưu tiên lấy dòng mới nhất ở trên cùng
                    new_team_idx[col_b] = col_h.strip().lstrip("~ ").strip()

        if new_info_idx:
            _tni_info_index = new_info_idx
        if new_team_idx:
            _tni_team_sum_index = new_team_idx
        _index_last_built = time.time()
        logger.info(f"Built index from Sheets — Info:{len(_tni_info_index)}, Team:{len(_tni_team_sum_index)}")

    except Exception as err:
        logger.error(f"Error building search indexes: {err}")
    finally:
        _index_building = False


def trigger_bg_index_refresh():
    """Chạy làm mới cache trong background thread để không bắt user chờ."""
    def _bg():
        build_search_indexes(force=True)
    t = threading.Thread(target=_bg, daemon=True)
    t.start()

def format_task_wo(raw: str) -> str:
    """Render col H content thành HTML sạch cho Toa 1 (Task & WO).
       Loại bỏ 100% phần 'Site Info' nếu có trong chuỗi thô."""
    e = html.escape
    if not raw:
        return ""

    raw_clean = raw
    if "📍 Site Info" in raw_clean or "📍 <b>Site Info</b>" in raw_clean or "🏢 Site" in raw_clean:
        task_pos = raw_clean.find("📋")
        wo_pos = raw_clean.find("🔧")
        alarm_pos = raw_clean.find("🔔")
        positions = [p for p in (task_pos, wo_pos, alarm_pos) if p != -1]
        if positions:
            raw_clean = raw_clean[min(positions):].strip()
        else:
            lines = []
            skip = False
            for line in raw_clean.split("\n"):
                if "Site Info" in line or "🏢 Site" in line:
                    skip = True
                elif skip and ("Task" in line or "WO" in line or "Alarm" in line):
                    skip = False
                    lines.append(line)
                elif not skip:
                    lines.append(line)
            raw_clean = "\n".join(lines).strip()

    # ── Format 1: Pre-formatted có ───── ──
    if "\u2500\u2500\u2500\u2500\u2500" in raw_clean:      # ─────
        lines = raw_clean.split("\n")
        content_lines = []
        in_content = False
        for line in lines:
            if "\u2500\u2500\u2500\u2500\u2500" in line:
                if not in_content:
                    in_content = True
                else:
                    break
            elif in_content:
                if "Site Info" not in line:
                    content_lines.append(line)
        if content_lines:
            return e("\n".join(content_lines).strip())

    # ── Format 2: Raw /Alarm: ... <+> /Task: ... <+> /WO: ... ──
    if "<+>" in raw_clean or "/Task:" in raw_clean or "/WO:" in raw_clean:
        sections = raw_clean.split("<+>")
        parts = []
        for sec in sections:
            sec = sec.strip()
            if "/Alarm:" in sec:
                content = sec[sec.find("/Alarm:") + 7:].strip()
                if content:
                    parts.append(f"🔔 <b>Alarm:</b> {e(content[:300])}")
            elif "/Task:" in sec:
                content = sec[sec.find("/Task:") + 6:].strip()
                if content and content.lower() not in ("no see", ""):
                    tasks = [t.strip() for t in content.split("/") if t.strip()]
                    parts.append("📋 <b>Task:</b>\n" + "\n".join(f"• {e(t[:150])}" for t in tasks[:5]))
            elif "/WO:" in sec:
                content = sec[sec.find("/WO:") + 4:].strip()
                if content:
                    wos = [w.strip() for w in content.split("/") if w.strip()]
                    parts.append("🔧 <b>WO:</b>\n" + "\n".join(f"• {e(w[:150])}" for w in wos[:3]))
        if parts:
            return "\n".join(parts)

    return e(raw_clean[:500])


def perform_unified_tni_search(tni: str, full_info: bool = False) -> str:
    """Tra cứu TNI O(1) — nhanh < 0.01s.
    full_info=False (TNI0122):      Task + WO ngắn gọn.
    full_info=True  (Info:TNI0122): Site + Cable + DIA + Task/WO đầy đủ."""
    e = html.escape
    tni_upper = tni.upper().strip()

    now = time.time()
    if not _tni_info_index:
        build_search_indexes(force=True)
    elif (now - _index_last_built) >= CSV_CACHE_TTL:
        trigger_bg_index_refresh()

    info    = _tni_info_index.get(tni_upper)
    task_wo = _tni_team_sum_index.get(tni_upper)

    has_info  = bool(info and any(info.values()))
    has_tasks = bool(task_wo)

    if not has_info and not has_tasks:
        return f"❌ No data found for <b>{e(tni_upper)}</b>"

    lines = [f"🔍 <b>{e(tni_upper)}</b>\n━━━━━━━━━━━━━━━━━━━━"]

    if full_info:
        # ── Info: TNI0122 → CHỈ Site + Cable + GPON + DIA (không gộp Task/WO) ──
        if not has_info:
            return f"❌ No site/cable/DIA info for <b>{e(tni_upper)}</b>"
        if info.get("site"):
            lines.append(f"\n🏢 <b>Site</b>\n{e(info['site'][:500])}")
        if info.get("cable"):
            lines.append(f"\n🔌 <b>Cable</b>\n{e(info['cable'][:500])}")
        if info.get("gpon"):
            lines.append(f"\n📶 <b>Gpon</b>\n{e(info['gpon'][:300])}")
        if info.get("dia"):
            dia_text = info["dia"]
            suffix = "..." if len(dia_text) > 500 else ""
            lines.append(f"\n🌐 <b>DIA</b>\n{e(dia_text[:500])}{suffix}")
    else:
        # ── TNI0122 → CHỈ Task + WO (không gộp Site/Cable/DIA) ──
        if not has_tasks:
            return f"❌ No task/WO data for <b>{e(tni_upper)}</b>"
        formatted = format_task_wo(task_wo)
        if formatted:
            lines.append(f"\n{formatted}")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

# ── Daily Report ──────────────────────────────────────────────────────────────
def fetch_daily_fields() -> list[str]:
    global _daily_fields, _daily_fields_ts
    now = time.time()
    if _daily_fields and (now - _daily_fields_ts) < DAILY_FIELDS_TTL:
        return _daily_fields
    # Dùng ngay danh sách trường chuẩn có sẵn để phản hồi tức thì (tránh chờ 10s Google Apps Script)
    return DAILY_FIELDS_DEFAULT

def clean_field_name(s: str) -> str:
    """Làm sạch nhãn cột: loại bỏ số thứ tự hoặc số La Mã đầu câu (1., 3., VII., I., etc.)."""
    s = re.sub(r'^[0-9ivxlcdmIVXLCDM]+[\.\s_\-]*', '', s.strip(), flags=re.IGNORECASE)
    return s.strip().lower()

def parse_daily_report(text: str, fields: list[str]) -> dict:
    result, cur_key, cur_val = {}, None, []

    def flush():
        if cur_key:
            result[cur_key] = " ".join(cur_val).strip()

    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        if ":" in line:
            colon = line.index(":")
            label = line[:colon].strip()
            val   = line[colon + 1:].strip()
            matched = None
            label_l = label.lower()
            clean_lbl = clean_field_name(label)
            
            # Nếu label chứa chữ "result" hoặc "daily", tự động khớp với "Daily report"
            if "result" in label_l or "daily" in label_l:
                for f in fields:
                    if f.lower() == "daily report":
                        matched = f
                        break
            
            if not matched:
                for f in fields:
                    clean_f = clean_field_name(f)
                    if clean_f and clean_lbl and (clean_f in clean_lbl or clean_lbl in clean_f):
                        matched = f
                        break

            if not matched:
                for f in fields:
                    if f.lower() in label_l or label_l in f.lower():
                        matched = f
                        break

            if matched:
                flush(); cur_key = matched
                cur_val = [val] if val else []
                continue
        if cur_key: cur_val.append(line)
    flush()
    return result

def is_daily(text: str) -> bool:
    text_l = text.lower()
    if "daily plan" in text_l or "plan:" in text_l or "kế hoạch" in text_l:
        return False
    if "above are the end-of-day" in text_l or "note:" in text_l or "ft result daily" in text_l or "find task" in text_l or "auto report" in text_l or "ref:" in text_l or "đã lưu" in text_l:
        return False
    if "daily result" not in text_l and "daily report" not in text_l:
        return False
    has_date = bool(re.search(r'\b\d{1,2}[/\.-]\d{1,2}[/\.-]\d{2,4}\b', text))
    return has_date


def get_copy_markup(chat_id: int, team_arg: str, text_label: str) -> dict:
    button_url = f"https://tni-bot.vercel.app/copy.html?team={team_arg}"
    if chat_id < 0:
        return {
            "inline_keyboard": [
                [{"text": text_label, "url": button_url}]
            ]
        }
    else:
        return {
            "inline_keyboard": [
                [{"text": text_label, "web_app": {"url": button_url}}]
            ]
        }



def get_user_team_number(user_id: int) -> int | None:
    try:
        df = get_staff_df()
        if df is None or df.empty:
            return None
        data = df.iloc[2:]
        sid = str(user_id).strip()
        col_a = data.iloc[:, 0].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
        matched = data[col_a == sid]
        if not matched.empty:
            row = matched.iloc[0]
            team_val = str(row.iloc[12]).strip().lower()
            if "team 01" in team_val or "team 1" in team_val or "t1" in team_val:
                return 1
            elif "team 02" in team_val or "team 2" in team_val or "t2" in team_val:
                return 2
            elif "team 03" in team_val or "team 3" in team_val or "t3" in team_val:
                return 3
            elif "team 04" in team_val or "team 4" in team_val or "t4" in team_val:
                return 4
    except Exception as e:
        logger.error(f"get_user_team_number error: {e}")
    return None

_team_staff_map = {}

def get_team_staff_names(team_num: int) -> list[str]:
    global _team_staff_map
    if team_num in _team_staff_map:
        return _team_staff_map[team_num]
    try:
        df = get_staff_df()
        if df is not None and not df.empty:
            data = df.iloc[2:]
            tmap = {1: [], 2: [], 3: [], 4: [], 5: []}
            for row in data.itertuples(index=False):
                if len(row) > 13:
                    probation_status = str(row[13]).strip().lower()
                    if "resign" in probation_status or "nghi" in probation_status or "nghỉ" in probation_status:
                        continue
                    row_team = str(row[12]).strip().lower()
                    full_name = str(row[5]).strip()
                    if full_name and full_name.lower() != "nan" and full_name != "-":
                        for t in (1, 2, 3, 4, 5):
                            if f"team 0{t}" in row_team or f"team {t}" in row_team or row_team == f"t{t}":
                                if full_name not in tmap[t]:
                                    tmap[t].append(full_name)
            _team_staff_map = tmap
            return _team_staff_map.get(team_num, [])
    except Exception as e:
        logger.error(f"get_team_staff_names error: {e}")
    return []

def get_plan_template_text(team_num: int) -> str:
    try:
        matched_staff = get_team_staff_names(team_num)
        now_mm = datetime.now(TZ_MM)
        date_str = now_mm.strftime("%d/%m/%Y")
        
        lines = [
            f"Daily Plan: {date_str}",
            f"Team {team_num}",
            "I. Hot task rescue Site down/ link Down >24 :",
            "II. Hot task Rescue Cell down: ",
            "III. Hot task Repair DG abnomal: ",
            "IV. Hot task Repair DG run>16H:",
            "V. Hot task other: ",
            "VI.  Note: /Find /TNIxxxx Yesterday check which /Tool, /material need /bring for do on Site. All material using new or move or order all people can sent folow menu: https://t.me/+atexSvtj13gyYjI1",
            "VII. List name FT : Name Site ( WO + Task)"
        ]
        
        for name in matched_staff:
            lines.append(f"{name}: ")
            
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"get_plan_template_text error: {e}")
        return f"Error: {str(e)}"

def is_daily_plan(text: str) -> bool:
    """Detect plan message: text has 'plan'/'kế hoạch' and date, excluding bot auto reports."""
    if not text:
        return False
    text_l = text.lower()
    if any(kw in text_l for kw in (
        "comparison of plan for", "auto report", "plan stats:", "report — daily plan",
        "crosscheck", "plan tomorrow status", "plan vs actual", "eod summary",
        "shows detailed site assignments", "tasks grouped by department", "recent plans",
        "plans for ", "plan updated", "plan saved", "ref:", "ref:dp-", "đã lưu",
        "tni personal find task", "ft result daily", "personal find task", "find task + wo",
        "list name ft"
    )):
        return False

    has_plan = "plan" in text_l or "kế hoạch" in text_l
    has_date = bool(re.search(r'\b\d{1,2}[\/\.-]\d{1,2}(?:[\/\.-]\d{2,4})?\b', text))
    return has_plan and has_date


def parse_plan_fields(text: str, chat_id: int | None = None, chat_title: str | None = None) -> tuple:
    """Extract (date, team, content) from plan message, with fallback to chat ID/title for team inference."""
    lines = text.strip().split("\n")
    date_str = ""
    date_m = re.search(r'(?:daily\s*plan|plan\s*for)[:\s]+(\d{1,2}[\/\.-]\d{1,2}(?:[\/\.-]\d{2,4})?)', text, re.IGNORECASE)
    if not date_m:
        date_m = re.search(r'(\d{1,2}[\/\.-]\d{1,2}(?:[\/\.-]\d{2,4})?)', text)
    if date_m:
        raw_d = date_m.group(1)
        parts = re.split(r'[\/\.-]', raw_d)
        now_mm = datetime.now(TZ_MM)
        if len(parts) == 3:
            d, m, y = parts
            if len(y) == 2:
                y = "20" + y
            date_str = f"{int(d):02d}/{int(m):02d}/{y}"
        elif len(parts) == 2:
            d, m = parts
            date_str = f"{int(d):02d}/{int(m):02d}/{now_mm.year}"
    if not date_str:
        now_mm = datetime.now(TZ_MM)
        date_str = now_mm.strftime("%d/%m/%Y")

    team_str = ""
    team_m = re.search(r'\bTeam\s*0?([1-5])\b', text, re.IGNORECASE)
    if not team_m:
        team_m = re.search(r'\bT([1-5])\b', text, re.IGNORECASE)
    if team_m:
        team_str = f"Team {team_m.group(1)}"

    # Fallback to chat_title or chat_id if team is not explicitly written in text
    if not team_str and chat_title:
        title_m = re.search(r'TEAM\s*0?([1-5])', chat_title, re.IGNORECASE)
        if title_m:
            team_str = f"Team {title_m.group(1)}"
    if not team_str and chat_id:
        TELEGRAM_GROUPS = {
            "Team 1": -1004215695747,
            "Team 2": -1004480845549,
            "Team 3": -1004369170658,
            "Team 4": -1004293741999,
        }
        def norm_id(cid): return str(cid).replace("-100", "").replace("-", "")
        for tname, gid in TELEGRAM_GROUPS.items():
            if norm_id(chat_id) == norm_id(gid):
                team_str = tname
                break

    team_line_idx = 0
    for i, line in enumerate(lines[1:], 1):
        if re.match(r'^\s*Team\s*0?[1-5]\s*$', line.strip(), re.IGNORECASE):
            team_line_idx = i
            break
    start_idx = max(1, team_line_idx + 1 if team_line_idx > 0 else 1)
    content_lines = []
    for i in range(start_idx, len(lines)):
        line = lines[i].strip()
        if not content_lines and not line:
            continue
        content_lines.append(lines[i])
    content = "\n".join(content_lines).strip()
    return date_str, team_str, content


def store_daily_plan_to_sheet(date_str: str, team_str: str, content: str) -> dict:
    url = DAILY_APPS_SCRIPT_URL or APPS_SCRIPT_URL or "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
    try:
        r = requests.post(url, json={
            "action": "store_daily_plan",
            "date": date_str,
            "team": team_str,
            "content": content,
            "daily_report": "",
            "comparison": ""
        }, timeout=25)
        return r.json()
    except Exception as e:
        logger.error(f"store_daily_plan_to_sheet error: {e}")
        return {}


_recent_plan_sends = {}
_recent_plan_msg_hashes = {}

def send_daily_plan_template(chat_id: int, team_num: int) -> None:
    now_ts = time.time()
    key = f"{chat_id}:{team_num}"
    if (now_ts - _recent_plan_sends.get(key, 0)) < 6.0:
        logger.info(f"Skipping duplicate send_daily_plan_template for chat {chat_id}")
        return
    _recent_plan_sends[key] = now_ts

    template = get_plan_template_text(team_num)
    tg_send(chat_id, template)

_recent_help_sends = {}

def send_help_menu(chat_id: int) -> None:
    now_ts = time.time()
    if (now_ts - _recent_help_sends.get(chat_id, 0)) < 1.5:
        logger.info(f"Skipping duplicate send_help_menu for chat {chat_id}")
        return
    _recent_help_sends[chat_id] = now_ts

    menu_text = (
        "🚂 <b>TNI SEARCH BOT — COMMAND DIRECTORY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>[TOA 1] Task & Work Order Search</b>\n"
        "• Type: <code>TNI0129</code> or <code>TNI0129_01</code> or <code>/tni TNI0129</code>\n\n"
        "<b>[TOA 2] Site Info & Cable & DIA Search</b>\n"
        "• Type: <code>Info: TNI0129</code> or <code>info TNI0129</code> or <code>/info TNI0129</code>\n\n"
        "<b>[TOA 3] Open / Not Close WOs Search</b>\n"
        "• Type: <code>/t1notclose</code>, <code>/t2notclose</code>, <code>/t3notclose</code>, <code>/t4notclose</code>\n\n"
        "<b>[TOA 4] Wait CD WOs Search</b>\n"
        "• Type: <code>/t1waitcd</code>, <code>/t2waitcd</code>, <code>/t3waitcd</code>, <code>/t4waitcd</code>\n\n"
        "<b>[TOA 5] Clear Site History Search</b>\n"
        "• Type: <code>Clear TNI0129</code> or <code>/clear TNI0129</code>\n\n"
        "<b>[TOA 6] Team Summary (Private Chat)</b>\n"
        "• Type: <code>T1</code>, <code>T2</code>, <code>T3</code>, <code>T4</code>\n\n"
        "<b>[TOA 7] Staff Personal Lookup</b>\n"
        "• Type: <code>mysite</code>, <code>mycable</code>, <code>mydia</code>, <code>mydata</code>\n"
        "• Admin: <code>mysite &lt;ID&gt;</code>, <code>mydata &lt;ID&gt;</code>\n\n"
        "<b>[TOA 8] Construction Search</b>\n"
        "• Type: <code>cons TNI0310</code> or <code>pro TNI0310</code> or <code>/cons TNI0310</code>\n\n"
        "<b>[TOA 9] Help & Interactive Menu</b>\n"
        "• Type: <code>menu</code> or <code>/menu</code> or <code>help</code>\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    tg_send(chat_id, menu_text, parse_mode="HTML")

_recent_daily_submits = {}
_recent_search_keys = {}
_recent_update_ids = {}

def is_duplicate_search(chat_id: int, user_id: int, query_key: str) -> bool:
    now = time.time()
    dedup = f"{chat_id}:{user_id}:{query_key.upper()}"
    last_time = _recent_search_keys.get(dedup, 0)
    if (now - last_time) < 1.5:  # Giảm xuống 1.5s để phản hồi siêu tốc (< 1s)
        logger.info(f"Skipping duplicate search for key {dedup}")
        return True
    _recent_search_keys[dedup] = now
    if len(_recent_search_keys) > 500:
        _recent_search_keys.clear()
    return False

def lookup_clear_site(tni: str) -> str:
    """Tra cứu Lịch sử Clear Site từ tab Search Site Clear (GID_SITE_CLEAR)."""
    tni_u = tni.upper()
    try:
        df = fetch_single_csv(GID_SITE_CLEAR, is_sd=True)
        if df is None or df.empty or len(df) < 4:
            return f"❌ Search Site Clear sheet missing or empty."

        col_idx = -1
        # Tìm cột chứa mã trạm trong các hàng tiêu đề (hàng 0, 1, 2, 3, 4)
        for r_idx in range(min(5, len(df))):
            row = df.iloc[r_idx]
            for col in range(1, len(row)):
                val = str(row.iloc[col]).strip().upper()
                if val == tni_u:
                    col_idx = col
                    break
            if col_idx >= 0:
                break

        if col_idx < 0:
            return f"❌ Not found <b>{html.escape(tni_u)}</b> in Clear Site sheet."

        lines = [f"🔍 <b>Clear History for {html.escape(tni_u)}</b>", "━━━━━━━━━━━━━━━━━━━━"]
        for r in range(len(df)):
            row = df.iloc[r]
            val = safe(row, col_idx)
            label = str(row.iloc[0]).strip() if len(row) > 0 else ""

            if not val or val.lower() in ("nan", "-", ""):
                continue
            if label and label.lower() != "nan":
                lines.append(f"• <b>{html.escape(label)}:</b> {html.escape(val)}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"lookup_clear_site error [{tni_u}]: {e}")
        return f"❌ Error loading clear site data: {html.escape(str(e)[:80])}"

CONS_SPREADSHEET_ID = "1ViXXv5P8jSgx5heBqEP419ZkSR77C3OsflK0xpHMoi8"

def lookup_construction_site(tni: str) -> str:
    """Tra cứu thông tin Construction từ tab Search Construction (Toa 8)."""
    e = html.escape
    tni_upper = tni.upper().strip()
    url = f"https://docs.google.com/spreadsheets/d/{CONS_SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet=Search%20Construction"
    
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return f"❌ Failed to fetch Construction data (HTTP {r.status_code})."
        import pandas as pd, io
        df = pd.read_csv(io.StringIO(r.text))
        if df.empty:
            return f"❌ Construction sheet is empty."

        clean_target = tni_upper.replace("-", "").replace("_", "").replace(" ", "")
        matched_row = None
        headers = df.columns.tolist()

        for idx, row in df.iterrows():
            col_a = str(row.iloc[0]).strip().upper() if len(row) > 0 else ""
            clean_col_a = col_a.replace("-", "").replace("_", "").replace(" ", "")
            if clean_col_a and (clean_col_a == clean_target or clean_target in clean_col_a or clean_col_a in clean_target):
                matched_row = row
                break

        if matched_row is None:
            return f"❌ No construction info found for <b>{e(tni_upper)}</b>"

        code_title = str(matched_row.iloc[0]).strip() if len(matched_row) > 0 else tni_upper
        lines = [f"🏗️ <b>CONSTRUCTION INFO: {e(code_title)}</b>\n━━━━━━━━━━━━━━━━━━━━"]

        for col_i in range(1, len(matched_row)):
            val = str(matched_row.iloc[col_i]).strip()
            if val and val.lower() != "nan":
                hdr = headers[col_i] if col_i < len(headers) and "Unnamed" not in str(headers[col_i]) else f"Item {col_i}"
                lines.append(f"🔹 <b>{e(hdr)}:</b>\n<code>{e(val)}</code>")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        return "\n\n".join(lines)
    except Exception as err:
        logger.error(f"lookup_construction_site error [{tni_upper}]: {err}")
        return f"❌ Construction search error: {e(str(err)[:100])}"

def submit_daily(chat_id: int, user_id: int, first_name: str, text: str) -> None:
    now_ts = time.time()
    dedup_key = f"{user_id}:{text.strip()[:60]}"
    if (now_ts - _recent_daily_submits.get(dedup_key, 0)) < 10.0:
        logger.info(f"Skipping duplicate submit_daily for user {user_id}")
        return
    _recent_daily_submits[dedup_key] = now_ts

    fields = fetch_daily_fields()
    parsed = parse_daily_report(text, fields)
    now_mm = datetime.now(TZ_MM)
    if "Daily report" not in parsed:
        parsed["Daily report"] = now_mm.strftime("%d/%m/%Y")
    if not DAILY_APPS_SCRIPT_URL:
        tg_send(chat_id, "❌ Bot DAILY_APPS_SCRIPT_URL not configured")
        return
    try:
        resp   = requests.post(DAILY_APPS_SCRIPT_URL,
                               json={"action": "daily_add",
                                     "telegram_id": str(user_id),
                                     "user_name": first_name or str(user_id),
                                     "fields": parsed},
                               timeout=35)
        result = resp.json()
        if result.get("status") == "ok":
            name = result.get("name") or first_name or str(user_id)
            logger.info(f"submit_daily ok: {name}")
            tg_send(chat_id, f"✅ Recorded Daily Result: <b>{html.escape(name)}</b>")
        else:
            tg_send(chat_id, f"❌ Save error\n{result.get('message','')[:120]}")
    except requests.exceptions.ReadTimeout:
        logger.warning(f"submit_daily read timeout (GAS background recording): {user_id}")
        name = first_name or str(user_id)
        tg_send(chat_id, f"✅ Recorded Daily Result: <b>{html.escape(name)}</b>")
    except Exception as ex:
        logger.error(f"submit_daily: {ex}")
        tg_send(chat_id, f"❌ Connection error\n{str(ex)[:80]}")

def submit_photo(chat_id: int, user_id: int, file_id: str) -> None:
    """Gửi ảnh lên GAS để lưu Drive — GAS tự attach vào dòng gần nhất."""
    if not DAILY_APPS_SCRIPT_URL:
        return
    file_path = tg_get_file(file_id)
    if not file_path:
        tg_send(chat_id, "📷 ❌")
        return
    tg_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    try:
        resp   = requests.post(DAILY_APPS_SCRIPT_URL,
                               json={"action": "daily_photo",
                                     "telegram_id": str(user_id),
                                     "tg_url": tg_url},
                               timeout=10)
        result = resp.json()
        tg_send(chat_id, "📷 ✅" if result.get("status") == "ok" else "📷 ❌")
    except Exception as ex:
        logger.error(f"submit_photo: {ex}")
        tg_send(chat_id, "📷 ❌")

# ── Self-healing Webhook Checker ──────────────────────────────────────────────
_last_wh_check = 0

def ensure_webhook_active():
    global _last_wh_check
    now = time.time()
    if now - _last_wh_check < 60:
        return
    _last_wh_check = now
    try:
        def _check():
            r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo", timeout=5).json()
            wh_url = r.get("result", {}).get("url", "")
            if wh_url != "https://tni-bot.vercel.app/api/search_bot":
                logger.warning(f"Webhook was missing ({wh_url}), re-hooking to Vercel...")
                requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url=https://tni-bot.vercel.app/api/search_bot", timeout=5)
        threading.Thread(target=_check, daemon=True).start()
    except Exception as e:
        logger.error(f"ensure_webhook_active error: {e}")

_processed_updates = set()

# ── Update handler ────────────────────────────────────────────────────────────
def handle(update: dict) -> None:
    ensure_webhook_active()
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return

    chat_id    = msg["chat"]["id"]
    user       = msg.get("from", {})
    user_id    = user.get("id", 0)
    first_name = user.get("first_name", "")

    # 🛑 BỎ QUA TIN NHẮN TRÙNG LẬP THEO UPDATE_ID
    update_id = update.get("update_id")
    if update_id:
        now_ts = time.time()
        if (now_ts - _recent_update_ids.get(update_id, 0)) < 15.0:
            logger.info(f"Skipping duplicate update_id {update_id}")
            return
        _recent_update_ids[update_id] = now_ts
        if len(_recent_update_ids) > 1000:
            _recent_update_ids.clear()

    # 🛑 BỎ QUA TIN NHẮN TỪ BOT KHÁC HOẶC BẢN THÂN BOT
    if user.get("is_bot"):
        return

    # ── PHOTO ──────────────────────────────────────────────────────────────
    if "photo" in msg:
        file_id = msg["photo"][-1]["file_id"]
        submit_photo(chat_id, user_id, file_id)
        return

    text = (msg.get("text") or "").strip()
    if not text:
        return

    # ── SITE DOWN V2 RELAY ──────────────────────────────────────────────────
    text_l = text.lower()
    if "site down" in text_l or "cell down" in text_l or "dg abnormal" in text_l or "dg run>16h" in text_l or "down_tni" in text_l:
        sd_url = "https://script.google.com/macros/s/AKfycbxVi0BGDW7B_KBxcSEdw3yuHB9Rs2BemQEYeKDwsybJQdmQv-_0HqyGHjpZI6jupxll/exec"
        logger.info(f"[SD Relay] Forwarding Site Down report update to Apps Script...")
        try:
            requests.post(sd_url, json=update, timeout=15)
        except Exception as e:
            logger.error(f"[SD Relay] Forward error: {e}")

    # Map reply keyboard button labels to actual commands
    text_l = text.lower().strip()
    if any(kw in text_l for kw in ("request enter site", "request site enter", "site access format", "site access", "site enter")):
        parts = text.split(maxsplit=1)
        passed_site = parts[1].upper().strip() if len(parts) > 1 and parts[1].upper().startswith("TNI") else "TNI0401"
        reply = get_site_access_template(passed_site)
        tg_send(chat_id, reply)
        return

    # ── UNIFIED COMMAND NORMALIZATION: Tự động loại bỏ '/' và '@bot_username' ──
    clean_text = text
    if clean_text.startswith("/"):
        parts = clean_text.split(maxsplit=1)
        first_word = parts[0][1:].lower().split("@")[0]  # e.g. "/t4notclose@bot" -> "t4notclose"
        rest = parts[1] if len(parts) > 1 else ""

        if first_word in ("request_enter_site", "request_site_enter", "site_access", "siteaccess", "site_enter", "request_site"):
            passed_site = rest.upper().strip() if rest else "TNI0401"
            reply = get_site_access_template(passed_site)
            tg_send(chat_id, reply)
            return

        if first_word == "ping":
            tg_send(chat_id, f"🏓 pong {BOT_VERSION} | chat={chat_id} | user={user_id}")
            return

        if first_word in ("start", "help", "menu", "men"):
            if rest.upper().startswith("PLAN_T"):
                team_num_str = rest[6:]
                if team_num_str.isdigit():
                    send_daily_plan_template(chat_id, int(team_num_str))
                    return
            send_help_menu(chat_id)
            return

        if first_word in ("daily", "daily_result", "dailyresult"):
            if is_duplicate_search(chat_id, user_id, "DAILY"):
                return
            send_daily_template(chat_id)
            return

        if first_word in ("plan", "dailyplan"):
            if is_duplicate_search(chat_id, user_id, f"PLAN:{text}"):
                return
            team_num = None
            if rest:
                team_arg = rest.upper()
                m = re.match(r"^(T(?:EAM)?\s*([1-4])|[1-4])$", team_arg, re.IGNORECASE)
                if m:
                    team_num = int(m.group(2) if m.group(2) else m.group(1))
            if not team_num:
                team_num = get_user_team_number(user_id) or 1
            send_daily_plan_template(chat_id, team_num)
            return

        if first_word in ("id", "myid"):
            chat_title = msg["chat"].get("title") or first_name or "Private"
            chat_type  = msg["chat"].get("type", "private")
            tg_send(chat_id, f"👤 <b>{html.escape(first_name)}</b>\n🔑 ID: <code>{user_id}</code>\n💬 Chat: <code>{chat_id}</code>\n📍 Type: {chat_type}")
            return

        if first_word == "reload":
            load_all_sheets()
            tg_send(chat_id, "✅ Data reloaded")
            return

        clean_text = f"{first_word} {rest}".strip()

    # ── CLASSIFY QUERY VIA SSOT ENGINE FIRST ──
    classified = classify_query(clean_text) if classify_query else None
    action = classified.get("action") if classified else None
    code = classified.get("code") if classified else None

    if action == "MENU":
        logger.info(f"[SSOT Router] Help menu requested | chat={chat_id}")
        send_help_menu(chat_id)
        return

    if action == "CONS":
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"CONS:{code}"): return
        log_search_bg(first_name or str(user_id), user_id, f"CONS {code}")
        message = lookup_construction_site(code)
        for chunk in split_messages(message): tg_send(chat_id, chunk)
        return

    if action == "NOTCLOSE":
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"NOTCLOSE:{code}"): return
        log_search_bg(first_name or str(user_id), user_id, f"{code}notclose")
        messages = lookup_notclose(code)
        full_text = f"📑 <b>{code} NOT CLOSE</b> ({len(messages)} items)\n\n" + "\n\n".join(messages)
        for chunk in split_messages(full_text): tg_send(chat_id, chunk)
        return

    if action == "WAITCD":
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"WAITCD:{code}"): return
        log_search_bg(first_name or str(user_id), user_id, f"{code}waitcd")
        messages = lookup_waitcd(code)
        full_text = f"⏳ <b>{code} WAIT CD</b> ({len(messages)} items)\n\n" + "\n\n".join(messages)
        for chunk in split_messages(full_text): tg_send(chat_id, chunk)
        return

    if action == "CLEAR":
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"CLEAR:{code}"): return
        log_search_bg(first_name or str(user_id), user_id, f"CLEAR {code}")
        message = lookup_clear_site(code)
        for chunk in split_messages(message): tg_send(chat_id, chunk)
        return

    if action == "INFO":
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"INFO:{code}"): return
        log_search_bg(first_name or str(user_id), user_id, f"Info:{code}")
        result = perform_unified_tni_search(code, full_info=True)
        for chunk in split_messages(result): tg_send(chat_id, chunk)
        return

    if action == "TNI":
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"TNI:{code}"): return
        log_search_bg(first_name or str(user_id), user_id, code)
        result = perform_unified_tni_search(code, full_info=False)
        for chunk in split_messages(result): tg_send(chat_id, chunk)
        return

    if action == "ADMIN_LOOKUP":
        field_name = classified.get("field")
        target_id  = int(classified.get("target_id"))
        field      = None if field_name in ("mydata", "myall") else field_name
        reply = get_staff_data(target_id, field)
        header = f"👤 <b>Viewing ID:</b> <code>{target_id}</code> ({html.escape(field_name)})\n"
        for chunk in split_messages(header + reply): tg_send(chat_id, chunk)
        return

    # ── DAILY REPORT SUBMIT ──
    if is_daily(clean_text):
        submit_daily(chat_id, user_id, first_name, clean_text)
        return

    # ── DAILY PLAN SUBMIT ──
    if is_daily_plan(clean_text):
        chat_title = msg.get("chat", {}).get("title", "")
        date_str, team_str, content = parse_plan_fields(clean_text, chat_id, chat_title)
        if date_str and team_str:
            res = store_daily_plan_to_sheet(date_str, team_str, content or clean_text)
            if res.get("status") in ("ok", "duplicate"):
                ref = res.get("ref", "?")
                dup = res.get("duplicate", False)
                tg_send(chat_id, f"✅ <b>Plan {'updated' if dup else 'saved'}</b> — REF:<b>{ref}</b> | {team_str} | {date_str}")
            return

    # ── STAFF PERSONAL LOOKUP (mysite / mycable / mydia / mydata / myolt) ──
    text_low = clean_text.lower().strip()
    is_my_field    = (text_low.startswith("my") and len(text_low) > 2 and " " not in text_low)
    is_range_query = bool(re.match(r'^[A-Z]\d+:[A-Z]\d+$', clean_text, re.IGNORECASE))
    if is_my_field or is_range_query:
        field = None if is_range_query else text_low
        reply = get_staff_data(user_id, field)
        tg_send(chat_id, reply)
        return

    # ── TEAM LEADER SEARCH (T1/T2/T3/T4) ──
    chat_type = msg.get("chat", {}).get("type", "private")
    team_match = re.match(r"^(T[1-4])$", clean_text.strip(), re.IGNORECASE)
    if team_match:
        if chat_type == "private":
            team_code = team_match.group(1).upper()
            log_search_bg(first_name or str(user_id), user_id, team_code)
            messages = lookup_team(team_code)
            full_text = f"📋 <b>{team_code} Summary</b> ({len(messages)} items)\n\n" + "\n\n".join(messages)
            for chunk in split_messages(full_text): tg_send(chat_id, chunk)
        return

    # ── CLASSIFY QUERY VIA SSOT SEARCH ENGINE ─────────────────────────────────
    classified = classify_query(text) if classify_query else None
    action = classified.get("action") if classified else None
    code = classified.get("code") if classified else None

    # ── TOA 9: MENU DIRECTORY (menu, /menu, help) ─────────────────────────────
    if action == "MENU":
        logger.info(f"[SSOT Router] Help menu requested | chat={chat_id}")
        send_help_menu(chat_id)
        return

    # ── TOA 8: CONSTRUCTION SEARCH (cons TNIxxxx, pro TNIxxxx) ─────────────────
    if action == "CONS":
        tni = code
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"CONS:{tni}"):
            return
        logger.info(f"[SSOT Router] Construction site lookup: {tni} | chat={chat_id}")
        log_search_bg(first_name or str(user_id), user_id, f"CONS {tni}")
        try:
            message = lookup_construction_site(tni)
            for chunk in split_messages(message):
                tg_send(chat_id, chunk)
        except Exception as err:
            logger.error(f"Construction lookup error [{tni}]: {err}")
            tg_send(chat_id, f"❌ Error: {html.escape(str(err)[:80])}")
        return

    # ── TOA 3: NOT CLOSE SEARCH (/t1notclose, t4notclose...) ──────────────────
    if action == "NOTCLOSE":
        team_code = code
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"NOTCLOSE:{team_code}"):
            return
        logger.info(f"[SSOT Router] NotClose lookup: {team_code} | chat={chat_id}")
        log_search_bg(first_name or str(user_id), user_id, f"{team_code}notclose")
        try:
            messages = lookup_notclose(team_code)
            full_text = f"📑 <b>{team_code} NOT CLOSE</b> ({len(messages)} WOs)\n\n" + "\n\n".join(messages)
            for chunk in split_messages(full_text):
                tg_send(chat_id, chunk)
        except Exception as err:
            logger.error(f"NotClose lookup error [{team_code}]: {err}")
            tg_send(chat_id, f"❌ Error: {html.escape(str(err)[:80])}")
        return

    # ── TOA 4: WAIT CD SEARCH (/t1waitcd, t4waitcd...) ────────────────────────
    if action == "WAITCD":
        team_code = code
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"WAITCD:{team_code}"):
            return
        logger.info(f"[SSOT Router] WaitCD lookup: {team_code} | chat={chat_id}")
        log_search_bg(first_name or str(user_id), user_id, f"{team_code}waitcd")
        try:
            messages = lookup_waitcd(team_code)
            full_text = f"⏳ <b>{team_code} WAIT CD</b> ({len(messages)} WOs)\n\n" + "\n\n".join(messages)
            for chunk in split_messages(full_text):
                tg_send(chat_id, chunk)
        except Exception as err:
            logger.error(f"WaitCD lookup error [{team_code}]: {err}")
            tg_send(chat_id, f"❌ Error: {html.escape(str(err)[:80])}")
        return

    # ── 1. KEY "CLEAR": CLEAR TNIxxxx / /clear TNIxxxx — tra cứu Lịch sử Clear Site ──────────────
    if action == "CLEAR":
        tni = code
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"CLEAR:{tni}"):
            return
        logger.info(f"[SSOT Router] Clear site lookup: {tni} | chat={chat_id}")
        log_search_bg(first_name or str(user_id), user_id, f"CLEAR {tni}")
        try:
            message = lookup_clear_site(tni)
            for chunk in split_messages(message):
                tg_send(chat_id, chunk)
        except Exception as err:
            logger.error(f"Clear lookup error [{tni}]: {err}")
            tg_send(chat_id, f"❌ Error: {html.escape(str(err)[:80])}")
        return

    # ── 2. KEY "INFO" SEARCH: /info TNIxxxx hoặc info: TNIxxxx ─────────────────────
    if action == "INFO":
        tni = code
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"INFO:{tni}"):
            return
        logger.info(f"[SSOT Router] Unified Info lookup: {tni} | chat={chat_id}")
        log_search_bg(first_name or str(user_id), user_id, f"Info:{tni}")
        try:
            result = perform_unified_tni_search(tni, full_info=True)   # Info: → Site+Cable+DIA only
            for chunk in split_messages(result):
                tg_send(chat_id, chunk)
        except Exception as err:
            logger.error(f"Unified search error [{tni}]: {err}")
            tg_send(chat_id, f"❌ Lookup error: {html.escape(str(err))}")
        return

    # ── 3. KEY "TNI" SEARCH: TNIxxxx / TNIxxxx_01 / /tni TNIxxxx ───────────────────
    if action == "TNI":
        tni = code
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"TNI:{tni}"):
            return
        logger.info(f"[SSOT Router] Unified TNI lookup: {tni} | chat={chat_id}")
        log_search_bg(first_name or str(user_id), user_id, tni)
        try:
            result = perform_unified_tni_search(tni, full_info=False)  # TNI0122 → Task+WO only
            for chunk in split_messages(result):
                tg_send(chat_id, chunk)
        except Exception as err:
            logger.error(f"Unified search error [{tni}]: {err}")
            tg_send(chat_id, f"❌ Lookup error: {html.escape(str(err))}")
        return


def ensure_webhook_locked_bg():
    """Tự động khóa lại Webhook Telegram cho Bot 3 trong background thread nếu bị nhả."""
    if not TOKEN:
        return
    def _do():
        try:
            target_url = "https://tni-bot.vercel.app/api/search_bot"
            requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={target_url}", timeout=5)
        except Exception as e:
            logger.error(f"ensure_webhook_locked_bg error: {e}")
    threading.Thread(target=_do, daemon=True).start()

_processed_updates = set()

# ── Vercel entry point (redeploy triggered) ──────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 2 * 1024 * 1024:  # 2MB Limit protection
                logger.warning("Rejected POST request: Payload size exceeds 2MB limit.")
                self.send_response(413)
                self.end_headers()
                self.wfile.write(b'{"error":"Payload Too Large"}')
                return

            if TELEGRAM_SECRET_TOKEN:
                secret_header = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if secret_header != TELEGRAM_SECRET_TOKEN:
                    logger.warning("Rejected POST request: Secret token mismatch.")
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b'{"error":"Forbidden"}')
                    return

            raw  = self.rfile.read(length)
            data = json.loads(raw)

            # ── Xử lý submit_plan (đồng bộ, cần response body) ──
            action = data.get("action")
            if action == "submit_plan":
                chat_id = data.get("chat_id")
                text = data.get("text", "")
                if chat_id and text:
                    tg_send(int(chat_id), text)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
                    return

            # ══════════════════════════════════════════════════════════
            # ⚡ CRITICAL: Trả HTTP 200 OK NGAY LẬP TỨC (~10ms)
            #    để Telegram KHÔNG retry gửi lại cùng update.
            #    Sau đó mới xử lý logic trong background thread.
            #    Vercel Python runtime giữ process sống trong maxDuration (60s)
            #    nên daemon thread vẫn chạy đủ sau khi flush response.
            # ══════════════════════════════════════════════════════════
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

            # ── Xử lý Telegram update trong background ──
            def _process_bg(update_data):
                try:
                    handle(update_data)
                except Exception as ex:
                    logger.error(f"handle() error: {ex}")
                    try:
                        import traceback
                        tb = traceback.format_exc()
                        msg_obj = update_data.get("message") or update_data.get("edited_message") or {}
                        chat_id = msg_obj.get("chat", {}).get("id")
                        if chat_id:
                            tg_send(chat_id, f"⚠️ <b>Error:</b>\n<pre>{html.escape(tb[:2000])}</pre>")
                    except Exception:
                        pass

            threading.Thread(target=_process_bg, args=(data,), daemon=True).start()

        except Exception as ex:
            logger.error(f"Webhook POST parse error: {ex}")
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except Exception:
                pass

    def do_GET(self):
        # Không gọi ensure_webhook_locked_bg — daemon thread chết ngay trên Vercel
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)
        
        action = query.get("action", [None])[0]
        
        # Reset webhook: xóa pending updates bị kẹt, set lại webhook
        if action == "reset":
            try:
                expected = "https://tni-bot.vercel.app/api/search_bot"
                r1 = requests.post(f"{TG_API}/deleteWebhook",
                    json={"drop_pending_updates": True}, timeout=10).json()
                r2 = requests.post(f"{TG_API}/setWebhook",
                    json={
                        "url": expected,
                        "allowed_updates": ["message", "edited_message", "channel_post"],
                        "drop_pending_updates": True
                    }, timeout=10).json()
                r3 = requests.get(f"{TG_API}/getWebhookInfo", timeout=10).json()
                setup_bot_menu_commands()
                result = {
                    "delete": r1,
                    "set": r2, 
                    "menu": "updated",
                    "info": r3.get("result", {}),
                    "version": BOT_VERSION
                }
            except Exception as ex:
                result = {"error": str(ex), "version": BOT_VERSION}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode("utf-8"))
            return

        if action == "template":
            team_arg = query.get("team", ["1"])[0]
            if team_arg == "daily":
                fields = fetch_daily_fields()
                now_mm = datetime.now(TZ_MM)
                lines  = [f"Daily result: {now_mm.strftime('%d/%m/%Y')}"]
                for i, f in enumerate(fields[1:], start=1):
                    lines.append(f"{i}. {f}:")
                template_text = "\n".join(lines)
            else:
                try:
                    team_num = int(team_arg)
                except ValueError:
                    team_num = 1
                template_text = get_plan_template_text(team_num)
                
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"template": template_text}).encode("utf-8"))
            return

        if TOKEN and not action:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                    json={"url": "https://tni-bot.vercel.app/api/search_bot", "allowed_updates": ["message", "edited_message", "channel_post"]},
                    timeout=5
                )
            except Exception:
                pass

        tok_ok  = "SET" if TOKEN else "MISSING"
        gas_ok  = "SET" if DAILY_APPS_SCRIPT_URL else "MISSING"
        log_val = APPS_SCRIPT_URL if APPS_SCRIPT_URL else "MISSING"
        log_ok  = f"SET (...{log_val[-15:]})" if APPS_SCRIPT_URL else "MISSING"
        msg = f"TNI Search Bot {BOT_VERSION} | TOKEN:{tok_ok} | DAILY_GAS:{gas_ok} | APPS_SCRIPT_URL:{log_ok}"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(msg.encode())

    def log_message(self, *a): pass
