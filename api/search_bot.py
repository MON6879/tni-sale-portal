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
BOT_VERSION = "v4.1"

# ── Config ────────────────────────────────────────────────────────────────────
SEARCH_BOT_TOKEN_SSOT = "8606383435:AAEstcN4Om6_9ZAjs4OoFV2uVlRALgae2Ac"
raw_tok = (os.environ.get("TELEGRAM_TOKEN") or os.environ.get("BOT_TOKEN") or os.environ.get("SEARCH_BOT_TOKEN") or "").strip().strip("\ufeff")
if not raw_tok or not raw_tok.startswith("8606383435"):
    TOKEN = SEARCH_BOT_TOKEN_SSOT
else:
    TOKEN = raw_tok
PRIMARY_GAS_URL       = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
DAILY_APPS_SCRIPT_URL = os.environ.get("DAILY_APPS_SCRIPT_URL", "").strip().strip("\ufeff")
APPS_SCRIPT_URL       = os.environ.get("APPS_SCRIPT_URL", "").strip().strip("\ufeff")
if not DAILY_APPS_SCRIPT_URL or "AKfycbz-NZlBk8q2" not in DAILY_APPS_SCRIPT_URL:
    DAILY_APPS_SCRIPT_URL = PRIMARY_GAS_URL
if not APPS_SCRIPT_URL or "AKfycbz-NZlBk8q2" not in APPS_SCRIPT_URL:
    APPS_SCRIPT_URL = PRIMARY_GAS_URL
