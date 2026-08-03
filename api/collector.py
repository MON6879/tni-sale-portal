"""
Vercel webhook handler for Collector Bot (TNIAsset_BO).

Routing:
  - TNI CABLE ROUTE group  (CABLE_CHAT_ID) → handle_cable()
  - TNI COLLECT MDG RUN    (MDG_CHAT_ID)   → handle_mdg()
  - All other chats                         → existing Asset handler

Webhook URL: https://tni-bot.vercel.app/api/collector
"""
import os, re, json, asyncio, logging, requests, html, base64
from http.server import BaseHTTPRequestHandler
from telegram import Bot, Update
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COLLECTOR_BOT_TOKEN   = os.environ.get("COLLECTOR_BOT_TOKEN", "").strip().strip("\ufeff")
APPS_SCRIPT_URL        = os.environ.get("APPS_SCRIPT_URL", "").strip().strip("\ufeff")
CABLE_APPS_SCRIPT_URL  = os.environ.get("CABLE_APPS_SCRIPT_URL", "").strip().lstrip('\ufeff')
try:
    CABLE_CHAT_ID = int(os.environ.get("CABLE_CHAT_ID", "-5531350787").strip())
except ValueError:
    CABLE_CHAT_ID = -5531350787

MDG_APPS_SCRIPT_URL = os.environ.get("MDG_APPS_SCRIPT_URL", "").strip().lstrip('\ufeff')
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

