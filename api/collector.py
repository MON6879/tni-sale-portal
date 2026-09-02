"""
Vercel webhook handler for Collector Bot (TNIAsset_BO).

Routing:
  - TNI CABLE ROUTE group  (CABLE_CHAT_ID) → handle_cable()
  - 6. TNI Run MDG + Invetory Fuel (MDG_CHAT_ID) → handle_mdg()
  - All other chats                         → existing Asset handler

Webhook URL: https://tni-bot.vercel.app/api/collector
"""
import os, re, json, asyncio, logging, requests, html, base64, time
from http.server import BaseHTTPRequestHandler
from telegram import Bot, Update
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COLLECTOR_BOT_TOKEN   = os.environ.get("COLLECTOR_BOT_TOKEN", "").strip().strip("\ufeff")
APPS_SCRIPT_URL        = os.environ.get("APPS_SCRIPT_URL", "").strip().strip("\ufeff")
CABLE_APPS_SCRIPT_URL  = os.environ.get("CABLE_APPS_SCRIPT_URL", "").strip().lstrip('\ufeff')

MAIN_GAS_FALLBACK = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
if not APPS_SCRIPT_URL or "AKfycbz-NZlBk8q2" not in APPS_SCRIPT_URL:
    APPS_SCRIPT_URL = MAIN_GAS_FALLBACK

try:
    CABLE_CHAT_ID = int(os.environ.get("CABLE_CHAT_ID", "-5531350787").strip())
except ValueError:
    CABLE_CHAT_ID = -5531350787

MDG_APPS_SCRIPT_URL = os.environ.get("MDG_APPS_SCRIPT_URL", "").strip().lstrip('\ufeff')
if not MDG_APPS_SCRIPT_URL or "AKfycbz-NZlBk8q2" not in MDG_APPS_SCRIPT_URL:
    MDG_APPS_SCRIPT_URL = MAIN_GAS_FALLBACK

try:
    MDG_CHAT_ID = int(os.environ.get("MDG_CHAT_ID", "-5412512982").strip())
except ValueError:
    MDG_CHAT_ID = -5412512982

TZ_VN = timezone(timedelta(hours=7))
TZ_MM = timezone(timedelta(hours=6, minutes=30))   # Myanmar UTC+6:30

KEYWORDS_DEFAULT = ["order", "revoke", "export", "move", "asset sent", "destroys"]

# ── Cable constants ──────────────────────────────────────────────────────
CABLE_TYPE_KEYWORDS = ["request change", "rescue", "maintenance", "deploy"]
CABLE_FIELDS_LIST   = [
    "incident name", "physical route", "total cable length",
    "cable owner", "responsible branch", "rca",
    "team name", "wo", "materials list",
]
_keywords_cache = None
_config_templates_cache = None
_config_templates_ts = 0
_last_daily_sync_date = ""

def fetch_config_templates(force: bool = False) -> dict:
    """Fetch Column A (A2:A) from 'Config' tab (gid=1236389870) in Google Sheet 1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8.
    Automatically refreshes every 5 minutes (300 seconds) or when forced.
    """
    global _config_templates_cache, _config_templates_ts, _last_daily_sync_date, _keywords_cache
    now = time.time()
    
    # 5-minute cache TTL (Pillar 1: Tight Sliding Window Timing)
    if not force and _config_templates_cache and (now - _config_templates_ts < 300):
        return _config_templates_cache

    try:
        url = (
            "https://docs.google.com/spreadsheets/d/"
            "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8"
            "/gviz/tq?tqx=out:csv&gid=1236389870&tq=select+A"
        )
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        import csv, io
        rows = list(csv.reader(io.StringIO(resp.text)))
        lines = []
        mapping = {}
        keywords = []
        for row in rows[1:]:  # Skip Header 'Field Name'
            val = (row[0] if row else "").strip()
            if not val or val.lower() == "field name":
                continue
            lines.append(val)
            if ":" in val:
                kw = val.split(":")[0].strip().lower()
                mapping[kw] = val
                if kw not in keywords:
                    keywords.append(kw)
            else:
                first_word = val.split()[0].strip().lower()
                mapping[first_word] = val
                if first_word not in keywords:
                    keywords.append(first_word)
        if lines:
            _config_templates_cache = {"all": lines, "map": mapping}
            _config_templates_ts = now
            _keywords_cache = keywords
            logger.info(f"Loaded {len(lines)} templates from Config sheet A2:A")
            return _config_templates_cache
    except Exception as e:
        logger.warning(f"Config templates load failed: {e}")

    if _config_templates_cache:
        return _config_templates_cache
    return {"all": [], "map": {}}

_change_oil_template_cache = None
_change_oil_template_ts = 0

def fetch_change_oil_template(force: bool = False) -> str:
    """Fetch Column F from 'Cable permit ID' tab in Google Sheet 1C8hU8SXpOdq-v6z7iLGoqwDJmO9DYudZ3rhflb7LC8Y."""
    global _change_oil_template_cache, _change_oil_template_ts
    now = time.time()
    if not force and _change_oil_template_cache and (now - _change_oil_template_ts < 300):
        return _change_oil_template_cache

    try:
        url = "https://docs.google.com/spreadsheets/d/1C8hU8SXpOdq-v6z7iLGoqwDJmO9DYudZ3rhflb7LC8Y/gviz/tq?tqx=out:csv&sheet=Cable%20permit%20ID"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 200:
            import csv, io
            rows = list(csv.reader(io.StringIO(resp.text)))
            lines = []
            now_mm = datetime.now(TZ_MM)
            date_today = now_mm.strftime("%d/%m/%Y")
            for r in rows:
                if len(r) > 5 and r[5].strip():
                    line = r[5].strip()
                    if line.lower().startswith("change oil mdg:"):
                        line = f"Change Oil MDG: {date_today}"
                    lines.append(line)
            if lines:
                _change_oil_template_cache = "\n".join(lines)
                _change_oil_template_ts = now
                return _change_oil_template_cache
    except Exception as ex:
        logger.warning(f"fetch_change_oil_template error: {ex}")

    if _change_oil_template_cache:
        return _change_oil_template_cache
    now_mm = datetime.now(TZ_MM)
    date_today = now_mm.strftime("%d/%m/%Y")
    return f"Change Oil MDG: {date_today}\nSite MDG: \nType oil: \nHour for MDG 8KVA: \nKW for MDG 8KVA: \nNote: "