SPREADSHEET_ID        = os.environ.get("SPREADSHEET_ID", "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8").strip().strip("\ufeff")
TELEGRAM_SECRET_TOKEN = os.environ.get("TELEGRAM_SECRET_TOKEN", "").strip()
SD_SPREADSHEET_ID     = "1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow"
BASE_URL              = (
    f"https://docs.google.com/spreadsheets/d/"
    f"{SPREADSHEET_ID}/export?format=csv&gid="
)
SD_BASE_URL           = (
    f"https://docs.google.com/spreadsheets/d/"
    f"{SD_SPREADSHEET_ID}/export?format=csv&gid="
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
    """Tra cứu WO Not Close (CD Not Yet Close A) cho Team T1..T4 từ Sheet TL_WaitCD."""
    df = fetch_single_csv(GID_TL_WAITCD)
    e = html.escape
    t_clean = team_code.upper().replace("TEAM", "T").strip()
    t_num = "".join(filter(str.isdigit, t_clean)) or "1"
    
    if df is None or df.empty:
        return [f"❌ No data for <b>T{e(t_num)}</b> not close"]

    results = []
    for _, row in df.iterrows():
        col_b = safe(row, 1).strip()
        if not col_b or col_b.lower() == "nan":
            continue
        col_c = safe(row, 2).strip()
        col_d = safe(row, 3).strip().lower()
        col_h = safe(row, 7).strip().lower()

        matched = False
        if f"team0{t_num}" in col_d or f"team {t_num}" in col_d or f"t{t_num}" in col_h:
            matched = True
        elif t_num == "1" and ("dawei" in col_d or "t1" in col_h):
            matched = True
        elif t_num == "2" and ("myeik" in col_d or "t2" in col_h):
            matched = True
        elif t_num == "3" and ("kawthaung" in col_d or "t3" in col_h):
            matched = True
        elif t_num == "4" and ("tanintharyi" in col_d or "kawthoung" in col_d or "t4" in col_h):
            matched = True

        if matched:
            col_a = safe(row, 0).strip()
            reason_str = f" | (Reason Code: {e(col_a)})" if col_a and col_a.lower() != "nan" else ""
            item_str = f"{e(col_b)} | {e(col_c)}{reason_str}"
            results.append(item_str)

    if not results:
        return [f"❌ No Not Close data for <b>T{e(t_num)}</b>"]

    header = f"📑 <b>CD NOT YET CLOSE WOs: T{e(t_num)} ({len(results)})</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    items_text = "\n".join(f"• {r}" for r in results)
    footer = "\n━━━━━━━━━━━━━━━━━━━━"
    return split_messages(header + items_text + footer)


def lookup_waitcd(team_code: str) -> list:
    """Tra cứu WO Wait CD (Col A có Reason Code) cho Team T1..T4 từ Sheet TL_WaitCD."""
    df = fetch_single_csv(GID_TL_WAITCD)
    e = html.escape
    t_clean = team_code.upper().replace("TEAM", "T").strip()
    t_num = "".join(filter(str.isdigit, t_clean)) or "1"
    
    if df is None or df.empty:
        return [f"⏳ No data for <b>T{e(t_num)}</b> wait CD"]

    results = []
    for _, row in df.iterrows():
        col_a = safe(row, 0).strip()
        if not col_a or col_a.lower() == "nan":
            continue
        col_b = safe(row, 1).strip()
        if not col_b or col_b.lower() == "nan":
            continue
        col_c = safe(row, 2).strip()
        col_d = safe(row, 3).strip().lower()
        col_h = safe(row, 7).strip().lower()

        matched = False
        if f"team0{t_num}" in col_d or f"team {t_num}" in col_d or f"t{t_num}" in col_h:
            matched = True
        elif t_num == "1" and ("dawei" in col_d or "t1" in col_h):
            matched = True
        elif t_num == "2" and ("myeik" in col_d or "t2" in col_h):
            matched = True
        elif t_num == "3" and ("kawthaung" in col_d or "t3" in col_h):
            matched = True
        elif t_num == "4" and ("tanintharyi" in col_d or "kawthoung" in col_d or "t4" in col_h):
            matched = True

        if matched:
            item_str = f"{e(col_b)} | {e(col_c)} | (Reason Code: {e(col_a)})"
            results.append(item_str)

    if not results:
        return [f"⏳ No Wait CD data for <b>T{e(t_num)}</b>"]

    header = f"⏳ <b>WAIT CD WOs: T{e(t_num)} ({len(results)})</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    items_text = "\n".join(f"• {r}" for r in results)
    footer = "\n━━━━━━━━━━━━━━━━━━━━"
    return split_messages(header + items_text + footer)

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
        {"command": "t1notclose",   "description": "Team 1 Not Close WOs"},
        {"command": "t2notclose",   "description": "Team 2 Not Close WOs"},
        {"command": "t3notclose",   "description": "Team 3 Not Close WOs"},
        {"command": "t4notclose",   "description": "Team 4 Not Close WOs"},
        {"command": "t1waitcd",     "description": "Team 1 Wait CD WOs"},
        {"command": "t2waitcd",     "description": "Team 2 Wait CD WOs"},
        {"command": "t3waitcd",     "description": "Team 3 Wait CD WOs"},
        {"command": "t4waitcd",     "description": "Team 4 Wait CD WOs"},
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
CSV_CACHE_TTL = 60  # 60 giây cache sống — đảm bảo cập nhật dữ liệu mới sau tối đa 1 phút

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
    try:
        resp = requests.get(url, headers=hdrs, timeout=5.0, allow_redirects=True)
        resp.raise_for_status()
        content = resp.content.decode("utf-8", errors="replace")
        df = pd.read_csv(io.StringIO(content), header=None, dtype=str, on_bad_lines="skip")
        _csv_cache[cache_key] = df
        _csv_cache_ts[cache_key] = time.time()
        return df
    except Exception as ex:
        logger.warning(f"fetch_single_csv error [gid={gid}]: {ex}")
        if cached is not None:
            logger.info(f"Returning stale cache for gid={gid}")
            return cached
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
        # ── 1. Fetch trực tiếp từ Google Sheets LIVE qua export CSV (~0.5s) ──
        logger.info("Fetching fresh index from Google Sheets LIVE...")
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

def linkify_text(text: str) -> str:
    """Format text: Y NGUYÊN 100% không thêm bất kỳ icon hay chữ nào."""
    if not text:
        return ""
    clean = html.escape(str(text).replace("&amp;gt;", ">").replace("&gt;", ">").replace("&amp;lt;", "<").replace("&lt;", "<"))
    def _url_sub(m):
        url = m.group(0)
        return f'<a href="{url}">{url}</a>'
    clean = re.sub(r'https?://[^\s<]+', _url_sub, clean)
    return clean

def e(s) -> str:
    return linkify_text(s)

def format_task_wo(raw: str) -> str:
    """Trả về Y NGUYÊN 100% dữ liệu gốc từ Google Sheet cell (0 icon thêm vào)."""
    if not raw:
        return ""
    clean_raw = str(raw).strip().lstrip("~ ").strip()
    return linkify_text(clean_raw)


def perform_unified_tni_search(tni: str, full_info: bool = False) -> str:
    """Tra cứu TNI O(1) — 100% Dữ liệu thô Y NGUYÊN từ Google Sheet (0 ICON thêm vào)."""
    tni_upper = tni.upper().strip()

    now = time.time()
    if not _tni_info_index:
        build_search_indexes(force=False)
    elif (now - _index_last_built) >= CSV_CACHE_TTL:
        trigger_bg_index_refresh()

    info    = _tni_info_index.get(tni_upper)
    task_wo = _tni_team_sum_index.get(tni_upper)

    has_info  = bool(info and any(info.values()))
    has_tasks = bool(task_wo)

    if not has_info and not has_tasks:
        return f"No data found for {html.escape(tni_upper)}"

    lines = []

    if full_info:
        # ✅ GHẾ INFO (Info: TNIxxxx / /info TNIxxxx): CHỈ trả về Hạ tầng (Site, Cable, GPON, DIA) từ tab Name Site (100% KHÔNG CHÈN Task/WO)
        if has_info:
            if info.get("site") and info['site'].strip():
                lines.append(linkify_text(info['site'].strip()))
            if info.get("cable") and info['cable'].strip():
                lines.append(linkify_text(info['cable'].strip()))
            if info.get("gpon") and info['gpon'].strip():
                lines.append(linkify_text(info['gpon'].strip()))
            if info.get("dia") and info['dia'].strip():
                lines.append(linkify_text(info['dia'].strip()))
        if not lines:
            return f"No Info data found for {html.escape(tni_upper)}"
    else:
        # ✅ GHẾ TNI (TNIxxxx): CHỈ trả về Task & WO từ tab Tên Sum WO (100% KHÔNG CHÈN Info Hạ tầng)
        if has_tasks:
            formatted = format_task_wo(task_wo)
            if formatted:
                lines.append(formatted)
        if not lines:
            return f"No Task/WO data found for {html.escape(tni_upper)}"

    return "\n\n".join(lines).strip()

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

    KNOWN_KEY_ALIASES = [
        "daily result", "daily report", "full name", "name", "transportation used", "transportation",
        "site rescue", "cell rescue", "rescue cable", "repair alarm", "partner refuel", "other task",
        "detail wo", "detail task", "wo", "task", "busines trip", "km moto bike"
    ]

    def flush():
        if cur_key:
            result[cur_key] = "\n".join(cur_val).strip()

    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        
        is_key_line = False
        label, val = "", ""
        if ":" in line:
            colon = line.index(":")
            lbl_candidate = line[:colon].strip()
            val_candidate = line[colon + 1:].strip()
            clean_cand = clean_field_name(lbl_candidate)
            
            # Kiểm tra xem label candidate có phải là từ khóa form hợp lệ không
            if any(alias in clean_cand or clean_cand in alias for alias in KNOWN_KEY_ALIASES):
                is_key_line = True
                label = lbl_candidate
                val = val_candidate

        if is_key_line:
            matched = None
            label_l = label.lower()
            clean_lbl = clean_field_name(label)
            
            if "result" in label_l or "daily" in label_l:
                for f in fields:
                    if f.lower() == "daily report" or f.lower() == "daily result":
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
                flush()
                cur_key = matched
                cur_val = [val] if val else []
                continue

        if cur_key:
            cur_val.append(line)
    flush()
    return result

def is_daily(text: str) -> bool:
    if not text:
        return False
    text_l = text.lower()
    
    # 🛑 1. CHẶN HẲN BÀI PLAN: Bài Plan của Team Leader BẮT BỘC bị loại trừ 100%
    if is_daily_plan(text):
        return False
    if any(kw in text_l for kw in ("daily plan", "plan:", "kế hoạch", "i. hot task", "above are the end-of-day", "auto report", "ref:dp-", "đã lưu", "team leader assign")):
        return False

    # 🟢 2. TỪ KHÓA NHẬN DẠNG CẤU TRÚC CHUẨN BÀI NỘP DAILY RESULT CỦA KỸ THUẬT VIÊN FT
    has_daily_kw = any(kw in text_l for kw in (
        "daily result", "daily result:", "daily report", "transportation used",
        "transportation", "detail wo:", "detail task:", "full name",
        "name site rescue", "name cell rescue", "resuce cable", "site repair alarm",
        "partner refuel", "other task:"
    ))
    
    return has_daily_kw


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
    # 1. Fetch from Template Attendance SSOT (18zQB4i0Fu4QfKKkkUZUd6SKWIEbdWDiwdpgNSaL9v54 gid=1366655674)
    try:
        import csv
        url = "https://docs.google.com/spreadsheets/d/18zQB4i0Fu4QfKKkkUZUd6SKWIEbdWDiwdpgNSaL9v54/gviz/tq?tqx=out:csv&gid=1366655674"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 200:
            reader = list(csv.reader(io.StringIO(resp.text)))
            team_col_map = {1: 5, 2: 6, 3: 7, 4: 8}
            col_idx = team_col_map.get(team_num, 5)
            names = []
            for r in reader[2:]:
                if len(r) > col_idx:
                    val = r[col_idx].strip()
                    if not val:
                        continue
                    clean = re.sub(r'^\d+[\.\s\-]+', '', val)
                    clean = re.sub(r':\s*/.*$', '', clean).strip()
                    clean = re.sub(r':\s*$', '', clean).strip()
                    if clean and clean not in names and clean.lower() not in ('nan', 'none', '-'):
                        names.append(clean)
            if names:
                return names
    except Exception as e:
        logger.warning(f"Error fetching staff from attendance template: {e}")

    # 2. Fallback to Staff sheet
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
        
        for i, name in enumerate(matched_staff, 1):
            lines.append(f"{i}. {name}: ")
            
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"get_plan_template_text error: {e}")
        return f"Error: {str(e)}"