def get_keywords() -> list:
    """Load keywords from Config sheet col A (text before ':'), cache result."""
    global _keywords_cache
    if _keywords_cache is not None:
        return _keywords_cache
    try:
        url = (
            "https://docs.google.com/spreadsheets/d/"
            "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8"
            "/gviz/tq?tqx=out:csv&gid=1236389870&tq=select+A+limit+30"
        )
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        import csv, io
        rows = list(csv.reader(io.StringIO(resp.text)))
        kws = []
        for row in rows[1:]:  # skip header
            val = (row[0] if row else "").strip()
            if ":" in val:
                kw = val.split(":")[0].strip().lower()
                if kw and kw not in kws:
                    kws.append(kw)
        if kws:
            _keywords_cache = kws
            logger.info(f"Keywords from Config: {kws}")
            return kws
    except Exception as e:
        logger.warning(f"Config keyword load failed: {e}, using defaults")
    _keywords_cache = KEYWORDS_DEFAULT
    return _keywords_cache



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
    """POST JSON to MDG Apps Script Web App."""
    if not MDG_APPS_SCRIPT_URL:
        logger.error("MDG_APPS_SCRIPT_URL not set.")
        return {"status": "error", "message": "MDG_APPS_SCRIPT_URL not configured"}
    try:
        resp = requests.post(MDG_APPS_SCRIPT_URL, json=payload, timeout=30)
        resp.raise_for_status()
        logger.info(f"MDG Apps Script response: {resp.text[:300]}")
        return resp.json()
    except Exception as e:
        logger.error(f"MDG Apps Script POST error: {e}")
        return {"status": "error", "message": str(e)}


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
    """Detect plan message: first 3 lines have 'plan', text has date d/m/yyyy."""
    if not text:
        return False
    text_l = text.lower()
    # 🛑 LOẠI BỎ TẤT CẢ CÁC BẢN TIN MẪU CỦA BOT HOẶC BÁO CÁO TỰ ĐỘNG
    if any(kw in text_l for kw in (
        "daily plan template", "copy → edit", "copy -> edit", "note: /find /tnixxxx",
        "comparison of plan for", "auto report", "plan stats:", "report — daily plan",
        "crosscheck", "plan tomorrow status", "plan vs actual", "eod summary"
    )):
        return False

    lines = [line.strip().lower() for line in text.split("\n") if line.strip()]
    first_few_lines = " ".join(lines[:3]) if lines else ""
    has_plan = "plan" in first_few_lines
    has_date = bool(re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', text))
    return has_plan and has_date


def parse_plan_fields(text: str) -> tuple:
    """Extract (date, team, content) from plan message."""
    lines = text.strip().split("\n")
    # Date: tìm ngày trong toàn bộ text
    date_str = ""
    date_m = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', text)
    if date_m:
        parts = date_m.group(1).split("/")
        if len(parts) == 3:
            d, m, y = parts
            if len(y) == 2:
                y = "20" + y
            date_str = f"{d.zfill(2)}/{m.zfill(2)}/{y}"
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
    """Match keyword at start of any line, case-insensitive, with or without ':', or via slash command."""
    if not text:
        return False
    # Xử lý lệnh dạng /order hoặc /order@TNIASSETOrderREQUEST_BOT
    clean_text = text.strip()
    if clean_text.startswith("/"):
        # Lấy tên lệnh bỏ qua phần @botusername
        cmd_m = re.match(r'^/([a-zA-Z0-9_]+)(?:@[a-zA-Z0-9_]+)?(?:\s+(.*))?$', clean_text, re.DOTALL)
        if cmd_m:
            cmd = cmd_m.group(1).lower()
            rest = cmd_m.group(2) or ""
            clean_text = f"{cmd} {rest}".strip()

    lower = clean_text.lower()
    for k in get_keywords():
        pattern = r'(?:^|\n)\s*' + re.escape(k) + r'(?:\s*[:\s]|\s*$)'
        if re.search(pattern, lower):
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
    """Handle all messages from the TNI COLLECT MDG RUN group."""
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
            prefix = "⛽" if msg_type == "INV" else "📷"
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
                "Available template command:\n"
                "• /inventory - Inventory report template\n\n"
                "<i>Tap the command to receive the template, then copy and fill out.</i>",
                parse_mode="HTML"
            )
            return
        elif cmd == "/inventory":
            await bot.send_message(
                chat_id,
                "📝 <b>Template: Inventory Fuel</b>\n"
                "<i>(Tap the code block below to copy)</i>\n\n"
                "<pre><code>Inventory fuel:\n"
                "DG ID: TNIXXXX\n"
                "Fuel cm: \n"
                "Fuel %: \n"
                "Fuel level: \n"
                "Kwh: \n"
                "Rh: \n"
                "Note: </code></pre>",
                parse_mode="HTML"
            )
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

    # ── Inventory Report message ─────────────────────────────────────────
    if "inventory fuel" in text.lower():
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
                f"⛽ <b>REF:{ref}</b> | INVENTORY | {dg_show} | {now.strftime('%d/%m/%Y %H:%M')}\n"
                f"✅ Reply <code>Confirm</code> to close | 📷 Photo → reply this msg",
                parse_mode="HTML",
            )
        else:
            err = html.escape(result.get("message", "Apps Script error"))
            await bot.send_message(chat_id, f"⚠️ Failed to record: {err}", parse_mode="HTML")
        return

    # ── MDG Report message ───────────────────────────────────────────────
    if "mdg" in text.lower():
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
                f"⚡ <b>REF:{ref}</b> | MDG | {site_show} | {now.strftime('%d/%m/%Y %H:%M')}\n"
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
                        "Available template command:\n"
                        "• /inventory - Inventory report template\n\n"
                        "<i>Tap the command to receive the template, then copy and fill out.</i>",
                        parse_mode="HTML"
                    )
                else:
                    await bot.send_message(
                        chat_id,
                        "👋 <b>TNI Asset & Cable Bot</b>\n\n"
                        "Available template commands:\n"
                        "• /order - Order template\n"
                        "• /revoke - Revoke template\n"
                        "• /move - Move template\n"
                        "• /export - Export template\n"
                        "• /done - Done template\n"
                        "• /find - Search tasks, WOs, or site details\n\n"
                        "<i>Tap any command to receive the template, then copy and fill out.</i>",
                        parse_mode="HTML"
                    )
                return
            elif cmd == "/daily":
                now_mm = datetime.now(TZ_MM)
                date_s = now_mm.strftime("%d/%m/%Y")
                template_text = (
                    f"Daily result: {date_s}\n"
                    "1. Full Name:\n"
                    "2. Transportation Used:\n"
                    "3. I. Hot task rescue Site down >24:\n"
                    "4. II Hot task Cell rescue:\n"
                    "5. III. Hot task Repair DG abnormal:\n"
                    "6. IV. Hot task Repair DG run>16H:\n"
                    "7. V. Hot task other:\n"
                    "8. VII. Detail WO:\n"
                    "9. VII. Detail task:\n"
                    "10. Name and detail Site go busines trip start go:\n"
                    "11. Name and detail Site go busines trip end go:\n"
                    "12. Km moto bike start:\n"
                    "13. Km moto bike the end:"
                )
                await bot.send_message(
                    chat_id,
                    f"📋 <b>Mẫu Daily Result</b>\n"
                    f"Nhấn copy → chỉnh sửa → gửi lại:\n\n"
                    f"<pre><code>{html.escape(template_text)}</code></pre>",
                    parse_mode="HTML"
                )
                return
            elif cmd == "/inventory":
                await bot.send_message(
                    chat_id,
                    "📝 <b>Template: Inventory Fuel</b>\n"
                    "<i>(Tap the code block below to copy)</i>\n\n"
                    "<pre><code>Inventory fuel:\n"
                    "DG ID: TNIXXXX\n"
                    "Fuel cm: \n"
                    "Fuel %: \n"
                    "Fuel level: \n"
                    "Kwh: \n"
                    "Rh: \n"
                    "Note: </code></pre>",
                    parse_mode="HTML"
                )
                return
            elif cmd == "/order" and chat_id != MDG_CHAT_ID:
                await bot.send_message(
                    chat_id,
                    "📝 <b>Template: Order</b>\n"
                    "<i>(Tap the code block below to copy)</i>\n\n"
                    "<pre><code>Order: TNIXXXX [Description/Item detail]</code></pre>",
                    parse_mode="HTML"
                )
                return
            elif cmd == "/revoke" and chat_id != MDG_CHAT_ID:
                await bot.send_message(
                    chat_id,
                    "📝 <b>Template: Revoke</b>\n"
                    "<i>(Tap the code block below to copy)</i>\n\n"
                    "<pre><code>Revoke: TNIXXXX [Description/Reason]</code></pre>",
                    parse_mode="HTML"
                )
                return
            elif cmd == "/move" and chat_id != MDG_CHAT_ID:
                await bot.send_message(
                    chat_id,
                    "📝 <b>Template: Move</b>\n"
                    "<i>(Tap the code block below to copy)</i>\n\n"
                    "<pre><code>Move: TNIXXXX [From station A to station B]</code></pre>",
                    parse_mode="HTML"
                )
                return
            elif cmd == "/export" and chat_id != MDG_CHAT_ID:
                await bot.send_message(
                    chat_id,
                    "📝 <b>Template: Export</b>\n"
                    "<i>(Tap the code block below to copy)</i>\n\n"
                    "<pre><code>Export: TNIXXXX [Detail]</code></pre>",
                    parse_mode="HTML"
                )
                return
            elif cmd == "/done" and chat_id != MDG_CHAT_ID:
                await bot.send_message(
                    chat_id,
                    "📝 <b>Template: Done</b>\n"
                    "<i>(Tap the code block below to copy)</i>\n\n"
                    "<pre><code>Done: #XXXXX [Action taken]</code></pre>",
                    parse_mode="HTML"
                )
                return
            elif cmd == "/find" and chat_id != MDG_CHAT_ID:
                await bot.send_message(
                    chat_id,
                    "🔍 <b>How to Search:</b>\n\n"
                    "Just send the site code (e.g. <code>TNI0001</code>) or staff name directly to the bot to search for tasks, WOs, or site details.",
                    parse_mode="HTML"
                )
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


        # ── Daily Plan → store to Team leader assign Plan sheet ─────────
        if is_daily_plan(text):
            date_str, team_str, content = parse_plan_fields(text)
            if date_str and team_str:
                result = post_sheet({
                    "action":      "store_daily_plan",
                    "date":        date_str,
                    "team":        team_str,
                    "content":     content or text,
                    "daily_report": "",
                    "comparison":  "",
                })
                status = result.get("status", "")
                if status == "ok":
                    ref = result.get("ref", "?")
                    dup = result.get("duplicate", False)
                    icon = "⏭️" if dup else "📋"
                    await bot.send_message(
                        chat_id,
                        f"{icon} Plan {'updated' if dup else 'saved'}"
                        f" — REF:{ref} | {team_str} | {date_str}",
                    )
                else:
                    err = html.escape(result.get("message", "unknown")[:80])
                    await bot.send_message(chat_id, f"⚠️ Plan save failed: {err}", parse_mode="HTML")
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


# ── Vercel entry point ────────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            ensure_collector_webhook_active()
            length = int(self.headers.get("Content-Length", 0))
            data   = json.loads(self.rfile.read(length))
            asyncio.run(handle(data))
        except Exception as e:
            logger.error(f"Webhook error: {e}")
        finally:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

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
        token_ok  = "SET" if COLLECTOR_BOT_TOKEN else "MISSING"
        script_ok = "SET" if APPS_SCRIPT_URL else "MISSING"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(
            f"Collector Bot OK | TOKEN:{token_ok} | SCRIPT_URL:{script_ok}".encode()
        )

    def log_message(self, *a): pass
