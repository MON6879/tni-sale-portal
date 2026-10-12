"""
Vercel webhook handler for 15 TNI CABLE Bot (@TNI_CABLE_BOT).
Seat: BOT-CABLE-15 / GAS-CABLE-15
Group: 8 TNI CABLE BROKEN SOS (CABLE_CHAT_ID: -5531350787)
Webhook URL: https://tni-bot.vercel.app/api/cable_bot
"""
import os, re, json, asyncio, logging, requests, html, time
from http.server import BaseHTTPRequestHandler
from telegram import Bot, Update
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CABLE_BOT_TOKEN = os.environ.get("CABLE_BOT_TOKEN", "").strip().strip("\ufeff")
CABLE_APPS_SCRIPT_URL = os.environ.get("CABLE_APPS_SCRIPT_URL", "").strip().lstrip('\ufeff')
MAIN_GAS_FALLBACK = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"

if not CABLE_APPS_SCRIPT_URL or "AKfycbz-NZlBk8q2" not in CABLE_APPS_SCRIPT_URL:
    CABLE_APPS_SCRIPT_URL = MAIN_GAS_FALLBACK

try:
    CABLE_CHAT_ID = int(os.environ.get("CABLE_CHAT_ID", "-5531350787").strip())
except ValueError:
    CABLE_CHAT_ID = -5531350787

TZ_MM = timezone(timedelta(hours=6, minutes=30))   # Myanmar UTC+6:30

CABLE_TYPE_KEYWORDS = ["request change", "rescue", "maintenance", "deploy"]
CABLE_FIELDS_LIST = [
    "incident name", "physical route", "total cable length",
    "cable owner", "responsible branch", "rca",
    "team name", "wo", "materials list"
]

def post_cable_sheet(payload: dict) -> dict:
    """POST JSON to Cable Apps Script Web App."""
    if not CABLE_APPS_SCRIPT_URL:
        logger.error("CABLE_APPS_SCRIPT_URL not set.")
        return {"status": "error", "message": "CABLE_APPS_SCRIPT_URL not configured"}
    try:
        resp = requests.post(CABLE_APPS_SCRIPT_URL, json=payload, timeout=30)
        logger.info(f"Cable Apps Script response: {resp.text[:300]}")
        return resp.json()
    except Exception as e:
        logger.error(f"Cable Apps Script POST error: {e}")
        return {"status": "error", "message": str(e)}

def post_cable_photo(payload: dict) -> dict:
    """Send cable photo data to GAS."""
    if not CABLE_APPS_SCRIPT_URL:
        return {"status": "error", "message": "CABLE_APPS_SCRIPT_URL not configured"}
    try:
        resp = requests.post(CABLE_APPS_SCRIPT_URL, json=payload, timeout=35)
        logger.info(f"Cable photo GAS response: {resp.text[:300]}")
        return resp.json()
    except Exception as e:
        logger.error(f"Cable photo error: {e}")
        return {"status": "error", "message": str(e)}

def parse_cable_type(text: str) -> str:
    first_line = text.strip().split("\n")[0].lower()
    for kw in CABLE_TYPE_KEYWORDS:
        if kw in first_line:
            return kw.title()
    for kw in CABLE_TYPE_KEYWORDS:
        if kw in text.lower():
            return kw.title()
    return ""

def parse_cable_fields(text: str) -> dict:
    fields = {}
    lines = text.strip().split("\n")
    current_key = None
    current_val = []

    for line in lines:
        matched = False
        for field in CABLE_FIELDS_LIST:
            pattern = rf"^\s*{re.escape(field)}\s*[:\-=]\s*(.*)$"
            m = re.match(pattern, line, re.IGNORECASE)
            if m:
                if current_key:
                    fields[current_key] = " ".join(current_val).strip()
                current_key = field.lower()
                current_val = [m.group(1).strip()]
                matched = True
                break
        if not matched:
            if current_key:
                current_val.append(line.strip())

    if current_key:
        fields[current_key] = " ".join(current_val).strip()

    return fields

MSG_REF_CACHE = {}  # telegram_msg_id -> ref_id

TEAM_EMOJIS = {
    "1": "🟠",
    "2": "🔵",
    "3": "🟢",
    "4": "🟡",
}