_attendance_cache = {"time": 0, "data": None}

def get_attendance_template_text(team_num: int = None, header_only: bool = False) -> str:
    """Tải động mẫu điểm danh từ tab Template Attendance của Spreadsheet 18zQB4i0Fu4QfKKkkUZUd6SKWIEbdWDiwdpgNSaL9v54 (gid=1366655674)."""
    global _attendance_cache
    now_ts = time.time()
    df = None
    
    if _attendance_cache["data"] is not None and now_ts - _attendance_cache["time"] < 60:
        df = _attendance_cache["data"]
    else:
        try:
            url = "https://docs.google.com/spreadsheets/d/18zQB4i0Fu4QfKKkkUZUd6SKWIEbdWDiwdpgNSaL9v54/gviz/tq?tqx=out:csv&gid=1366655674"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if resp.status_code == 200:
                df = pd.read_csv(io.StringIO(resp.text), header=None)
                _attendance_cache = {"time": now_ts, "data": df}
        except Exception as e:
            logger.error(f"Error fetching attendance template: {e}")
            if _attendance_cache["data"] is not None:
                df = _attendance_cache["data"]
    
    if df is None:
        return "⚠️ Could not load attendance template from Google Sheets."

    team_col_map = {1: 5, 2: 6, 3: 7, 4: 8}
    now_mm = datetime.now(TZ_MM)
    date_short = now_mm.strftime("%d/%m/%y")

    def extract_team_lines(t):
        col_idx = team_col_map.get(t)
        if col_idx is None or col_idx >= df.shape[1]:
            return []
        lines = []
        for r in range(len(df)):
            v = df.iloc[r, col_idx]
            if pd.notna(v) and str(v).strip() != "":
                v_str = str(v).strip()
                if v_str.lower().startswith("total:"):
                    continue
                if r == 0 and "report:" in v_str.lower():
                    v_str = f"Team 0{t} Attendane report: {date_short}"
                lines.append(v_str)
                if header_only and len(lines) >= 1:
                    break
        return lines

    if team_num in team_col_map:
        lines = extract_team_lines(team_num)
        if not lines:
            return f"⚠️ No template found for Team {team_num}."
        return "\n".join(lines)
    else:
        all_blocks = []
        for t in (1, 2, 3, 4):
            lines = extract_team_lines(t)
            if lines:
                all_blocks.append("\n".join(lines))
        if header_only:
            return "\n".join(all_blocks)
        return "\n\n".join(all_blocks)