def sync_telegram_menu_commands(force: bool = False) -> bool:
    """Sync Telegram Bot Menu Commands directly from Google Sheet Config Tab Column A in EXACT order."""
    if not COLLECTOR_BOT_TOKEN:
        return False
    data = fetch_config_templates(force=force)
    lines = data.get("all", [])
    if not lines:
        return False
    
    commands = []
    seen = set()
    for l in lines:
        first_part = l.split(":")[0].strip() if ":" in l else l.split()[0].strip()
        cmd = first_part.lower().replace(" ", "_").replace("-", "_")
        cmd = "".join(c for c in cmd if c.isalnum() or c == "_")[:32]
        if cmd and cmd not in seen and cmd != "field_name":
            seen.add(cmd)
            desc = f"Get {first_part} template"
            commands.append({"command": cmd, "description": desc[:256]})

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{COLLECTOR_BOT_TOKEN}/setMyCommands",
            json={"commands": commands},
            timeout=10
        )
        logger.info(f"Telegram setMyCommands sync ({len(commands)} commands in exact sheet order): {r.json()}")
        return True
    except Exception as ex:
        logger.error(f"Telegram setMyCommands error: {ex}")
        return False

def get_keywords() -> list:
    """Load keywords from Config sheet col A (text before ':'), cache result."""
    data = fetch_config_templates()
    if data and data.get("map"):
        return list(data["map"].keys())
    return KEYWORDS_DEFAULT

def get_template_text(cmd_name: str) -> str:
    """Find matching template for command name from Config sheet Column A2:A."""
    data = fetch_config_templates()
    lines = data.get("all", [])
    mapping = data.get("map", {})
    
    clean_cmd = cmd_name.lstrip("/").strip().lower()
    norm_cmd = clean_cmd.replace("_", " ").replace("-", " ")
    no_space_cmd = clean_cmd.replace("_", "").replace("-", "").replace(" ", "")
    
    # 1. Exact match in mapping
    if clean_cmd in mapping:
        return mapping[clean_cmd]
    if norm_cmd in mapping:
        return mapping[norm_cmd]
        
    # 2. Normalized match (e.g. loss_fuel -> Loss fuel, inventory_oil -> Inventory oil)
    for k, v in mapping.items():
        k_clean = k.replace("_", "").replace("-", "").replace(" ", "")
        if k_clean == no_space_cmd:
            return v
        
    # 3. Match lines starting with command name (e.g. /inventory -> all "Inventory..." lines)
    matching = [line for line in lines if line.lower().startswith(norm_cmd) or line.lower().startswith(clean_cmd)]
    if matching:
        return "\n".join(matching)
        
    # 4. Fallback: all lines if /template or /all
    if clean_cmd in ("template", "templates", "all", "help"):
        return "\n".join(lines) if lines else ""

    return ""