def extract_team_info(text: str) -> tuple[str, str]:
    """
    Trích xuất (team_name, team_tag) từ text theo chuẩn chấm màu Site Down:
      'Team 1 today()' -> ('Team 1', '🟠Team 1')
      'Progress: ... <=> 🟢 T3 - IP ...' -> ('T3', '🟢T3')
      'Progress: ... <=> 🔵 T2s1 - IP ...' -> ('T2s1', '🔵T2s1')
      'Team04' -> ('Team 4', '🟡Team 4')
    """
    # 1. Dạng Team X (Team 1, Team 04, Team 3)
    m1 = re.search(r"\bTeam\s*(\d+|[A-Za-z0-9_]+)", text, re.IGNORECASE)
    if m1:
        num = m1.group(1).lstrip("0") or m1.group(1)
        emoji = TEAM_EMOJIS.get(num, "")
        clean_team = f"Team {num}"
        return clean_team, f"{emoji}{clean_team}" if emoji else clean_team

    # 2. Dạng T1..T4 (kèm s1, S1...)
    m2 = re.search(r"(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?\b(T[1-4](?:[sS]\d+|\s*S\d+)?)\b", text, re.IGNORECASE)
    if m2:
        t_raw = m2.group(1)
        num = t_raw[1] if len(t_raw) > 1 and t_raw[1] in TEAM_EMOJIS else ""
        emoji = TEAM_EMOJIS.get(num, "")
        clean_t = re.sub(r'^[🔴🔵🟢🟡🟠🟣⚪⚫]\s*', '', t_raw)
        return clean_t, f"{emoji}{clean_t}" if emoji else clean_t

    return ("", "")

def resolve_ref_from_msg(msg, text=""):
    """Resolve REF ID, Incident Name, Team Name, and Reply Text from current message or replied message."""
    ref_id = None
    incident_name = None
    team_name = None
    reply_text = ""

    # 1. Search current text for REF
    m = re.search(r"REF[:\s#]*(\d+)", text, re.IGNORECASE)
    if m:
        ref_id = m.group(1)

    # 2. Inspect replied-to message if any
    if msg.reply_to_message:
        reply_msg = msg.reply_to_message
        reply_text = reply_msg.text or reply_msg.caption or ""

        # Check in-memory cache for reply_msg.message_id
        if not ref_id and reply_msg.message_id in MSG_REF_CACHE:
            ref_id = MSG_REF_CACHE[reply_msg.message_id]

        # Check for REF in reply text (e.g. Reply to Bot message)
        if not ref_id:
            m = re.search(r"REF[:\s#]*(\d+)", reply_text, re.IGNORECASE)
            if m:
                ref_id = m.group(1)

        # Check for Incident Name in reply text (e.g. Reply to Step 2)
        inc_fields = parse_cable_fields(reply_text)
        incident_name = inc_fields.get("incident name")
        if not incident_name:
            m_inc = re.search(r"incident\s*name\s*[:\-=\s]+(.*)", reply_text, re.IGNORECASE)
            if m_inc:
                incident_name = m_inc.group(1).split("\n")[0].strip()

        # Check for Team Name in reply text (e.g. Reply to Step 1)
        m_team = re.search(r"Team\s*(\d+|[A-Za-z0-9_]+)", reply_text, re.IGNORECASE)
        if m_team:
            team_name = f"Team {m_team.group(1)}"
        elif not team_name:
            m_team_t = re.search(r"(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?\b(T[1-4](?:[sS]\d+|\s*S\d+)?)\b", reply_text, re.IGNORECASE)
            if m_team_t:
                team_name = m_team_t.group(1)

        # Check for Incident from Type 2 Link down text
        if not incident_name and "link down" in reply_text.lower():
            m_ip = re.search(r"(?:IP\s*:\s*)?(TNI\d{4}[A-Za-z0-9\-]+)", reply_text, re.IGNORECASE)
            if m_ip:
                incident_name = m_ip.group(1)
            else:
                incident_name = reply_text[:60].strip()

    return ref_id, incident_name, team_name, reply_text