def get_leave_template_text(leave_type: str = None) -> str:
    """Tải động 2 mẫu xin nghỉ phép (Cột A: Half Day, Cột B: Full Day) từ tab Template Attendance."""
    global _attendance_cache
    now_ts = time.time()
    df = None
    
    if _attendance_cache["data"] is not None and now_ts - _attendance_cache["time"] < 60:
        df = _attendance_cache["data"]
    else:
        try:
            url = "https://docs.google.com/spreadsheets/d/18zQB4i0Fu4QfKKkkUZUd6SKWIEbdWDiwdpgNSaL9v54/gviz/tq?tqx=out:csv&gid=1366655674"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if resp.status_code == 200:
                df = pd.read_csv(io.StringIO(resp.text), header=None)
                _attendance_cache = {"time": now_ts, "data": df}
        except Exception as e:
            logger.error(f"Error fetching leave template: {e}")
            if _attendance_cache["data"] is not None:
                df = _attendance_cache["data"]
    
    if df is None:
        return "⚠️ Could not load leave template from Google Sheets."

    def extract_col_lines(c_idx):
        if c_idx >= df.shape[1]:
            return []
        lines = []
        for r in range(len(df)):
            v = df.iloc[r, c_idx]
            if pd.notna(v) and str(v).strip() != "":
                lines.append(str(v).strip())
        return lines

    col_a = extract_col_lines(0)
    col_b = extract_col_lines(1)

    str_a = "\n".join(col_a) if col_a else "Full Name: take leave half day\nReason:"
    str_b = "\n".join(col_b) if col_b else "Full Name: Take leave\nReason:"

    if leave_type == "half":
        return str_a
    elif leave_type == "all" or leave_type == "both":
        return f"{str_a}\n\n{str_b}"
    else:
        # Default: Full-day leave (Col B)
        return str_b



_processed_attendance_msg_ids = set()

def is_attendance_report(text: str) -> bool:
    if not text:
        return False
    text_l = text.lower().strip()
    if re.search(r"team\s*0?[1-4]\s*attendan[ce]+\s*report", text_l):
        return True
    if re.match(r"^[^:\n]+:\s*take\s*leave", text_l):
        return True
    return False

def parse_attendance_report(text: str, default_tg_id: str = "") -> list:
    records = []
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return []
    
    # 1. Team Leader Attendance report (Multi-person)
    m_team = re.search(r"team\s*0?([1-4])\s*attendan[ce]+\s*report[:\s]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", lines[0], re.IGNORECASE)
    if m_team:
        date_str = m_team.group(2)
        current_rec = None
        for line in lines[1:]:
            m_p = re.match(r"^(?:\d+[\.\)]\s*)?([^:]+):\s*(.*)$", line)
            if m_p and not m_p.group(1).lower().startswith("reason") and not m_p.group(1).lower().startswith("total"):
                if current_rec:
                    records.append(current_rec)
                p_name = m_p.group(1).strip()
                p_stat = m_p.group(2).strip().lower()
                work = "Work" if "work" in p_stat and "leave" not in p_stat else ""
                half_day = "Half day" if "half" in p_stat else ""
                take_leave = "Take leave" if "leave" in p_stat and "half" not in p_stat else ""
                current_rec = {
                    "date": date_str,
                    "name": p_name,
                    "work": work,
                    "takeLeave": take_leave,
                    "halfDay": half_day,
                    "reason": "",
                    "telegramId": ""
                }
            elif line.lower().startswith("reason:") and current_rec:
                current_rec["reason"] = line.split(":", 1)[1].strip()
        if current_rec:
            records.append(current_rec)
        return records

    # 2. Individual leave / half day format
    m_indiv = re.match(r"^([^:]+):\s*take\s*leave(?:\s*(half\s*day|full\s*day))?", lines[0], re.IGNORECASE)
    if m_indiv:
        name = m_indiv.group(1).strip()
        hd_match = m_indiv.group(2)
        half_day = "Half day" if (hd_match and "half" in hd_match.lower()) or "half" in lines[0].lower() else ""
        take_leave = "Take leave" if not half_day else ""
        reason = ""
        for line in lines[1:]:
            if line.lower().startswith("reason:"):
                reason = line.split(":", 1)[1].strip()
        now_mm = datetime.now(TZ_MM)
        date_str = now_mm.strftime("%d/%m/%Y")
        records.append({
            "date": date_str,
            "name": name,
            "work": "",
            "takeLeave": take_leave,
            "halfDay": half_day,
            "reason": reason,
            "telegramId": str(default_tg_id or "")
        })
        return records

    return []

def store_attendance_to_sheet(items: list) -> dict:
    try:
        url = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
        payload = {
            "action": "attendance_add",
            "items": items
        }
        resp = requests.post(url, json=payload, timeout=10)
        return resp.json()
    except Exception as e:
        logger.error(f"store_attendance_to_sheet error: {e}")
        return {"status": "error", "message": str(e)}