# ── Send data to Asset Google Sheet via Apps Script ──────────────────────
def post_sheet(payload: dict, timeout: int = 35):
    """POST JSON to Asset Apps Script Web App."""
    if not APPS_SCRIPT_URL:
        logger.error("APPS_SCRIPT_URL not set.")
        return {"status": "error", "message": "APPS_SCRIPT_URL not configured"}
    try:
        resp = requests.post(APPS_SCRIPT_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        logger.info(f"Apps Script response: {resp.text[:300]}")
        # Handle empty response body (GAS timeout / redirect trả về HTML rỗng)
        if not resp.text or not resp.text.strip():
            logger.error("Apps Script returned empty response")
            return {"status": "error", "message": "Apps Script returned empty response (possible timeout or session expired)"}
        try:
            return resp.json()
        except ValueError as je:
            logger.error(f"Apps Script non-JSON response: {resp.text[:200]}")
            return {"status": "error", "message": f"Invalid response from Apps Script: {resp.text[:100]}"}
    except Exception as e:
        logger.error(f"Apps Script POST error: {e}")
        return {"status": "error", "message": str(e)}



# ── Send data to Cable Google Sheet via Apps Script ───────────────────────
def post_cable_sheet(payload: dict):
    """POST JSON to Cable Apps Script Web App."""
    if not CABLE_APPS_SCRIPT_URL:
        logger.error("CABLE_APPS_SCRIPT_URL not set.")
        return {"status": "error", "message": "CABLE_APPS_SCRIPT_URL not configured"}
    try:
        resp = requests.post(CABLE_APPS_SCRIPT_URL, json=payload, timeout=30)
        resp.raise_for_status()
        logger.info(f"Cable Apps Script response: {resp.text[:300]}")
        return resp.json()
    except Exception as e:
        logger.error(f"Cable Apps Script POST error: {e}")
        return {"status": "error", "message": str(e)}


# ── Send data to MDG Google Sheet via Apps Script ─────────────────────────
def post_cable_photo(payload: dict):
    """Fire-and-forget: send cable photo data to GAS then return immediately.
    GAS handles download+upload independently (up to 6 minutes).
    """
    if not CABLE_APPS_SCRIPT_URL:
        return {"status": "error", "message": "CABLE_APPS_SCRIPT_URL not configured"}
    try:
        resp = requests.post(CABLE_APPS_SCRIPT_URL, json=payload, timeout=(10, 8))
        resp.raise_for_status()
        logger.info(f"Cable photo GAS response: {resp.text[:200]}")
        return resp.json()
    except requests.exceptions.ReadTimeout:
        logger.info("GAS processing cable photo in background — OK")
        return {"status": "processing"}
    except Exception as e:
        logger.error(f"Cable photo error: {e}")
        return {"status": "error", "message": str(e)}


def post_mdg_sheet(payload: dict):
    """POST JSON to MDG Apps Script Web App with automatic fallback."""
    url = MDG_APPS_SCRIPT_URL or MAIN_GAS_FALLBACK
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        logger.info(f"MDG Apps Script response: {resp.text[:300]}")
        return resp.json()
    except Exception as e:
        logger.error(f"MDG Apps Script POST error ({url}): {e} -> Retrying with MAIN_GAS_FALLBACK")
        try:
            resp = requests.post(MAIN_GAS_FALLBACK, json=payload, timeout=30)
            resp.raise_for_status()
            logger.info(f"MDG Apps Script fallback response: {resp.text[:300]}")
            return resp.json()
        except Exception as retry_err:
            return {"status": "error", "message": str(retry_err)}


def post_mdg_photo(payload: dict):
    """Fire-and-forget: send photo data to GAS then return immediately.
    GAS (6-min limit on Google servers) handles download+upload independently.
    Python only waits 8s for read — if GAS hasn't replied, treat as 'processing'.
    """
    if not MDG_APPS_SCRIPT_URL:
        return {"status": "error", "message": "MDG_APPS_SCRIPT_URL not configured"}
    try:
        # connect_timeout=10s, read_timeout=8s — just enough to deliver payload
        resp = requests.post(MDG_APPS_SCRIPT_URL, json=payload, timeout=(10, 20))
        resp.raise_for_status()
        logger.info(f"MDG photo GAS response: {resp.text[:200]}")
        return resp.json()
    except requests.exceptions.ReadTimeout:
        # GAS received data and is processing (download Telegram + upload Drive)
        # GAS runs for up to 6 minutes on Google servers — this is NORMAL
        logger.info("GAS processing photo in background (up to 3 min) — OK")
        return {"status": "processing"}
    except Exception as e:
        logger.error(f"MDG photo error: {e}")
        return {"status": "error", "message": str(e)}


# ── MDG: field list ───────────────────────────────────────────────────────
MDG_FIELDS_LIST = [
    "date", "site id", "branch", "team",
    "mdg code", "mdg capacity", "mdg serial",
    "dg start time", "dg end time", "total hours",
    "staff name", "staff code", "remark",
]


def parse_mdg_fields(text: str) -> dict:
    """Extract MDG field values - allows multiple spaces between words
    (e.g. 'DG end  Time' with double space).
    """
    result = {}
    for field in MDG_FIELDS_LIST:
        # Build regex allowing \s+ between each word of the field name
        word_pattern = r"\s+".join(re.escape(w) for w in field.split())
        pattern = rf"(?i){word_pattern}\s*:\s*(.+?)(?=\n|$)"
        m = re.search(pattern, text)
        if m:
            val = m.group(1).strip()
            # Strip stray leading colons e.g. ": 10hrs" → "10hrs"
            val = re.sub(r"^[:\s]+", "", val).strip()
            result[field] = val
    return result


# ── Inventory: field list ─────────────────────────────────────────────────
INV_FIELDS_LIST = [
    "inventory fuel", "dg id", "fuel cm", "fuel %",
    "fuel level", "kwh", "rh", "note"
]

def parse_inv_fields(text: str) -> dict:
    """Extract Inventory Fuel field values.
    Numeric fields: chỉ lấy số, bỏ đơn vị (vd: '19cm'→'19', '15%'→'15').
    """
    NUMERIC_FIELDS = {"fuel cm", "fuel %", "fuel level", "kwh", "rh"}
    result = {}
    for field in INV_FIELDS_LIST:
        word_pattern = r"\s+".join(re.escape(w) for w in field.split())
        pattern = rf"(?i){word_pattern}\s*:\s*(.+?)(?=\n|$)"
        m = re.search(pattern, text)
        if m:
            val = m.group(1).strip()
            val = re.sub(r"^[:\s]+", "", val).strip()
            if field in NUMERIC_FIELDS:
                # Chỉ giữ lại số và dấu chấm thập phân, bỏ đơn vị
                num = re.sub(r"[^\d.]", "", val)
                val = num if num else val
            result[field] = val
    return result

# ── Change Oil MDG: field list ───────────────────────────────────────────
OIL_FIELDS_LIST = [
    "change oil mdg", "site mdg", "type oil",
    "hour for mdg 8kva", "kw for mdg 8kva", "note"
]

def parse_oil_fields(text: str) -> dict:
    """Extract Change Oil MDG field values.
    Numeric fields: chỉ lấy số (vd: '120hrs'→'120', '8kw'→'8').
    """
    NUMERIC_FIELDS = {"hour for mdg 8kva", "kw for mdg 8kva"}
    result = {}
    for field in OIL_FIELDS_LIST:
        word_pattern = r"\s+".join(re.escape(w) for w in field.split())
        pattern = rf"(?i){word_pattern}\s*:\s*(.+?)(?=\n|$)"
        m = re.search(pattern, text)
        if m:
            val = m.group(1).strip()
            val = re.sub(r"^[:\s]+", "", val).strip()
            if field in NUMERIC_FIELDS:
                num = re.sub(r"[^\d.]", "", val)
                val = num if num else val
            result[field] = val
    return result



# ── Cable: detect type keyword ────────────────────────────────────────────
def parse_cable_type(text: str) -> str:
    """Return Rescue / Request Change / Maintenance / Deploy (or empty)."""
    lower = text.lower()
    for kw in CABLE_TYPE_KEYWORDS:
        if kw in lower:
            return kw.title()
    return ""


# ── Cable: parse 9 structured fields ─────────────────────────────────────
def parse_cable_fields(text: str) -> dict:
    """Extract field values from lines like 'Incident Name : ...'."""
    result = {}
    for field in CABLE_FIELDS_LIST:
        pattern = rf"(?i){re.escape(field)}\s*:\s*(.+?)(?=\n|$)"
        m = re.search(pattern, text)
        if m:
            result[field] = m.group(1).strip()
    return result


# ── Daily Plan detection ──────────────────────────────────────────────────
def is_daily_plan(text: str) -> bool:
    """Detect plan message: text has 'plan' and date d/m/yyyy, excluding bot auto reports."""
    if not text:
        return False
    text_l = text.lower()
    if any(kw in text_l for kw in (
        "comparison of plan for", "auto report", "plan stats:", "report — daily plan",
        "crosscheck", "plan tomorrow status", "plan vs actual", "eod summary",
        "shows detailed site assignments", "tasks grouped by department", "recent plans",
        "plans for ", "tni personal find task", "ft result daily", "personal find task",
        "find task + wo", "list name ft"
    )):
        return False

    has_plan = "plan" in text_l
    has_date = bool(re.search(r'\b\d{1,2}[\/\.]\d{1,2}[\/\.]\d{2,4}\b', text))
    return has_plan and has_date


def parse_plan_fields(text: str) -> tuple:
    """Extract (date, team, content) from plan message."""
    lines = text.strip().split("\n")
    # Date: tìm ngày trong toàn bộ text (ưu tiên theo chữ 'daily plan' hoặc 'plan for')
    date_str = ""
    date_m = re.search(r'(?:daily\s*plan|plan\s*for)[:\s]+(\d{1,2}[\/\.]\d{1,2}[\/\.]\d{2,4})', text, re.IGNORECASE)
    if not date_m:
        date_m = re.search(r'(\d{1,2}[\/\.]\d{1,2}[\/\.]\d{2,4})', text)
    if date_m:
        raw_d = date_m.group(1)
        parts = re.split(r'[\/\.]', raw_d)
        if len(parts) == 3:
            d, m, y = parts
            if len(y) == 2:
                y = "20" + y
            date_str = f"{int(d):02d}/{int(m):02d}/{y}"
    if not date_str:
        now_mm = datetime.now(TZ_MM)
        date_str = now_mm.strftime("%d/%m/%Y")

    # Team: tìm Team + số
    team_str = ""
    team_m = re.search(r'Team\s*0?([1-5])', text, re.IGNORECASE)
    if team_m:
        team_str = f"Team {team_m.group(1)}"

    # Content: mọi thứ sau dòng header (dòng đầu có 'plan') và dòng team
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


# ── Detect collector keyword in message ───────────────────────────────────
def is_collector_msg(text: str) -> bool:
    """
    Strict match: keyword phải nằm ở DÒNG ĐẦU TIÊN và phải đứng TRƯỚC dấu ':'.
    Ví dụ hợp lệ:
        Order: 12/08/2026 ...
        Revoke: TNI0210 ...
        Move:
        /order
    Ví dụ KHÔNG hợp lệ (chat bình thường):
        Let me order something
        We should move that asset
        can you export this?
    """
    if not text:
        return False

    # 🛑 LOẠI BỎ DAILY RESULT VÀ DAILY PLAN (Do Search bot xử lý)
    text_l = text.lower()
    if "daily result" in text_l or "daily plan" in text_l:
        return False

    clean_text = text.strip()

    # ── Xử lý lệnh slash /order hoặc /order@bot ──
    if clean_text.startswith("/"):
        cmd_m = re.match(r'^/([a-zA-Z0-9_]+)(?:@[a-zA-Z0-9_]+)?(?:\s+(.*))?$', clean_text, re.DOTALL)
        if cmd_m:
            cmd = cmd_m.group(1).lower()
            # Slash command hợp lệ nếu là keyword đã biết
            for k in get_keywords():
                if cmd == k.replace(" ", "_") or cmd == k.replace(" ", ""):
                    return True
        return False

    # ── Chỉ kiểm tra DÒNG ĐẦU TIÊN ──
    first_line = clean_text.splitlines()[0].strip().lower()

    for k in get_keywords():
        k_esc = re.escape(k)
        # Keyword phải đứng ĐẦU dòng, và ngay sau keyword là ':' hoặc khoảng trắng + ký tự khác (không phải chữ cái liên tiếp)
        # Pattern: ^<keyword>\s*: hoặc ^<keyword>\s+\S (có nội dung sau)
        # Không cho phép: "let me order" hay "We can move"
        if re.match(r'^\s*' + k_esc + r'\s*[:\-]', first_line):
            return True
        if re.match(r'^\s*' + k_esc + r'\s+\d', first_line):   # keyword + ngày tháng/số
            return True
        if re.match(r'^\s*' + k_esc + r'\s*$', first_line):    # keyword đứng một mình
            return True

    return False


# ── Main async handler ────────────────────────────────────────────────────
# ============================================================
# CABLE GROUP HANDLER
# ============================================================
async def handle_cable(msg, bot, now, user, sender_name, sender_id):
    """Handle all messages from the TNI CABLE ROUTE group."""
    chat_id = msg.chat_id

    # ── Photos ──────────────────────────────────────────────────────────
    if msg.photo:
        photos = msg.photo  # list of sizes, take largest
        largest = photos[-1]
        try:
            file_info = await bot.get_file(largest.file_id)
            tg_url = (
                f"https://api.telegram.org/file/bot{COLLECTOR_BOT_TOKEN}/"
                f"{file_info.file_path}"
            )
        except Exception as e:
            logger.error(f"Cable get_file error: {e}")
            tg_url = ""

        # Try to find REF from caption or reply
        ref_id = None
        caption = msg.caption or ""
        ref_m = re.search(r"REF[:\s#]*(\d+)", caption, re.IGNORECASE)
        if ref_m:
            ref_id = ref_m.group(1)
        elif msg.reply_to_message:
            reply_text = msg.reply_to_message.text or ""
            ref_m = re.search(r"REF[:\s#]*(\d+)", reply_text, re.IGNORECASE)
            if ref_m:
                ref_id = ref_m.group(1)

        result    = post_cable_photo({
            "action":      "cable_add_photo",
            "ref_id":      ref_id,
            "tg_url":      tg_url,
            "tg_file_id":  largest.file_id,
            "sender_name": sender_name,
            "sender_id":   sender_id,
            "date":        now.strftime("%d/%m/%Y %H:%M"),
        })
        actual_ref = result.get("ref") or ref_id
        ref_show   = str(actual_ref).zfill(5) if actual_ref else "?????"
        status     = result.get("status", "error")

        if status == "ok":
            drive_link = result.get("link", "")
            link_html  = f"\n🔗 <a href='{drive_link}'>View on Drive</a>" if drive_link else ""
            await bot.send_message(
                chat_id,
                f"📷 <b>REF:{ref_show}</b> | Photo saved{link_html}",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        elif status == "processing":
            await bot.send_message(
                chat_id,
                f"📷 <b>REF:{ref_show}</b> | Photo submitted ⏳ (uploading to Drive...)",
                parse_mode="HTML",
            )
        else:
            err = html.escape(result.get("message", "Upload failed"))
            await bot.send_message(
                chat_id,
                f"⚠️ Photo error (REF:{ref_show}): {err}",
                parse_mode="HTML",
            )
        return

    if not msg.text:
        return

    text = msg.text.strip()

    # ── /start ──────────────────────────────────────────────────────────
    if text.lower().startswith("/start"):
        await bot.send_message(
            chat_id,
            "🔌 <b>TNI Cable Route Bot</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>Send incident in this format:</b>\n\n"
            "<code>Rescue:\n"
            "Incident Name : TNI0146-TNI0147 link down\n"
            "Physical route : TNI0146-TNI0147\n"
            "Total cable length : 16.5KM\n"
            "Cable Owner : Mytel\n"
            "Responsible Branch : TNI\n"
            "RCA : people cut at 10.6KM from TNI0146\n"
            "Team Name : TNI Team01\n"
            "WO : Need\n"
            "Materials List : 48 FO M100 and JB 2pcs</code>\n\n"
            "🏷️ <b>Types:</b> Rescue | Request Change | Maintenance | Deploy\n"
            "✅ <b>Confirm:</b> Reply bot message with <code>Confirm</code>\n"
            "📷 <b>Photo:</b> Send photo (reply to bot msg with REF) — OCR enabled",
            parse_mode="HTML",
        )
        return

    # ── Confirm Complete ─────────────────────────────────────────────────
    if re.match(r"^confirm\b", text, re.IGNORECASE):
        ref_id = None
        # Extract REF from reply-to message
        if msg.reply_to_message:
            reply_text = msg.reply_to_message.text or ""
            ref_m = re.search(r"REF[:\s#]*(\d+)", reply_text, re.IGNORECASE)
            if ref_m:
                ref_id = ref_m.group(1)
        # Also try from text itself: "Confirm REF:00001"
        if not ref_id:
            ref_m = re.search(r"REF[:\s#]*(\d+)", text, re.IGNORECASE)
            if ref_m:
                ref_id = ref_m.group(1)

        if not ref_id:
            await bot.send_message(
                chat_id,
                "⚠️ Please <b>reply</b> to the bot confirmation message to confirm.\n"
                "Or use: <code>Confirm REF:00001</code>",
                parse_mode="HTML",
            )
            return

        confirm_detail = re.sub(r"^confirm\s*:?\s*(?:REF[:\s#]*\d+)?\s*", "",
                                text, flags=re.IGNORECASE).strip()
        result = post_cable_sheet({
            "action":         "cable_confirm",
            "ref_id":         ref_id,
            "confirmed_by":   sender_name,
            "sender_id":      sender_id,
            "confirm_detail": confirm_detail,
            "date":           now.strftime("%d/%m/%Y"),
            "time":           now.strftime("%H:%M"),
        })

        if result.get("status") == "ok":
            ref_pad = str(ref_id).zfill(5)
            await bot.send_message(
                chat_id,
                f"✅ <b>REF #{ref_pad} — Confirmed</b>\n"
                f"👤 {html.escape(sender_name)}\n"
                f"📅 {now.strftime('%d/%m/%Y %H:%M')}" +
                (f"\n📝 {html.escape(confirm_detail)}" if confirm_detail else ""),
                parse_mode="HTML",
            )
        else:
            err = html.escape(result.get("message", "unknown error"))
            await bot.send_message(chat_id, f"⚠️ Confirm failed: {err}", parse_mode="HTML")
        return

    # ── Cable incident message ────────────────────────────────────────────
    cable_type = parse_cable_type(text)
    fields     = parse_cable_fields(text)

    payload = {
        "action":      "cable_add",
        "date":        now.strftime("%d/%m/%Y"),
        "time":        now.strftime("%H:%M"),
        "type":        cable_type or "Unknown",
        "sender_name": sender_name,
        "sender_id":   sender_id,
        "fields":      fields,
        "raw":         text if not fields else "",
    }

    result = post_cable_sheet(payload)

    if result.get("status") == "ok":
        ref  = result.get("ref") or str(result.get("row", "???")).zfill(5)
        flds = []
        if fields.get("incident name"):   flds.append(f"📍 {fields['incident name']}")
        if fields.get("team name"):        flds.append(f"👷 {fields['team name']}")
        if fields.get("total cable length"): flds.append(f"📏 {fields['total cable length']}")
        detail_lines = "\n".join(flds)

        type_emoji = {"rescue": "🚨", "request change": "🔄",
                      "maintenance": "🔧", "deploy": "🚀"}
        t_emoji = type_emoji.get((cable_type or "").lower(), "🔌")
        type_label = html.escape(cable_type or "Unknown")

        await bot.send_message(
            chat_id,
            f"{t_emoji} <b>REF:{ref}</b> | {type_label} | {now.strftime('%d/%m/%Y %H:%M')}\n"
            f"✅ Reply <code>Confirm</code> to close | 📷 Photo → reply this msg",
            parse_mode="HTML",
        )
    else:
        err = html.escape(result.get("message", "Apps Script error"))
        await bot.send_message(chat_id, f"⚠️ Failed to record: {err}", parse_mode="HTML")



# ============================================================
# MDG GROUP HANDLER
# ============================================================
async def handle_mdg(msg, bot, now, user, sender_name, sender_id):
    """Handle all messages from group `6. TNI Run MDG + Invetory Fuel`."""
    chat_id = msg.chat_id

    # ── Photos ──────────────────────────────────────────────────────────
    if msg.photo:
        largest = msg.photo[-1]
        try:
            file_info = await bot.get_file(largest.file_id)
            tg_url = (
                f"https://api.telegram.org/file/bot{COLLECTOR_BOT_TOKEN}/"
                f"{file_info.file_path}"
            )
        except Exception as e:
            logger.error(f"MDG get_file error: {e}")
            tg_url = ""

        ref_id = None
        caption = msg.caption or ""
        ref_m = re.search(r"REF[:\s#]*(\d+)", caption, re.IGNORECASE)
        if ref_m:
            ref_id = ref_m.group(1)
        elif msg.reply_to_message:
            reply_text = msg.reply_to_message.text or ""
            ref_m = re.search(r"REF[:\s#]*(\d+)", reply_text, re.IGNORECASE)
            if ref_m:
                ref_id = ref_m.group(1)

        action_name = "process_photo"
        if msg.reply_to_message and msg.reply_to_message.text:
            rt_upper = msg.reply_to_message.text.upper()
            if "INVENTORY" in rt_upper:
                action_name = "inv_add_photo"
            elif "MDG" in rt_upper:
                action_name = "mdg_add_photo"

        # ── Send file_id + tg_url to Apps Script (GAS downloads — no timeout) ──
        filename = f"MDG_{sender_id}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
        result   = post_mdg_photo({
            "action":      action_name,
            "ref_id":      ref_id,
            "tg_url":      tg_url,
            "tg_file_id":  largest.file_id,
            "filename":    filename,
            "sender_name": sender_name,
            "sender_id":   sender_id,
            "date":        now.strftime("%d/%m/%Y %H:%M"),
        })
        actual_ref = result.get("ref") or ref_id
        ref_show   = str(actual_ref).zfill(5) if actual_ref else "?????"
        status     = result.get("status", "error")

        if status == "ok":
            photo_num = result.get("photoNum", "")
            msg_type = result.get("type", "")
            prefix = "⛽" if msg_type == "INV" else ("🛢️" if msg_type == "OIL" else "📷")
            await bot.send_message(
                chat_id,
                f"{prefix} <b>REF:{ref_show}</b> | Photo {photo_num} saved",
                parse_mode="HTML",
            )
        elif status == "processing":
            await bot.send_message(
                chat_id,
                f"📷 <b>REF:{ref_show}</b> | Photo submitted ⏳ (uploading to Drive...)",
                parse_mode="HTML",
            )
        else:
            err = html.escape(result.get("message", "Upload failed"))
            await bot.send_message(
                chat_id,
                f"⚠️ Photo error (REF:{ref_show}): {err}",
                parse_mode="HTML",
            )
        return

    if not msg.text:
        return

    text = msg.text.strip()

    # ── Commands ────────────────────────────────────────────────────────
    if text.startswith("/"):
        cmd = text.split()[0].split("@")[0].lower()
        if cmd in ("/start", "/help"):
            await bot.send_message(
                chat_id,
                "👋 <b>TNI MDG Run & Inventory Bot</b>\n\n"
                "Available template commands:\n"
                "• /inventory - Inventory report template\n"
                "• /change_oil - Change oil MDG template\n\n"
                "<i>Tap any command to receive the template, then copy and fill out.</i>",
                parse_mode="HTML"
            )
            return
        elif cmd in ("/inventory", "/inventory_fuel"):
            await bot.send_message(
                chat_id,
                "Inventory fuel:\n"
                "DG ID: TNIXXXX\n"
                "Fuel cm: \n"
                "Fuel %: \n"
                "Fuel level: \n"
                "Kwh: \n"
                "Rh: \n"
                "Note: ",
                parse_mode="HTML"
            )
            return
        elif cmd in ("/change_oil", "/oil", "/change_oil_mdg", "/oil_mdg"):
            tpl = fetch_change_oil_template()
            await bot.send_message(chat_id, tpl, parse_mode="HTML")
            return

    # ── Confirm reply ────────────────────────────────────────────────────
    if text.lower() == "confirm" and msg.reply_to_message:
        reply_text = msg.reply_to_message.text or ""
        ref_m = re.search(r"REF:(\d+)", reply_text)
        if ref_m:
            ref_id = ref_m.group(1)
            action_name = "mdg_confirm"
            if "INVENTORY" in reply_text.upper():
                action_name = "inv_confirm"
            elif "CHANGE OIL" in reply_text.upper() or "OIL" in reply_text.upper():
                action_name = "oil_confirm"
            
            result = post_mdg_sheet({
                "action":       action_name,
                "ref_id":       ref_id,
                "confirmed_by": sender_name,
                "date":         now.strftime("%d/%m/%Y %H:%M"),
            })
            if result.get("status") == "ok":
                await bot.send_message(
                    chat_id,
                    f"✅ <b>REF:{str(ref_id).zfill(5)}</b> — Confirmed by {html.escape(sender_name)}",
                    parse_mode="HTML",
                )
            else:
                err = html.escape(result.get("message", "unknown error"))
                await bot.send_message(chat_id, f"⚠️ Confirm failed: {err}", parse_mode="HTML")
        return

    # ── Change Oil MDG Report message (Strict Rule: Requires "change oil" AND "site mdg") ──
    text_l = text.lower()
    has_oil_kw = "change oil" in text_l or "change oil mdg" in text_l
    has_site_mdg = "site mdg" in text_l or "site id" in text_l

    if has_oil_kw and has_site_mdg:
        lines_oil = text.splitlines()
        oil_start_idx = next(
            (i for i, ln in enumerate(lines_oil) if "change oil" in ln.lower()),
            0
        )
        oil_text = "\n".join(lines_oil[oil_start_idx:]).strip()
        if oil_start_idx > 0:
            logger.info(f"[OIL] Trimmed {oil_start_idx} header line(s) before Change Oil section")

        fields = parse_oil_fields(oil_text)
        site_mdg = fields.get("site mdg", "")

        payload = {
            "action":      "oil_add",
            "date":        now.strftime("%d/%m/%Y"),
            "time":        now.strftime("%H:%M"),
            "sender_name": sender_name,
            "sender_id":   sender_id,
            "fields":      fields,
            "raw":         oil_text,
        }

        result = post_mdg_sheet(payload)

        if result.get("status") == "ok":
            ref = result.get("ref") or str(result.get("row", "???")).zfill(5)
            site_show = html.escape(site_mdg) if site_mdg else "—"
            await bot.send_message(
                chat_id,
                f"🛢️ <b>REF:{ref}</b> | 🪑 <b>Ghế 2C: Change Oil MDG</b> | {site_show} | {now.strftime('%d/%m/%Y %H:%M')}\n"
                f"✅ Reply <code>Confirm</code> to close | 📸 Photo → reply this msg",
                parse_mode="HTML",
            )
        else:
            err = html.escape(result.get("message", "Apps Script error"))
            await bot.send_message(chat_id, f"⚠️ Failed to record: {err}", parse_mode="HTML")
        return

    # ── Inventory Report message (Strict Rule: Requires "inventory fuel" AND "dg id: tni") ──
    has_inv_kw = "inventory fuel" in text_l
    has_dg_tni = "dg id: tni" in text_l or "dg id:tni" in text_l or ("dg id:" in text_l and "tni" in text_l)

    if has_inv_kw and has_dg_tni:
        # FIX: forward từ Viber → trim text từ dòng đầu có "inventory fuel"
        lines_inv = text.splitlines()
        inv_start_idx = next(
            (i for i, ln in enumerate(lines_inv) if "inventory fuel" in ln.lower()),
            0
        )
        inv_text = "\n".join(lines_inv[inv_start_idx:]).strip()
        if inv_start_idx > 0:
            logger.info(f"[INV] Trimmed {inv_start_idx} header line(s) before Inventory section")

        fields = parse_inv_fields(inv_text)
        dg_id = fields.get("dg id", "")

        payload = {
            "action":      "inv_add",
            "date":        now.strftime("%d/%m/%Y"),
            "time":        now.strftime("%H:%M"),
            "sender_name": sender_name,
            "sender_id":   sender_id,
            "fields":      fields,
            "raw":         inv_text,
        }

        result = post_mdg_sheet(payload)

        if result.get("status") == "ok":
            ref = result.get("ref") or str(result.get("row", "???")).zfill(5)
            dg_show = html.escape(dg_id) if dg_id else "—"
            await bot.send_message(
                chat_id,
                f"⛽ <b>REF:{ref}</b> | 🪑 <b>Ghế 2B: Inventory Fuel</b> | {dg_show} | {now.strftime('%d/%m/%Y %H:%M')}\n"
                f"✅ Reply <code>Confirm</code> to close | 📸 Photo → reply this msg",
                parse_mode="HTML",
            )
        else:
            err = html.escape(result.get("message", "Apps Script error"))
            await bot.send_message(chat_id, f"⚠️ Failed to record: {err}", parse_mode="HTML")
        return

    # ── MDG Report message (Strict Rule: Requires "mdg" AND "site id: tni") ──
    has_mdg_kw = "mdg" in text_l
    has_site_tni = "site id: tni" in text_l or "site id:tni" in text_l or ("site id:" in text_l and "tni" in text_l)

    if has_mdg_kw and has_site_tni:
        # FIX: forward từ Viber / copy-paste có thể có text thừa trước "MDG ::Report"
        # → tìm dòng đầu tiên có chữ "MDG" và parse từ đó
        lines = text.splitlines()
        mdg_start_idx = next(
            (i for i, ln in enumerate(lines) if "mdg" in ln.lower()),
            0  # fallback: dùng toàn bộ text nếu không tìm thấy
        )
        mdg_text = "\n".join(lines[mdg_start_idx:]).strip()
        if mdg_start_idx > 0:
            logger.info(f"[MDG] Trimmed {mdg_start_idx} header line(s) before MDG section")

        fields = parse_mdg_fields(mdg_text)
        site_id = fields.get("site id", "")

        payload = {
            "action":      "mdg_add",
            "date":        now.strftime("%d/%m/%Y"),
            "time":        now.strftime("%H:%M"),
            "sender_name": sender_name,
            "sender_id":   sender_id,
            "fields":      fields,
            "raw":         mdg_text,   # lưu text đã trim, không lưu phần header thừa
        }

        result = post_mdg_sheet(payload)

        if result.get("status") == "ok":
            ref = result.get("ref") or str(result.get("row", "???")).zfill(5)
            site_show = html.escape(site_id) if site_id else "—"
            await bot.send_message(
                chat_id,
                f"⚡ <b>REF:{ref}</b> | 🪑 <b>Ghế 2A: MDG Run Report</b> | {site_show} | {now.strftime('%d/%m/%Y %H:%M')}\n"
                f"✅ Reply <code>Confirm</code> to close | 📷 Photo → reply this msg",
                parse_mode="HTML",
            )
        else:
            err = html.escape(result.get("message", "Apps Script error"))
            await bot.send_message(chat_id, f"⚠️ Failed to record: {err}", parse_mode="HTML")
        return


# ============================================================
# MAIN HANDLER
# ============================================================
async def handle(data: dict):
    async with Bot(token=COLLECTOR_BOT_TOKEN) as bot:
        update = Update.de_json(data, bot)
        if not update.message:
            return

        msg         = update.message
        user        = msg.from_user
        if not user or user.is_bot:
            logger.info("Ignoring message from bot or missing user")
            return

        chat_id     = msg.chat_id
        now         = datetime.now(TZ_MM)          # Myanmar time for all groups
        sender_name = (user.full_name if user else "") or ""
        sender_id   = str(user.id) if user else ""
        username    = (f"@{user.username}" if user and user.username else str(user.id)) if user else ""

        # ── Route: Cable group ─────────────────────────────────────────
        if chat_id == CABLE_CHAT_ID:
            logger.info(f"[Cable] msg from {sender_name} ({sender_id})")
            await handle_cable(msg, bot, now, user, sender_name, sender_id)
            return

        # ── Route: MDG group ───────────────────────────────────────────
        if chat_id == MDG_CHAT_ID:
            logger.info(f"[MDG] msg from {sender_name} ({sender_id})")
            await handle_mdg(msg, bot, now, user, sender_name, sender_id)
            return

        # ── Photo messages ─────────────────────────────────────────────
        if msg.photo:
            largest = msg.photo[-1]

            # Tìm ref_id nếu có (Reply hoặc caption)
            ref_id = None
            reply  = msg.reply_to_message
            if reply:
                m = re.search(r"#(\d+)", reply.text or reply.caption or "")
                if m:
                    ref_id = m.group(1)
            if not ref_id and msg.caption:
                m = re.search(r"#(\d+)", msg.caption)
                if m:
                    ref_id = m.group(1)

            try:
                # Bước 1: Python download ảnh từ Telegram (dùng library built-in)
                file_info = await bot.get_file(largest.file_id)
                photo_bytes = await file_info.download_as_bytearray()
                if not photo_bytes:
                    await bot.send_message(
                        chat_id,
                        "⚠️ Telegram download failed: empty file"
                    )
                    return

                photo_b64 = base64.b64encode(bytes(photo_bytes)).decode("utf-8")
                ext = (file_info.file_path or "photo.jpg").rsplit(".", 1)[-1]

                # Bước 2: Gửi base64 lên GAS
                payload = {
                    "action":     "add_photo",
                    "user_id":    str(user.id if user else ""),
                    "photo_b64":  photo_b64,
                    "photo_ext":  ext,
                    "date":       now.strftime("%d/%m/%Y %H:%M"),
                }
                if ref_id:
                    payload["ref_id"] = ref_id

                result = post_sheet(payload, timeout=25)
                logger.info(f"Photo result: {result}")

                # Bước 3: Reply cho user
                status = result.get("status", "")
                if status == "ok":
                    r_id = str(result.get("ref_id") or ref_id or "").zfill(5) or "..."
                    await bot.send_message(
                        chat_id,
                        f"📷 Photo gắn vào <b>#{r_id}</b>",
                        parse_mode="HTML"
                    )
                else:
                    err_msg = result.get("message", "unknown")[:200]
                    await bot.send_message(
                        chat_id,
                        f"⚠️ Photo GAS error: {err_msg}",
                        parse_mode="HTML"
                    )

            except Exception as e:
                logger.error(f"Photo handler error: {e}")
                try:
                    await bot.send_message(chat_id, f"⚠️ Photo exception: {e}")
                except:
                    pass
            return


        # ── Text only from here ────────────────────────────────────────
        if not msg.text:
            return

        text    = msg.text.strip()

        # ── Commands ──────────────────────────────────────────────────────
        if text.startswith("/"):
            cmd = text.split()[0].split("@")[0].lower()
            
            if cmd in ("/start", "/help"):
                if chat_id == MDG_CHAT_ID:
                    await bot.send_message(
                        chat_id,
                        "👋 <b>TNI MDG Run & Inventory Bot</b>\n\n"
                        "Available template commands:\n"
                        "• /inventory - Inventory report template\n"
                        "• /change_oil - Change oil MDG template\n\n"
                        "<i>Tap any command to receive the template, then copy and fill out.</i>",
                        parse_mode="HTML"
                    )
                else:
                    cmd_list_lines = []
                    for l in fetch_config_templates().get("all", []):
                        fp = l.split(":")[0].strip() if ":" in l else l.split()[0].strip()
                        c_name = fp.lower().replace(" ", "_").replace("-", "_")
                        c_name = "".join(c for c in c_name if c.isalnum() or c == "_")[:32]
                        if c_name and c_name != "field_name":
                            cmd_list_lines.append(f"• /{c_name} — {fp} template")
                    cmd_text = "\n".join(cmd_list_lines)
                    await bot.send_message(
                        chat_id,
                        f"👋 <b>TNI Asset & Cable Bot</b>\n\n"
                        f"Available template commands:\n"
                        f"{cmd_text}\n\n"
                        f"<i>Tap any command to receive the template, then copy and fill out.</i>",
                        parse_mode="HTML"
                    )
                return
            else:
                tpl_txt = get_template_text(cmd)
                if tpl_txt:
                    await bot.send_message(chat_id, tpl_txt, parse_mode="HTML")
                    return

        # ── Done ──────────────────────────────────────────────────────────
        if re.match(r"^done\b", text, re.IGNORECASE):
            # 1) Extract #ID from user's text: "Done: #00008" or "Done: #8"
            id_in_text = re.search(r"#(\d+)", text)
            ref_id = None

            if id_in_text:
                ref_id = id_in_text.group(1)
            else:
                # 2) Extract #ID or REF:ID from reply_to_message
                reply = msg.reply_to_message
                if reply:
                    reply_text = reply.text or reply.caption or ""
                    if reply_text:
                        # Try #00010 or REF:00010 format
                        id_in_reply = (
                            re.search(r"#(\d+)", reply_text) or
                            re.search(r"REF:(\d+)", reply_text)
                        )
                        if id_in_reply:
                            ref_id = id_in_reply.group(1)
                        else:
                            # 3) Fallback: use Apps Script "find" to search
                            #    by original message content in sheet
                            logger.info(f"[Done] Fallback find: {reply_text[:80]}")
                            find_result = post_sheet({
                                "action": "find",
                                "text":   reply_text.strip()
                            })
                            if find_result.get("status") == "ok":
                                ref_id = str(find_result.get("row", ""))
                                logger.info(f"[Done] Found ref_id={ref_id} via sheet find")

            if not ref_id:
                await bot.send_message(
                    chat_id,
                    "Receive Done (Only asset or Team leader reply Done or Done detail)",
                    parse_mode="HTML"
                )
                return

            # Extract done detail: "Done: fixed it" → "fixed it"
            done_detail = re.sub(r"^done\s*:?\s*#?\d*\s*", "", text, flags=re.IGNORECASE).strip()

            result = post_sheet({
                "action":    "done",
                "ref_id":    ref_id,
                "done":      done_detail,
                "done_date": now.strftime("%d/%m/%Y"),
                "done_time": now.strftime("%H:%M"),
                "chat_id":   str(user.id if user else chat_id),
                "sender_name": sender_name,
            })
            status = result.get("status")
            if status == "ok":
                ref_padded = str(ref_id).zfill(5)
                # 2 dòng: dòng 1 = REF, dòng 2 = Done + ngày
                line1 = f"REQUEST_BOT ✅ Recorded — 🆔 #{ref_padded} 🏷️"
                line2 = "Done"
                if done_detail:
                    line2 += ": " + html.escape(done_detail)
                line2 += f" 📅 {now.strftime('%d/%m/%Y %H:%M')}"
                await bot.send_message(chat_id, f"{line1}\n{line2}", parse_mode="HTML")
            elif status == "denied":
                await bot.send_message(
                    chat_id,
                    f"🚫 ID <code>{user.id if user else chat_id}</code> not authorised.",
                    parse_mode="HTML"
                )
            else:
                err = html.escape(result.get("message", "unknown error"))
                await bot.send_message(chat_id, f"⚠️ Error: {err}", parse_mode="HTML")
            return


        # ── Daily Plan → Handled exclusively by Search Bot (@SEARCHTNITASKWOBOT) ──
        if is_daily_plan(text):
            return

        # ── Collector commands ─────────────────────────────────────────────
        if is_collector_msg(text):
            result = post_sheet({
                "action":  "add",
                "date":    now.strftime("%d/%m/%Y %H:%M"),   # Column A
                "chat_id": str(user.id if user else chat_id),# Column B
                "msg":     text,                              # Column C
            })

            if result.get("status") == "ok":
                row_id = str(result.get("row", "???")).zfill(5)
                await bot.send_message(
                    chat_id,
                    f"REQUEST_BOT ✅ Recorded — 🆔 #{row_id}📅 {now.strftime('%d/%m/%Y %H:%M')}",
                    parse_mode="HTML"
                )
            else:
                err = html.escape(result.get("message", "no response from Apps Script"))
                logger.error(f"Sheet error: {err}")
                await bot.send_message(
                    chat_id,
                    f"⚠️ <b>Failed to record.</b>\n<i>{err}</i>",
                    parse_mode="HTML"
                )
            return

        # ── Unknown message — ignore silently in groups ─────────────────
        # Only reply in private chat to avoid spam in groups
        if msg.chat.type == "private":
            kws = get_keywords()
            kw_list = ", ".join(k.title() + ":" for k in kws)
            await bot.send_message(
                chat_id,
                f"❓ <b>Command not recognised.</b>\n"
                f"Use: {kw_list}\n"
                f"Send <code>/start</code> for help.",
                parse_mode="HTML"
            )


_collector_webhook_set = False
def ensure_collector_webhook_active() -> None:
    global _collector_webhook_set
    if _collector_webhook_set or not COLLECTOR_BOT_TOKEN:
        return
    try:
        expected = "https://tni-bot.vercel.app/api/collector"
        r = requests.get(f"https://api.telegram.org/bot{COLLECTOR_BOT_TOKEN}/getWebhookInfo", timeout=5).json()
        wh_url = r.get("result", {}).get("url", "")
        if wh_url != expected:
            logger.info(f"Setting Asset Bot webhook to {expected} (was: {wh_url})")
            requests.post(f"https://api.telegram.org/bot{COLLECTOR_BOT_TOKEN}/setWebhook", json={
                "url": expected,
                "allowed_updates": ["message", "edited_message", "channel_post"],
                "drop_pending_updates": False
            }, timeout=5)
        _collector_webhook_set = True
    except Exception as e:
        logger.error(f"ensure_collector_webhook_active error: {e}")


_processed_collector_updates = {}   # update_id -> timestamp

# ── Vercel entry point ────────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            data   = json.loads(self.rfile.read(length))
            
            # ── Deduplication for Telegram Retries (TTL = 15s) ──
            update_id = data.get("update_id")
            now_ts = time.time()
            if update_id:
                stale_uids = [uid for uid, ts in list(_processed_collector_updates.items()) if now_ts - ts > 15]
                for uid in stale_uids:
                    _processed_collector_updates.pop(uid, None)

                if update_id in _processed_collector_updates:
                    logger.info(f"Skipping duplicate Collector update_id: {update_id}")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b"OK")
                    return
                _processed_collector_updates[update_id] = now_ts

            # Execute synchronously FIRST before returning 200 OK to prevent Vercel process freeze
            asyncio.run(handle(data))

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            try:
                self.send_response(500)
                self.end_headers()
            except Exception:
                pass

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)
        action = query.get("action", [None])[0]

        if action == "reset" and COLLECTOR_BOT_TOKEN:
            try:
                expected = "https://tni-bot.vercel.app/api/collector"
                r1 = requests.post(f"https://api.telegram.org/bot{COLLECTOR_BOT_TOKEN}/deleteWebhook", json={"drop_pending_updates": True}, timeout=10).json()
                r2 = requests.post(f"https://api.telegram.org/bot{COLLECTOR_BOT_TOKEN}/setWebhook", json={
                    "url": expected,
                    "allowed_updates": ["message", "edited_message", "channel_post"],
                    "drop_pending_updates": True
                }, timeout=10).json()
                r3 = requests.get(f"https://api.telegram.org/bot{COLLECTOR_BOT_TOKEN}/getWebhookInfo", timeout=10).json()
                res = {"delete": r1, "set": r2, "info": r3.get("result", {})}
            except Exception as ex:
                res = {"error": str(ex)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res, indent=2).encode("utf-8"))
            return

        ensure_collector_webhook_active()
        cmd_synced = sync_telegram_menu_commands()
        token_ok  = "SET" if COLLECTOR_BOT_TOKEN else "MISSING"
        script_ok = "SET" if APPS_SCRIPT_URL else "MISSING"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(
            f"Collector Bot OK | TOKEN:{token_ok} | SCRIPT_URL:{script_ok} | CMDS_SYNCED:{cmd_synced}".encode()
        )

    def log_message(self, *a): pass