async def handle_cable(msg, bot, now, user, sender_name, sender_id):
    """Handle messages for 15 TNI CABLE."""
    chat_id = msg.chat_id

    # ── Photos ──────────────────────────────────────────────────────────
    if msg.photo:
        photos = msg.photo
        largest = photos[-1]
        try:
            file_info = await bot.get_file(largest.file_id)
            tg_url = (
                f"https://api.telegram.org/file/bot{CABLE_BOT_TOKEN}/"
                f"{file_info.file_path}"
            )
        except Exception as e:
            logger.error(f"Cable get_file error: {e}")
            tg_url = ""

        caption = msg.caption or ""
        ref_id, incident_name, team_name, reply_text = resolve_ref_from_msg(msg, caption)

        # Kiểm tra xem có phải ảnh bảo trì (Maintenance Photo) không
        is_maintenance = False
        if any(kw in caption.lower() for kw in ["maint", "splicer", "otdr", "done"]):
            is_maintenance = True
        elif msg.reply_to_message:
            rep_text = msg.reply_to_message.text or msg.reply_to_message.caption or ""
            if "done" in rep_text.lower() or "maintenance" in rep_text.lower() or "maint" in rep_text.lower():
                is_maintenance = True

        result = post_cable_photo({
            "action":         "cable_add_photo",
            "ref_id":         ref_id,
            "incident_name":  incident_name,
            "team":           team_name,
            "reply_text":     reply_text,
            "caption":        caption,
            "is_maintenance": is_maintenance,
            "tg_url":         tg_url,
            "tg_file_id":     largest.file_id,
            "sender_name":    sender_name,
            "sender_id":      sender_id,
            "chat_id":        chat_id,
            "date":           now.strftime("%d/%m/%Y %H:%M"),
        })
        actual_ref = result.get("ref") or ref_id
        ref_show   = str(actual_ref).zfill(5) if actual_ref else "?????"
        status     = result.get("status", "error")

        if status == "ok":
            # Ảnh đã được tải lên Drive & ghi link vào Sheet, hàng đợi 10 phút sẽ gửi tin tổng hợp
            logger.info(f"Photo uploaded for REF:{ref_show}, 10-min ack queued in GAS.")
            if ref_show != "?????":
                MSG_REF_CACHE[msg.message_id] = ref_show
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

    # Bỏ qua tin nhắn từ Bot khác hoặc tin báo cáo tự động của chính Bot 15
    if user and user.is_bot:
        return
    if text.startswith("🔌") and ("LINK DOWN REPORT" in text.upper() or "15 TNI CABLE" in text.upper()):
        return

    # ── 1. /template: Incident Report Template (Step 1 & 2) ──────────────
    if text.lower().startswith(("/template", "/incident")):
        await bot.send_message(
            chat_id,
            "🔌 <b>15 TNI CABLE Bot (@TNI_CABLE_BOT)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📋 <b>Incident Report Template (Step 1 & 2):</b>\n\n"
            "<b>Step 1 — Send Team Template:</b>\n"
            "<code>Team 1 today()\n"
            "Route Broken:\n"
            "Note: Need fix cable and splicer full core, Fix cable high. /MaintenanceSplicerandOTDR affter using and /Charging</code>\n"
            "<i>(Initial photos can be attached here)</i>\n\n"
            "<b>Step 2 — Reply with Incident Details (Route Broken):</b>\n"
            "<code>Incident Name : TNI0295-TNI0355 SRT link down at 1.9.2026\n"
            "Physical route : TNI0012-TNI0015\n"
            "Total cable length :74 KM\n"
            "Cable Owner : Mytel\n"
            "Responsible Branch : TNI\n"
            "RCA : Squirrel bite cut or at 4.70KM from TNI295\n"
            "Team Name  : Team04  \n"
            "WO : Need\n"
            "materials List : Closure 1</code>\n"
            "<i>(Photo collection for incident ends after this message)</i>\n\n"
            "💡 <i>When resolved, use /done or reply Done to close.</i>",
            parse_mode="HTML",
        )
        return

    # ── 2. /done Guide: Resolution & Maintenance Guide (Step 3 & 4) ──────
    # If user sent "/done" as standalone command without replying to an incident
    is_done_guide_cmd = text.lower().split()[0] in ["/done", "/done@tni_cable_bot", "/done_guide", "/maint"]
    if is_done_guide_cmd and not msg.reply_to_message and not re.search(r"\bREF[:\s#]*\d+", text, re.IGNORECASE) and len(text.split()) == 1:
        await bot.send_message(
            chat_id,
            "✅ <b>15 TNI CABLE Bot — Done & Maintenance Guide (Step 3 & 4)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>Step 3 — Reply <code>Done</code> when resolved:</b>\n"
            "Reply <code>Done</code> (or <code>Done REF:00032</code>) to the incident message (Step 1, Step 2, or Bot message) to close the incident and mark Column K.\n\n"
            "<b>Step 4 — Send Maintenance Photos (Splicer + OTDR):</b>\n"
            "Send or reply maintenance photos with caption <code>maint</code>, <code>splicer</code>, <code>otdr</code>, or reply directly to the Done message.\n"
            "<i>(Saved to Maintenance folder on Drive, 10-min summary notification sent automatically)</i>",
            parse_mode="HTML",
        )
        return

    # ── 3. /start, /help, /menu ──────────────────────────────────────────
    if text.lower().startswith(("/start", "/help", "/menu")):
        await bot.send_message(
            chat_id,
            "🔌 <b>15 TNI CABLE Bot (@TNI_CABLE_BOT)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📋 <b>Available Commands:</b>\n\n"
            "• <b>/template</b> — Incident Report Template (Step 1 & 2)\n"
            "• <b>/done</b> — Resolution & Maintenance Guide (Step 3 & 4)\n"
            "• <b>/confirm</b> — Confirm incident complete (Management)\n"
            "• <b>/help</b> — Show this command list\n\n"
            "<i>Tap any command above to use!</i>",
            parse_mode="HTML",
        )
        return

    # ── Done Action (Thu thập vào cột Done - Cột K) ───────────────────────
    # Hỗ trợ: Reply Bước 1 (Team notice), Reply Bước 2 (Route Broken), Reply Bot, hoặc gõ Done/REF
    if re.match(r"^/?done\b", text, re.IGNORECASE):
        ref_id, incident_name, team_name, reply_text = resolve_ref_from_msg(msg, text)

        done_detail = re.sub(r"^/?done\s*:?\s*(?:REF[:\s#]*\d+)?\s*", "",
                             text, flags=re.IGNORECASE).strip()
        result = post_cable_sheet({
            "action":        "cable_done",
            "ref_id":        ref_id,
            "incident_name": incident_name,
            "team":          team_name,
            "reply_text":    reply_text,
            "sender_name":   sender_name,
            "sender_id":     sender_id,
            "done_detail":   done_detail,
            "date":          now.strftime("%d/%m/%Y"),
            "time":          now.strftime("%H:%M"),
        })

        if result.get("status") == "ok":
            actual_ref = result.get("ref") or ref_id or "00000"
            ref_pad = str(actual_ref).zfill(5)
            MSG_REF_CACHE[msg.message_id] = ref_pad
            detail_str = f" | 📝 {html.escape(done_detail)}" if done_detail else ""
            bot_done_msg = await bot.send_message(
                chat_id,
                f"✅ <b>REF #{ref_pad} — Done</b> | 🗓️ {now.strftime('%d/%m/%Y %H:%M')}\n"
                f"👤 {html.escape(sender_name)}{detail_str} | 📷 Reply maintenance photo (Splicer + OTDR) to attach",
                parse_mode="HTML",
            )
            MSG_REF_CACHE[bot_done_msg.message_id] = ref_pad
        else:
            err = html.escape(result.get("message", "unknown error"))
            await bot.send_message(chat_id, f"⚠️ Done failed: {err}", parse_mode="HTML")
        return

    # ── Confirm Complete (Cột B) ─────────────────────────────────────────
    if re.match(r"^confirm\b", text, re.IGNORECASE):
        ref_id, incident_name, team_name, reply_text = resolve_ref_from_msg(msg, text)

        confirm_detail = re.sub(r"^confirm\s*:?\s*(?:REF[:\s#]*\d+)?\s*", "",
                                text, flags=re.IGNORECASE).strip()
        result = post_cable_sheet({
            "action":         "cable_confirm",
            "ref_id":         ref_id,
            "incident_name":  incident_name,
            "team":           team_name,
            "reply_text":     reply_text,
            "confirmed_by":   sender_name,
            "sender_id":      sender_id,
            "confirm_detail": confirm_detail,
            "date":           now.strftime("%d/%m/%Y"),
            "time":           now.strftime("%H:%M"),
        })

        if result.get("status") == "ok":
            actual_ref = result.get("ref") or ref_id or "00000"
            ref_pad = str(actual_ref).zfill(5)
            MSG_REF_CACHE[msg.message_id] = ref_pad
            detail_str = f" | 📝 {html.escape(confirm_detail)}" if confirm_detail else ""
            bot_conf_msg = await bot.send_message(
                chat_id,
                f"✅ <b>REF #{ref_pad} — Confirmed</b> | 🗓️ {now.strftime('%d/%m/%Y %H:%M')}\n"
                f"👤 {html.escape(sender_name)}{detail_str}",
                parse_mode="HTML",
            )
            MSG_REF_CACHE[bot_conf_msg.message_id] = ref_pad
        else:
            err = html.escape(result.get("message", "unknown error"))
            await bot.send_message(chat_id, f"⚠️ Confirm failed: {err}", parse_mode="HTML")
        return

    # ── Step 2: Route Broken details (Incident Name : ...) ────────────────
    if re.search(r"incident\s*name\s*:", text, re.IGNORECASE):
        ref_id, inc_name, team_name, reply_text = resolve_ref_from_msg(msg, text)
        result = post_cable_sheet({
            "action":       "cable_route_broken",
            "ref_id":       ref_id,
            "incident_name": inc_name,
            "team":         team_name,
            "reply_text":   reply_text,
            "raw_incident": text,
            "sender_name":  sender_name,
            "sender_id":    sender_id,
            "date":         now.strftime("%d/%m/%Y"),
            "time":         now.strftime("%H:%M"),
        })

        if result.get("status") == "ok":
            ref = result.get("ref") or "00000"
            ref_pad = str(ref).zfill(5)
            MSG_REF_CACHE[msg.message_id] = ref_pad
            bot_rb_msg = await bot.send_message(
                chat_id,
                f"🔌 <b>REF:{ref_pad}</b> | Route Broken recorded ✅ | 🗓️ {now.strftime('%d/%m/%Y %H:%M')}\n"
                f"✅ Reply <code>Done</code> to close | 📷 Maintenance photos after Done",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            MSG_REF_CACHE[bot_rb_msg.message_id] = ref_pad
        else:
            err = html.escape(result.get("message", "Error recording Route Broken"))
            await bot.send_message(chat_id, f"❌ Error: {err}", parse_mode="HTML")
        return

    # ── Step 1: Template 1 Thu Thập (Hỗ Trợ 2 Loại) ───────────────────────
    # Loại 1: Team Notice / Template truyền thống (Team 1 today(), Route Broken:, Splicer...)
    m_team1 = re.search(r"\bTeam\s*(\d+|[A-Za-z0-9_]+)", text, re.IGNORECASE)
    is_type1 = bool(m_team1 and any(kw in text.lower() for kw in ["today", "route broken", "splicer"])) or bool(parse_cable_type(text))

    # Loại 2: Link Down Progress Report (Progress: ... <=> ... link down ...)
    is_type2 = bool(
        ("link down" in text.lower()) and
        (
            "progress" in text.lower() or
            "<=>" in text or
            bool(re.search(r"\bT[1-4](?:[sS]\d+|\s*S\d+)?\b", text, re.IGNORECASE)) or
            bool(re.search(r"TNI\d{4}", text, re.IGNORECASE))
        )
    )

    if is_type1 or is_type2:
        team_name, team_tag = extract_team_info(text)

        if is_type2 and not is_type1:
            # ── Type 2: Progress update → UPDATE "Link down now" tab (nhanh, không tạo row mới)
            payload = {
                "action":      "cable_update_link_now",
                "raw":         text,
                "sender_name": sender_name,
                "sender_id":   sender_id,
                "date":        now.strftime("%d/%m/%Y"),
                "time":        now.strftime("%H:%M"),
            }
            result = post_cable_sheet(payload)

            status = result.get("status", "error")
            row    = result.get("row", "?")
            ip     = result.get("ip", "?")

            if status == "ok":
                tag_show = team_tag or (f"Team {team_name}" if team_name else "")
                team_str = f" | {tag_show}" if tag_show else ""
                bot_upd_msg = await bot.send_message(
                    chat_id,
                    f"🔗 <b>Link down progress updated ✅</b>{team_str} | 🗓️ {now.strftime('%d/%m/%Y %H:%M')}\n"
                    f"📋 IP: <code>{html.escape(str(ip))}</code> | Row {row} in Link down now sheet",
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            elif status == "not_found":
                # IP không tìm được trong sheet → log nhưng không báo lỗi ầm ĩ
                tried = result.get("tried", [])
                await bot.send_message(
                    chat_id,
                    f"⚠️ <b>IP not in Link down now sheet</b>: {html.escape(', '.join(tried))}\n"
                    f"Check sheet or add entry manually.",
                    parse_mode="HTML",
                )
            else:
                err = html.escape(result.get("message", "Apps Script error"))
                await bot.send_message(chat_id, f"❌ Error updating link status: {err}", parse_mode="HTML")
            return

        else:
            # ── Type 1 (hoặc cả Type 1 + Type 2): Tạo record mới trong Detail cable
            payload = {
                "action":        "cable_add_template",
                "template_type": "type_2_link_down" if is_type2 else "type_1_team_notice",
                "team":          team_name or "Team",
                "raw":           text,
                "route_broken":  text if is_type2 else "",
                "sender_name":   sender_name,
                "sender_id":     sender_id,
                "date":          now.strftime("%d/%m/%Y"),
                "time":          now.strftime("%H:%M"),
            }
            result = post_cable_sheet(payload)

            if result.get("status") == "ok":
                ref = result.get("ref") or str(result.get("row", "??")).zfill(5)
                ref_pad  = str(ref).zfill(5)
                tag_show = team_tag or (f"Team {team_name}" if team_name else "")
                team_str = f" | {tag_show}" if tag_show else ""

                action_guide = "📷 Reply photos to attach | ✅ Reply Done to close"
                if is_type1 and not is_type2:
                    action_guide = "📷 Reply photos to attach | 📝 Reply 'Incident Name : ...' for Route Broken"

                bot_inc_msg = await bot.send_message(
                    chat_id,
                    f"🔌 <b>REF:{ref_pad}</b>{team_str} | 🗓️ {now.strftime('%d/%m/%Y %H:%M')}\n"
                    f"{action_guide}",
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                MSG_REF_CACHE[msg.message_id] = ref_pad
                MSG_REF_CACHE[bot_inc_msg.message_id] = ref_pad
            else:
                err = html.escape(result.get("message", "Apps Script error"))
                await bot.send_message(chat_id, f"❌ Error saving report: {err}", parse_mode="HTML")
        return

async def process_update(data: dict):
    if not CABLE_BOT_TOKEN:
        logger.error("CABLE_BOT_TOKEN not configured.")
        return

    async with Bot(token=CABLE_BOT_TOKEN) as bot:
        update = Update.de_json(data, bot)
        if not update:
            return

        msg = update.message or update.edited_message
        if not msg:
            return

        chat_id     = msg.chat_id
        now         = datetime.now(TZ_MM)
        user        = msg.from_user
        sender_name = (user.full_name if user else "") or ""
        sender_id   = str(user.id) if user else ""

        # Allow handling in CABLE_CHAT_ID or private testing chats
        if chat_id == CABLE_CHAT_ID or msg.chat.type == "private":
            logger.info(f"[15 TNI CABLE] msg from {sender_name} ({sender_id}) in {chat_id}")
            await handle_cable(msg, bot, now, user, sender_name, sender_id)

def _tg_secret_ok(headers, env_name):
    """PM-97 R5: constant-time Telegram webhook secret check when configured; allow if env not set."""
    import hmac as _hmac
    import os as _os
    exp = _os.environ.get(env_name, "").strip()
    if not exp:
        return True
    got = headers.get("X-Telegram-Bot-Api-Secret-Token", "").strip()
    return bool(got) and _hmac.compare_digest(got.encode("utf-8"), exp.encode("utf-8"))


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not _tg_secret_ok(self.headers, "CABLE_WEBHOOK_SECRET"):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'{"error":"Forbidden"}')
            return
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            asyncio.run(process_update(data))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        except Exception as e:
            logger.error(f"Error processing POST: {e}", exc_info=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": false}')

    def do_GET(self):
        query = self.path.split("?")[-1] if "?" in self.path else ""
        params = dict(qc.split("=", 1) for qc in query.split("&") if "=" in qc)
        action = params.get("action", "").lower()

        if action in ("setup", "reset") and CABLE_BOT_TOKEN:
            try:
                if action == "reset":
                    requests.post(f"https://api.telegram.org/bot{CABLE_BOT_TOKEN}/deleteWebhook",
                                  json={"drop_pending_updates": True}, timeout=10)
                set_resp = requests.post(f"https://api.telegram.org/bot{CABLE_BOT_TOKEN}/setWebhook", json={
                    "url": "https://tni-bot.vercel.app/api/cable_bot",
                    "drop_pending_updates": False,
                }, timeout=10).json()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(set_resp).encode())
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
                return

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"15 TNI CABLE Bot Webhook Active 24/7 (Seat 15)")