def is_daily_plan(text: str) -> bool:
    """
    Detect Daily Plan message submitted by Team Leaders.
    Structure: Starts with/Contains 'Daily Plan: DD/MM/YYYY', 'Team X', 'I. Hot task'.
    """
    if not text:
        return False
    text_l = text.lower().strip()

    # 🛑 BỎ QUA 100% CÁC CÚ PHÁP TRA CỨU (TNI, Info, Clear, Cons, NotClose, WaitCD) — KHÔNG THỂ THÀNH DAILY PLAN
    if text_l.startswith("tni") or text_l.startswith("/tni") or text_l.startswith("info") or text_l.startswith("/info") or text_l.startswith("clear") or text_l.startswith("/clear") or text_l.startswith("cons") or text_l.startswith("/cons") or "notclose" in text_l or "waitcd" in text_l:
        return False

    # Blacklist of bot outputs/reports to avoid self-triggering
    if any(kw in text_l for kw in (
        "5.1 report", "5. report", "4. report", "report 4", "refuel plan",
        "comparison of plan for", "auto report", "plan stats:", "report — daily plan",
        "crosscheck", "plan tomorrow status", "plan vs actual", "eod summary",
        "shows detailed site assignments", "tasks grouped by department", "recent plans",
        "plan updated", "plan saved", "ref:dp-", "đã lưu",
        "tni personal find task", "ft result daily", "personal find task", "find task + wo",
        "submitted ✓", "submitted v", "not yet submitted", "3. tni personal",
        "sent folow menu", "follow menu", "all material using new or move"
    )):
        return False

    # BẮT BUỘC: Phải có Tiêu đề 'Daily Plan: DD/MM/YYYY' (hoặc 'Plan for DD/MM/YYYY') VÀ có 'Team'
    has_header = bool(re.search(r'(?:daily\s*plan|plan\s*for)[:\s]+\d{1,2}[\/\.-]\d{1,2}(?:[\/\.-]\d{2,4})?', text, re.IGNORECASE))
    has_team = bool(re.search(r'\bteam\s*0?[1-5]\b|\bt[1-5]\b', text, re.IGNORECASE))

    return has_header and has_team


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
        if not title_m:
            title_m = re.search(r'T([1-5])\b', chat_title, re.IGNORECASE)
        if title_m:
            team_str = f"Team {title_m.group(1)}"
    if not team_str and chat_id:
        def norm_id(cid): return str(cid).replace("-100", "").replace("-", "")
        for tk, gid in TELEGRAM_GROUPS.items():
            if norm_id(chat_id) == norm_id(gid):
                team_num = tk.replace("T", "")
                team_str = f"Team {team_num}"
                break
    if not team_str:
        team_str = "Team 1"  # Fallback safety default

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


_processed_plan_msg_ids = set()

def store_daily_plan_to_sheet(date_str: str, team_str: str, content: str, msg_id: int = None) -> dict:
    url = DAILY_APPS_SCRIPT_URL or APPS_SCRIPT_URL or "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
    payload = {
        "action": "store_daily_plan",
        "date": date_str,
        "team": team_str,
        "content": content,
        "daily_report": "",
        "comparison": "",
        "msg_id": str(msg_id) if msg_id else ""
    }
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=35)
            if r.status_code == 200:
                data = r.json()
                if data.get("ref"):
                    return data
        except Exception as e:
            logger.warning(f"store_daily_plan_to_sheet attempt {attempt+1} error: {e}")
            time.sleep(1)
    return {}


def fetch_max_plan_ref() -> str:
    """Fallback: Fetch max existing DP-xxx from Sheet and return next REF (e.g. DP-166)."""
    SPREADSHEET_ID_PLAN = "1C8hU8SXpOdq-v6z7iLGoqwDJmO9DYudZ3rhflb7LC8Y"
    csv_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID_PLAN}/gviz/tq?tqx=out:csv&sheet=Team%20leader%20assign%20Plan"
    try:
        r = requests.get(csv_url, timeout=10)
        if r.status_code == 200:
            max_num = 0
            for line in r.text.splitlines()[1:]:
                m = re.search(r'DP-(\d+)', line)
                if m:
                    val = int(m.group(1))
                    if val > max_num:
                        max_num = val
            if max_num > 0:
                return f"DP-{str(max_num + 1).zfill(3)}"
    except Exception as e:
        logger.warning(f"fetch_max_plan_ref error: {e}")
    return f"DP-{int(time.time()) % 1000:03d}"


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
        "<b>[TOA 9] Attendance & Form Templates</b>\n"
        "• Type: <code>template attendance</code>, <code>template leave</code>, <code>template team 1-4</code>, <code>template header</code>, <code>daily</code>, <code>plan</code>\n\n"
        "<b>[TOA 10] Help & Interactive Menu</b>\n"
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

        header_lines = [f"🔍 <b>Clear History for {html.escape(tni_u)}</b>", "━━━━━━━━━━━━━━━━━━━━"]
        history_lines = []

        for r in range(len(df)):
            row = df.iloc[r]
            val = safe(row, col_idx)
            label = str(row.iloc[0]).strip() if len(row) > 0 else ""

            if not val or val.lower() in ("nan", "-", ""):
                continue

            # Bỏ qua ô chứa chính mã trạm trong bảng
            if val.upper() == tni_u:
                if label and label.lower() != "nan":
                    header_lines.append(f"• <b>Status:</b> {html.escape(label)}")
                continue

            if label and label.lower() != "nan":
                header_lines.append(f"• <b>{html.escape(label)}:</b> {html.escape(val)}")
            else:
                history_lines.append(f"• {html.escape(val)}")

        result_parts = list(header_lines)
        if history_lines:
            result_parts.append("\n<b>📜 History Records:</b>")
            cur_len = sum(len(x) for x in result_parts)
            for h_line in history_lines:
                if cur_len + len(h_line) + 2 > 3800:
                    result_parts.append("• <i>... (more older records truncated)</i>")
                    break
                result_parts.append(h_line)
                cur_len += len(h_line) + 1
        else:
            result_parts.append("• <i>No history records found</i>")

        return "\n".join(result_parts)
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

def send_ingestion_alarm(sheet_name: str, group_name: str, user_info: str, reason: str):
    """GHẾ 9.1: Báo động thu thập dữ liệu/ảnh Google Sheet thất bại về Nhóm 9 (9 TNI REQUEST REFUEL)."""
    refuel_req_chat_id = -5469544739
    now_str = datetime.now(TZ_MM).strftime('%d/%m/%Y %H:%M:%S')
    msg = (
        f"🚨 <b>[CẢNH BÁO THU THẬP LỖI - GHẾ 9.1]</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"❌ <b>Tên Sheet không thu thập được thông tin:</b>\n"
        f"<code>{html.escape(sheet_name)}</code>\n\n"
        f"📱 <b>Nhóm / Người nộp:</b> {html.escape(group_name)} ({html.escape(user_info)})\n"
        f"⏱️ <b>Thời gian kiểm tra:</b> {now_str} MMT\n"
        f"⚠️ <b>Nguyên nhân lỗi:</b> {html.escape(reason[:150])}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    try:
        tg_send(refuel_req_chat_id, msg)
    except Exception as e:
        logger.error(f"send_ingestion_alarm error: {e}")

def fetch_max_result_ref() -> str:
    """Fallback: Fetch max existing numeric REF from Daily report and Bussiness sheet."""
    SPREADSHEET_ID_NEW = "1C8hU8SXpOdq-v6z7iLGoqwDJmO9DYudZ3rhflb7LC8Y"
    csv_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID_NEW}/gviz/tq?tqx=out:csv&gid=2037920194"
    try:
        r = requests.get(csv_url, timeout=10)
        if r.status_code == 200:
            max_num = 0
            for line in r.text.splitlines()[1:]:
                parts = line.split(",")
                if parts:
                    clean = parts[0].replace('"', '').strip()
                    if clean.isdigit():
                        val = int(clean)
                        if val > max_num:
                            max_num = val
            if max_num > 0:
                return str(max_num + 1)
    except Exception as e:
        logger.warning(f"fetch_max_result_ref error: {e}")
    return "265"


def submit_daily(chat_id: int, user_id: int, first_name: str, text: str, msg_date: int | None = None) -> None:
    now_ts = time.time()
    dedup_key = f"{user_id}:{text.strip()[:60]}"
    if (now_ts - _recent_daily_submits.get(dedup_key, 0)) < 10.0:
        logger.info(f"Skipping duplicate submit_daily for user {user_id}")
        return
    _recent_daily_submits[dedup_key] = now_ts

    fields = fetch_daily_fields()
    parsed = parse_daily_report(text, fields)
    now_mm = datetime.fromtimestamp(msg_date, TZ_MM) if msg_date else datetime.now(TZ_MM)
    time_str = now_mm.strftime('%H:%M')
    date_str = parsed.get("Daily report") or now_mm.strftime("%d/%m/%Y")

    url = DAILY_APPS_SCRIPT_URL or APPS_SCRIPT_URL or "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
    name = first_name or str(user_id)
    ref_str = ""

    try:
        resp = requests.post(url,
                             json={"action": "daily_add",
                                   "telegram_id": str(user_id),
                                   "user_name": name,
                                   "fields": parsed},
                             timeout=35)
        if resp.status_code == 200:
            try:
                result = resp.json()
                if result.get("status") == "ok":
                    name = result.get("name") or name
                    ref_str = str(result.get("ref", "")).strip()
            except Exception as parse_ex:
                logger.info(f"submit_daily non-json ok: {name}")
    except Exception as ex:
        logger.error(f"submit_daily requests error: {ex}")

    if not ref_str or ref_str == "?" or "OK" in ref_str:
        ref_str = fetch_max_result_ref()

    logger.info(f"submit_daily ok: {name} (ref={ref_str})")
    tg_send(chat_id, f"✅ <b>Result saved ({time_str})</b> — REF:<b>{ref_str}</b> | {date_str}")

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



_processed_updates = {}

# ── Update handler ────────────────────────────────────────────────────────────
def handle(update: dict) -> None:
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

    text_l = text.lower().strip()
    if any(kw in text_l for kw in ("request enter site", "request site enter", "site access format", "site access", "site enter")):
        parts = text.split(maxsplit=1)
        passed_site = parts[1].upper().strip() if len(parts) > 1 and parts[1].upper().startswith("TNI") else "TNI0401"
        reply = get_site_access_template(passed_site)
        tg_send(chat_id, reply)
        return

    # Plain text command for Attendance Template (Strict Exact/Prefix Matching, Max 3 words)
    is_att_tpl = (
        text_l in ("template attendance", "attendance template", "template attend", "template diemdanh", "template att", "/attendance", "/att", "/diemdanh")
        or (text_l.startswith("template team") or text_l.startswith("template t") or text_l.startswith("/template_team"))
    ) and len(text_l.split()) <= 3
    if is_att_tpl:
        header_only = any(kw in text_l for kw in ("header", "title", "tieude", "short"))
        team_num = None
        if re.search(r"team\s*0?1|\bt1\b|_team1\b|team_1\b|template_team1\b|\b1\b", text_l):
            team_num = 1
        elif re.search(r"team\s*0?2|\bt2\b|_team2\b|team_2\b|template_team2\b|\b2\b", text_l):
            team_num = 2
        elif re.search(r"team\s*0?3|\bt3\b|_team3\b|team_3\b|template_team3\b|\b3\b", text_l):
            team_num = 3
        elif re.search(r"team\s*0?4|\bt4\b|_team4\b|team_4\b|template_team4\b|\b4\b", text_l):
            team_num = 4
        reply = get_attendance_template_text(team_num, header_only=header_only)
        tg_send(chat_id, reply)
        return

    # Plain text command for Leave Template (Xin nghỉ phép: Cột A & B — Strict Matching)
    is_leave_tpl = (
        text_l in ("template leave", "leave template", "template take leave", "take leave", "/leave", "leave half day", "leave full day", "xin nghi", "xin phep")
        or (text_l.startswith("template leave") or text_l.startswith("leave template"))
    ) and len(text_l.split()) <= 3
    if is_leave_tpl:
        l_type = "half" if "half" in text_l else ("full" if "full" in text_l else None)
        reply = get_leave_template_text(l_type)
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

        if first_word in ("start", "help", "menu"):
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
                team_arg = rest.upper().strip()
                m = re.match(r"^(T(?:EAM)?\s*([1-4])|[1-4])$", team_arg, re.IGNORECASE)
                if m:
                    team_num = int(m.group(2) if m.group(2) else m.group(1))
            if not team_num:
                chat_title = (msg.get("chat", {}).get("title") or "").lower()
                cid_str = str(chat_id)
                if "4215695747" in cid_str or "team 1" in chat_title or "dawei" in chat_title:
                    team_num = 1
                elif "4480845549" in cid_str or "team 2" in chat_title or "myeik" in chat_title:
                    team_num = 2
                elif "4369170658" in cid_str or "team 3" in chat_title or "bokpyin" in chat_title:
                    team_num = 3
                elif "4293741999" in cid_str or "team 4" in chat_title or "kawthoung" in chat_title:
                    team_num = 4
                else:
                    team_num = get_user_team_number(user_id) or 1
            send_daily_plan_template(chat_id, team_num)
            return

        if first_word in ("id", "myid"):
            chat_title = msg["chat"].get("title") or first_name or "Private"
            chat_type  = msg["chat"].get("type", "private")
            tg_send(chat_id, f"👤 <b>{html.escape(first_name)}</b>\n🔑 ID: <code>{user_id}</code>\n💬 Chat: <code>{chat_id}</code>\n📍 Type: {chat_type}")
            return

        if first_word in ("attendance", "attend", "diemdanh", "att") or first_word.startswith("template_team") or first_word.startswith("template_t") or (first_word == "template" and ("attend" in rest.lower() or "diemdanh" in rest.lower() or "att" in rest.lower())):
            full_cmd = f"{first_word} {rest}".lower()
            header_only = any(kw in full_cmd for kw in ("header", "title", "tieude", "short"))
            team_num = None
            if re.search(r"team\s*0?1|\bt1\b|_team1\b|team_1\b|template_team1\b|\b1\b", full_cmd):
                team_num = 1
            elif re.search(r"team\s*0?2|\bt2\b|_team2\b|team_2\b|template_team2\b|\b2\b", full_cmd):
                team_num = 2
            elif re.search(r"team\s*0?3|\bt3\b|_team3\b|team_3\b|template_team3\b|\b3\b", full_cmd):
                team_num = 3
            elif re.search(r"team\s*0?4|\bt4\b|_team4\b|team_4\b|template_team4\b|\b4\b", full_cmd):
                team_num = 4
            reply = get_attendance_template_text(team_num, header_only=header_only)
            tg_send(chat_id, reply)
            return

        if first_word in ("leave", "takeleave", "xinnghi", "nghiphep") or (first_word == "template" and any(k in rest.lower() for k in ("leave", "nghi", "phep"))):
            l_type = "half" if "half" in rest.lower() else ("full" if "full" in rest.lower() else None)
            reply = get_leave_template_text(l_type)
            tg_send(chat_id, reply)
            return

        if first_word == "reload":
            load_all_sheets()
            tg_send(chat_id, "✅ Data reloaded")
            return

        clean_text = f"{first_word} {rest}".strip()

    # ── 0. ATTENDANCE & LEAVE REPORT SUBMIT (PRIORITY #0: Process attendance/leave reports & split per person) ──
    if is_attendance_report(clean_text) or is_attendance_report(text):
        msg_id = msg.get("message_id")
        if msg_id and msg_id in _processed_attendance_msg_ids:
            logger.info(f"Skipping duplicate Attendance webhook msg_id={msg_id}")
            return
        if msg_id:
            _processed_attendance_msg_ids.add(msg_id)
            if len(_processed_attendance_msg_ids) > 500:
                _processed_attendance_msg_ids.clear()

        att_items = parse_attendance_report(text, default_tg_id=str(user_id or ""))
        if att_items:
            res = store_attendance_to_sheet(att_items)
            count = len(att_items)
            msg_date = msg.get("date")
            now_mm = datetime.fromtimestamp(msg_date, TZ_MM) if msg_date else datetime.now(TZ_MM)
            time_str = now_mm.strftime('%H:%M')
            tg_send(chat_id, f"✅ <b>Attendance saved ({time_str})</b> — Recorded {count} staff to Sheet.")
            return

    # ── 1. DAILY PLAN SUBMIT (PRIORITY #1: Process plan BEFORE SSOT classify to prevent TNI code hijacking) ──
    if is_daily_plan(clean_text) or is_daily_plan(text):
        msg_id = msg.get("message_id")
        if msg_id and msg_id in _processed_plan_msg_ids:
            logger.info(f"Skipping duplicate Daily Plan webhook msg_id={msg_id}")
            return
        if msg_id:
            _processed_plan_msg_ids.add(msg_id)
            if len(_processed_plan_msg_ids) > 500:
                _processed_plan_msg_ids.clear()

        chat_title = msg.get("chat", {}).get("title", "")
        date_str, team_str, content = parse_plan_fields(text, chat_id, chat_title)
        if date_str and team_str:
            res = store_daily_plan_to_sheet(date_str, team_str, text, msg_id=msg_id)
            ref = res.get("ref")
            dup = res.get("duplicate", False)

            # 🛑 Nếu GAS xác nhận đây là bản trùng (đã lưu bởi instance Vercel khác) → bỏ qua, không gửi confirmation
            if dup:
                logger.info(f"GAS returned duplicate=true for msg_id={msg_id}, skipping confirmation")
                return

            if not ref or ref == "?" or "OK" in str(ref):
                ref_show = fetch_max_plan_ref()
            else:
                ref_show = ref

            msg_date = msg.get("date")
            now_mm = datetime.fromtimestamp(msg_date, TZ_MM) if msg_date else datetime.now(TZ_MM)
            time_str = now_mm.strftime('%H:%M')

            tg_send(chat_id, f"📋 <b>Daily Plan</b> ✅ #<b>{ref_show}</b> | 📍 <b>{team_str}</b> | 🗓️ <b>{date_str} {time_str}</b>")
            return

    # ── 2. DAILY REPORT SUBMIT (PRIORITY #2: Process daily report BEFORE SSOT classify) ──
    if is_daily(clean_text) or is_daily(text):
        msg_date = msg.get("date")
        submit_daily(chat_id, user_id, first_name, text, msg_date)
        return

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
        chunks = lookup_notclose(code)
        for chunk in chunks: tg_send(chat_id, chunk)
        return

    if action == "WAITCD":
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"WAITCD:{code}"): return
        log_search_bg(first_name or str(user_id), user_id, f"{code}waitcd")
        chunks = lookup_waitcd(code)
        for chunk in chunks: tg_send(chat_id, chunk)
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
            for chunk in messages:
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
            for chunk in messages:
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
        logger.info(f"[SSOT Router] Detailed Info lookup (Ghế Info): {tni} | chat={chat_id}")
        log_search_bg(first_name or str(user_id), user_id, f"Info:{tni}")
        try:
            # ✅ GHẾ INFO ĐỘC LẬP 100%: Tra cứu Thông tin Hạ tầng đầy đủ (Site, Cable, GPON, DIA) từ tab Name Site
            result = perform_unified_tni_search(tni, full_info=True)
            for chunk in split_messages(result):
                tg_send(chat_id, chunk)
        except Exception as err:
            logger.error(f"Detailed Info lookup error [{tni}]: {err}")
            tg_send(chat_id, f"❌ Lookup error: {html.escape(str(err))}")
        return

    # ── 3. KEY "TNI" SEARCH: TNIxxxx / TNIxxxx_01 / /tni TNIxxxx ───────────────────
    if action == "TNI":
        tni = code
        if is_duplicate_search and is_duplicate_search(chat_id, user_id, f"TNI:{tni}"):
            return
        logger.info(f"[SSOT Router] Unified TNI lookup (Ghế TNI): {tni} | chat={chat_id}")
        log_search_bg(first_name or str(user_id), user_id, tni)
        try:
            # ✅ GHẾ TNI ĐỘC LẬP 100%: Chỉ tra cứu Task & WO tương ứng
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

_processed_updates = {}   # update_id -> timestamp

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

            # ── Deduplication for Telegram Retries (TTL = 15 seconds) ──
            update_id = data.get("update_id")
            now_ts = time.time()
            if update_id:
                # Cleanup stale entries older than 15s
                stale_uids = [uid for uid, ts in list(_processed_updates.items()) if now_ts - ts > 15]
                for uid in stale_uids:
                    _processed_updates.pop(uid, None)

                if update_id in _processed_updates:
                    logger.info(f"Skipping duplicate Telegram update_id: {update_id}")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                    return
                _processed_updates[update_id] = now_ts

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
            # ⚡ Synchronous Processing: handle() runs in main thread
            #    takes < 0.05s, guaranteeing Vercel never freezes thread
            # ══════════════════════════════════════════════════════════
            try:
                handle(data)
            except Exception as ex:
                logger.error(f"handle() error: {ex}")
                try:
                    import traceback
                    tb = traceback.format_exc()
                    msg_obj = data.get("message") or data.get("edited_message") or {}
                    chat_id = msg_obj.get("chat", {}).get("id")
                    if chat_id:
                        tg_send(chat_id, f"⚠️ <b>Error:</b>\n<pre>{html.escape(tb[:2000])}</pre>")
                except Exception:
                    pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

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
                    json={"drop_pending_updates": False}, timeout=10).json()
                r2 = requests.post(f"{TG_API}/setWebhook",
                    json={
                        "url": expected,
                        "allowed_updates": ["message", "edited_message", "channel_post"],
                        "drop_pending_updates": False
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
