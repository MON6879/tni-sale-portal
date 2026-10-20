"""
# api/refuel_collector.py (redeploy trigger)
========================
Vercel webhook handler cho @TNI_FUEL bot.
Thu thập tin nhắn từ group 9 TNI REQUEST REFUEL (chat_id: -5469544739)
Phân loại:
  - Chứa "DG Type"  → REFUELED  (đổ xăng thực tế)
  - Chứa "Plan"     → PLAN      (kế hoạch đổ)
  - Chứa "request"  → REQUEST   (yêu cầu từ trạm)
Lưu vào Google Sheet qua REFUEL_PLAN_GAS_URL.

Webhook URL: https://tni-bot.vercel.app/api/refuel_collector
"""
import os, json, logging, requests
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REFUEL_BOT_TOKEN    = os.environ.get("REFUEL_BOT_TOKEN", "").strip()
REFUEL_PLAN_GAS_URL = (
    os.environ.get("REFUEL_APPS_SCRIPT_URL") or   # GitHub Actions secret name
    os.environ.get("REFUEL_PLAN_GAS_URL") or       # Vercel env var name (fallback)
    ""
).strip()

# Tự động chuyển đổi về SSOT GAS URL hiện hành nếu env chứa deployment cũ
MAIN_GAS_FALLBACK = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
if not REFUEL_PLAN_GAS_URL or "AKfycbz-NZlBk8q2" not in REFUEL_PLAN_GAS_URL:
    REFUEL_PLAN_GAS_URL = MAIN_GAS_FALLBACK

PLAN_GROUP_ID       = "5469544739"   # ID group 9 TNI REQUEST REFUEL (dạng số dương, không có dấu -)

TZ_MM = timezone(timedelta(hours=6, minutes=30))


def classify(text: str) -> str | None:
    """Phân loại tin nhắn báo cáo chính xác 100%, bắt buộc đúng cú pháp BẮT ĐẦU của Template (Anchored Start)."""
    import re
    t = text.strip().lower()
    has_site = bool(re.search(r'\btni0*(\d{1,4})\b', t))

    # 1. FT_MONITOR: Bắt buộc BẮT ĐẦU bằng 'Name of FT staff member...' hoặc 'follow monitor' VÀ có mã trạm TNI
    if (re.search(r'^\s*name\s+of\s+ft\s+staff\s+member\s+accompanying\s+to\s+supervise\b', t) or
        re.search(r'^\s*follow\s*monit[eo]r\b', t)):
        if has_site:
            return "FT_MONITOR"
        return None

    # 2. REFUELED: Báo cáo đổ dầu thực tế (hỗ trợ cả mẫu bắt đầu bằng DG Type, Date=, 1. Date=, Site ID, TNI... DG, hoặc khối Before/After)
    refueled_start = bool(
        re.search(r'^\s*(?:dg\s*type|tni0*\d{1,4}\b.*dg\s*type)\b', t) or
        re.search(r'^\s*(?:\d+[\.\:\-\)]\s*)?date\s*[=:]', t) or
        re.search(r'^\s*(?:\d+[\.\:\-\)]\s*)?(?:mytel\s*)?(?:site|dg)\s*id\b', t) or
        re.search(r'^\s*tni0*\d{1,4}\b', t) or
        re.search(r'^\s*(?:refuel(?:ed)?|báo\s*cáo\s*đổ\s*dầu)\b', t)
    )
    refueled_metrics = bool(
        'actual filled' in t or 'csu reading' in t or 'running hour' in t or
        'level %' in t or 'fuel level' in t or 'fuel liter' in t
    )
    refueled_keywords = bool(
        'dg type' in t or 'actual filled' in t or 'fuel filling team' in t or 'power mode' in t
    )

    if has_site and refueled_metrics and (refueled_start or ('before' in t and 'after' in t)) and refueled_keywords:
        return "REFUELED"

    # 3. LETTER_APPROVED & 4. LETTER_SUBMIT: Hỗ trợ đơn lẻ, có dấu • đầu dòng, hoặc copy nguyên khối /letter
    has_approve_line = bool(
        re.search(r'(?:^|\n)\s*(?:[•\-\*]\s*)?(?:approve(?:d)?\s*letter|letter\s*approve(?:d)?|government\s+approve(?:d)?)\s*[:\-]', t) or
        re.search(r'(?:^|\n)\s*(?:[•\-\*]\s*)?(?:approve(?:d)?\s*letter|letter\s*approve(?:d)?)\b.*\d{1,2}[/\-\.]\d{1,2}', t)
    )
    has_submit_line = bool(
        re.search(r'(?:^|\n)\s*(?:[•\-\*]\s*)?(?:letter\s*submit(?:ted)?|submit(?:ted)?\s*letter)\s*[:\-]', t) or
        re.search(r'(?:^|\n)\s*(?:[•\-\*]\s*)?(?:letter\s*submit(?:ted)?|submit(?:ted)?\s*letter)\b.*\d{1,2}[/\-\.]\d{1,2}', t)
    )
    if has_approve_line:
        return "LETTER_APPROVED"
    if has_submit_line:
        return "LETTER_SUBMIT"

    # 5. PLAN: Bắt buộc BẮT ĐẦU bằng 'Plan refuel' hoặc 'Team X Plan' VÀ có mã trạm TNI
    if re.search(r'^\s*(?:plan\s*refuel|team[\s_\-]*0*[1-4](?:\s*s\d+)?\s*plan(?:\s*refuel)?)\b', t):
        if has_site:
            return "PLAN"
        return None

    # 6. REQUEST: Bắt buộc BẮT ĐẦU bằng 'Request refuel' hoặc 'Team X Request' VÀ có mã trạm TNI
    if re.search(r'^\s*(?:request\s*refuel|team[\s_\-]*0*[1-4](?:\s*s\d+)?\s*request(?:\s*refuel)?)\b', t):
        if has_site:
            return "REQUEST"
        return None

    return None


def post_gas(payload: dict) -> dict:
    """POST dữ liệu lên Refuel Plan GAS."""
    if not REFUEL_PLAN_GAS_URL:
        logger.error("REFUEL_PLAN_GAS_URL not configured")
        return {"status": "error", "message": "REFUEL_PLAN_GAS_URL not set"}
    try:
        r = requests.post(REFUEL_PLAN_GAS_URL, json=payload, timeout=15)
        r.raise_for_status()
        text_resp = r.text.strip()
        if not text_resp:
            return {"status": "error", "message": "Empty GAS response"}
        
        # Nếu GAS trả về JSON có status
        try:
            js = r.json()
            if isinstance(js, dict):
                return js
        except ValueError:
            pass

        # Nếu GAS trả về HTML hoặc Text chứa "OK" hoặc "status" ok
        if "OK" in text_resp.upper() or "SUCCESS" in text_resp.upper():
            return {"status": "ok", "message": "Saved successfully"}

        return {"status": "ok", "message": "Processed"}
    except Exception as e:
        logger.error(f"GAS POST error: {e}")
        return {"status": "error", "message": str(e)}


def tg_reply(chat_id: str, text: str):
    """Gửi tin nhắn vào group Telegram."""
    try:
        cid = str(chat_id).strip()
        if not cid.startswith("-") and cid.isdigit():
            cid = "-" + cid
        url = f"https://api.telegram.org/bot{REFUEL_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={
            "chat_id": cid,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=10)
        logger.info(f"tg_reply to {cid}: status={r.status_code}, resp={r.text[:80]}")
    except Exception as e:
        logger.error(f"tg_reply error: {e}")


def answer_inline(query_id: str, query: str):
    """Phản hồi inline query bằng các template."""
    today_str = datetime.now(TZ_MM).strftime("%d/%m/%Y")
    tomorrow_str = (datetime.now(TZ_MM) + timedelta(days=1)).strftime("%d/%m/%Y")
    
    results = [
        {
            "type": "article",
            "id": "refuel",
            "title": "Báo cáo đã đổ dầu (Refueled)",
            "description": "Chèn mẫu báo cáo đã đổ dầu xong (REFUELED)",
            "input_message_content": {
                "message_text": (
                    f"DG Type\n"
                    f"Date: {today_str}\n"
                    f"DG ID: TNIXXXX\n"
                    f"Team: Team X\n"
                    f"Running Hour: \n"
                    f"KWH Hour: \n\n"
                    f"Before:\n"
                    f"CSU Reading (L): \n"
                    f"Level %: \n"
                    f"Liter/cm - ()\n\n"
                    f"After:\n"
                    f"CSU Reading (L): \n"
                    f"Level %: \n"
                    f"Liter/cm - ()\n\n"
                    f"Actual Filled Qty (L): \n"
                    f"Partner price = "
                )
            }
        },
        {
            "type": "article",
            "id": "plan",
            "title": "Kế hoạch đổ dầu (Plan)",
            "description": "Chèn mẫu kế hoạch đổ dầu (PLAN)",
            "input_message_content": {
                "message_text": (
                    f"Plan refuel\n"
                    f"Date: {tomorrow_str}\n"
                    f"Team X\n"
                    f"TNIXXXX 440L\n"
                    f"TNIXXXX 220L"
                )
            }
        },
        {
            "type": "article",
            "id": "request",
            "title": "Yêu cầu cấp dầu (Request)",
            "description": "Chèn mẫu yêu cầu cấp dầu (REQUEST)",
            "input_message_content": {
                "message_text": (
                    f"Request refuel\n"
                    f"Date: {tomorrow_str}\n"
                    f"Team X\n"
                    f"TNIXXXX: 440 L\n"
                    f"TNIXXXX: 220 L"
                )
            }
        },
        {
            "type": "article",
            "id": "letter",
            "title": "Công văn Trình/Duyệt (Letter)",
            "description": "Chèn mẫu công văn trình/duyệt",
            "input_message_content": {
                "message_text": (
                    f"Letter Submit: {today_str}\n"
                    f"Approved Letter: {today_str}"
                )
            }
        }
    ]
    
    # Lọc kết quả theo từ khóa
    q = query.lower().strip()
    if q:
        results = [r for r in results if q in r["title"].lower() or q in r["id"]]
        
    try:
        url = f"https://api.telegram.org/bot{REFUEL_BOT_TOKEN}/answerInlineQuery"
        requests.post(url, json={
            "inline_query_id": query_id,
            "results": results,
            "cache_time": 60
        }, timeout=10)
    except Exception as e:
        logger.error(f"answer_inline error: {e}")


def process_update(update: dict):
    """Xử lý 1 Telegram update."""
    # ── Xử lý Inline Query ──
    if "inline_query" in update:
        iq = update["inline_query"]
        answer_inline(iq["id"], iq.get("query", ""))
        return

    msg = update.get("message") or update.get("channel_post")
    if not msg:
        return

    chat        = msg.get("chat", {})
    raw_chat_id  = chat.get("id", 0)
    norm_chat_id = str(raw_chat_id).replace("-100", "").replace("-", "")
    chat_id      = str(raw_chat_id)
    chat_title   = chat.get("title", "")
    text         = (msg.get("text") or msg.get("caption") or "").strip()

    if not text:
        return

    logger.info(f"Received msg from raw_chat_id={raw_chat_id} (norm={norm_chat_id}, title='{chat_title}'): {text[:50]}")

    if text.startswith("/id") or text.startswith("/chatid") or text.startswith("/start"):
        tg_reply(str(raw_chat_id), f"<b>Chat Title:</b> {chat_title}\n<b>Chat ID:</b> <code>{raw_chat_id}</code>")
        return

    # Chỉ xử lý tin từ group refuel chính
    title_l = chat_title.lower()
    if norm_chat_id != PLAN_GROUP_ID and "refuel" not in title_l and "cross check" not in title_l and "9.1" not in title_l and "9" not in title_l:
        logger.info(f"Skip norm_chat_id={norm_chat_id}")
        return
    # Xử lý các lệnh lấy template
    if text.startswith("/"):
        cmd = text.split()[0].split("@")[0].lower()
        
        if cmd == "/refuel":
            today_str = datetime.now(TZ_MM).strftime("%d/%m/%Y")
            reply_text = (
                f"DG Type\n"
                f"Date: {today_str}\n"
                f"DG ID: TNIXXXX\n"
                f"Team: Team X\n"
                f"Running Hour: \n"
                f"KWH Hour: \n\n"
                f"Before:\n"
                f"CSU Reading (L): \n"
                f"Level %: \n"
                f"Liter/cm - ()\n\n"
                f"After:\n"
                f"CSU Reading (L): \n"
                f"Level %: \n"
                f"Liter/cm - ()\n\n"
                f"Actual Filled Qty (L): \n"
                f"Partner price = "
            )
            tg_reply(chat_id, reply_text)
            return
            
        elif cmd == "/plan":
            tomorrow_str = (datetime.now(TZ_MM) + timedelta(days=1)).strftime("%d/%m/%Y")
            reply_text = f"Team X Plan refuel {tomorrow_str} : TNIXXXX 440L + TNIXXXX 220L"
            tg_reply(chat_id, reply_text)
            return
            
        elif cmd == "/request":
            tomorrow_str = (datetime.now(TZ_MM) + timedelta(days=1)).strftime("%d/%m/%Y")
            reply_text = f"Team X request {tomorrow_str}: TNIXXXX: 440L + TNIXXXX: 220L"
            tg_reply(chat_id, reply_text)
            return
            
        elif cmd == "/letter":
            today_str = datetime.now(TZ_MM).strftime("%d/%m/%Y")
            reply_text = (
                "• Submit Letter:\n"
                f"Letter Submit: {today_str}\n\n"
                "• Approved Letter:\n"
                f"Approved Letter: {today_str}"
            )
            tg_reply(chat_id, reply_text)
            return

        elif cmd == "/monitor":
            today_str = datetime.now(TZ_MM).strftime("%d/%m/%Y")
            reply_text = f"Name of FT staff member accompanying to supervise the quality of premium oil and ensure the correct quantity is poured according to the plan: Paung Aung Soe - {today_str} TNI0213 + 660L, TNI0129 + 660L"
            tg_reply(chat_id, reply_text)
            return
            
        elif cmd in ("/start", "/help"):
            reply_text = (
                "👋 <b>Welcome to TNI Refuel Bot!</b>\n\n"
                "Available template commands:\n"
                "• /refuel - Refueled Report template\n"
                "• /plan - Refuel Plan template\n"
                "• /request - Refuel Request template\n"
                "• /letter - Transport Letter template\n"
                "• /monitor - FT Follow Monitor template\n\n"
                "<i>Tap any command to receive the template, then copy and fill out.</i>"
            )
            tg_reply(chat_id, reply_text)
            return

        logger.info(f"Unknown command {cmd} — skip")
        return

    category = classify(text)
    if not category:
        # Tin nhắn trò chuyện thông thường (không phải báo cáo): Ghi log đọc tin ngầm (non-blocking thread)
        if msg.get("from"):
            f_user = msg["from"]
            s_name = f"{f_user.get('first_name','')} {f_user.get('last_name','')}".strip()
            s_id = str(f_user.get("id", ""))
            if s_id:
                import threading
                th = threading.Thread(
                    target=post_gas,
                    args=({
                        "action": "realtime_read",
                        "group_id": PLAN_GROUP_ID,
                        "sender": s_name,
                        "sender_id": s_id,
                        "text": text[:100],
                    },),
                    daemon=True
                )
                th.start()
                th.join(timeout=2.5)
        logger.info("No keyword match (casual chat logged async) — skip")
        return

    # Lấy tên, ID và username của người gởi (Team Leader)
    sender = ""
    sender_id = ""
    sender_user = ""
    if msg.get("from"):
        f = msg["from"]
        sender = f"{f.get('first_name','')} {f.get('last_name','')}".strip()
        sender_id = str(f.get("id", ""))
        sender_user = f.get("username", "").strip()

    tl_tag = f"@{sender_user}" if sender_user else f"<a href='tg://user?id={sender_id}'>{sender}</a>"

    # Tự động gán tag Team Leader theo số Team hoặc mã Site trong báo cáo (Tag đúng 4 Đội trưởng, không tag nhân viên/đối tác)
    import re
    team_m = re.search(r'\bteam[\s_\-]*0*([1-4])\b', text, re.IGNORECASE)
    t_num = team_m.group(1) if team_m else None
    
    if not t_num:
        site_m = re.search(r'\bTNI0*(\d{1,4})\b', text, re.IGNORECASE)
        if site_m:
            site_no = int(site_m.group(1))
            if site_no <= 200:
                t_num = "1"
            elif site_no <= 400:
                t_num = "2"
            elif site_no <= 600:
                t_num = "3"
            else:
                t_num = "4"

    if t_num == "1":
        mention_tag = "@PaingAung"      # Team 1 Leader: Paing Aung Soe
    elif t_num == "2":
        mention_tag = "@NayMyoThu"      # Team 2 Leader: Nay Myo Thu
    elif t_num == "3":
        mention_tag = "@PyaePhyoZaw"    # Team 3 Leader: Pyae Phyo Zaw
    elif t_num == "4":
        mention_tag = "@NaingMyoHtun"   # Team 4 Leader: Naing Myo Htun
    else:
        mention_tag = tl_tag

    now    = datetime.now(TZ_MM)
    result = post_gas({
        "action":   "collect_message",
        "group_id": PLAN_GROUP_ID,
        "text":     text,
        "sender":   sender,
        "sender_id": sender_id,
        "date":     now.strftime("%d/%m/%Y %H:%M"),
        "category": category,
    })
    logger.info(f"[{category}] sender={sender} | GAS={result.get('status')} def={result.get('def','')}")

    # ── GỬI REPLY XÁC NHẬN KHI GHI THÀNH CÔNG (CHỈ REPLY KHI STATUS LÀ "OK" VÀ CÓ DEF ID HỢP LỆ) ──
    if result.get("status") == "ok" and result.get("def"):
        ts     = result.get("time", now.strftime("%d/%m/%Y %H:%M"))
        def_id = str(result.get("def", "")).strip()

        # 💺 GHẾ 1: DÀNH RIÊNG CHO BÁO CÁO KẾ HOẠCH DẦU (PLAN REFUEL — DUY NHẤT CÓ CÂU HỎI VÀ TAG LEADER)
        if category == "PLAN":
            reply_text = (
                f"⛽ <b>Plan refuel</b> ✅ #{def_id.replace('#', '')} | 🗓️ {ts}\n"
                f"📢 {mention_tag} Who is assigned to follow and monitor ?"
            )
            tg_reply(chat_id, reply_text)
            return

        # 💺 GHẾ 2: DÀNH RIÊNG CHO BÁO CÁO FT FOLLOW MONITOR
        if category == "FT_MONITOR":
            reply_text = (
                f"🔍 <b>FT follow monitor</b> ✅ #{def_id.replace('#', '')} | 🗓️ {ts}\n"
                f"✅ Recorded successfully"
            )
            tg_reply(chat_id, reply_text)
            return

        # 💺 GHẾ 3: DÀNH RIÊNG CHO BÁO CÁO ĐÃ ĐỔ XĂNG THỰC TẾ (REFUELED)
        if category == "REFUELED":
            reply_text = (
                f"⛽ <b>Refueled</b> ✅ #{def_id.replace('#', '')} | 🗓️ {ts}\n"
                f"✅ Recorded successfully"
            )
            tg_reply(chat_id, reply_text)
            return

        # 💺 GHẾ 4: DÀNH RIÊNG CHO BÁO CÁO YÊU CẦU ĐỘI (TEAM REQUEST)
        if category == "REQUEST":
            reply_text = (
                f"📋 <b>Team request</b> ✅ #{def_id.replace('#', '')} | 🗓️ {ts}\n"
                f"✅ Recorded successfully"
            )
            tg_reply(chat_id, reply_text)
            return

        # 💺 GHẾ 5: DÀNH RIÊNG CHO ĐƠN TRÌNH LETTER SUBMIT
        if category == "LETTER_SUBMIT":
            reply_text = (
                f"📋 <b>Letter Submit</b> ✅ Recorded — 🪪 <code>{def_id}</code>\n"
                f"📅 Date: <b>{result.get('date', ts)}</b>"
            )
            tg_reply(chat_id, reply_text)
            return

        # 💺 GHẾ 6: DÀNH RIÊNG CHO ĐƠN DUYỆT LETTER APPROVED
        if category == "LETTER_APPROVED":
            reply_text = (
                f"✅ <b>Letter Approved</b> ✅ Recorded — 🪪 <code>{def_id}</code>\n"
                f"📅 Date: <b>{result.get('date', ts)}</b>"
            )
            tg_reply(chat_id, reply_text)
            return

        # 💺 GHẾ 7: FALLBACK CHUNG CHO CÁC MẪU ĐƠN KHÁC
        reply_text = (
            f"<b>{category}</b> ✅ Recorded — 🪪 <code>{def_id}</code>\n"
            f"Done 📅 {ts}"
        )
        tg_reply(chat_id, reply_text)
    else:
        logger.info(f"[{category}] GAS did not return ok with def ({result}) — skip sending tg_reply")


def _tg_secret_ok(headers, env_name):
    """PM-97 R5: constant-time Telegram webhook secret check when configured; allow if env not set."""
    import hmac as _hmac
    import os as _os
    exp = _os.environ.get(env_name, "").strip().strip('"').strip("'")
    if not exp:
        return True
    got = headers.get("X-Telegram-Bot-Api-Secret-Token", "").strip()
    return bool(got) and _hmac.compare_digest(got.encode("utf-8"), exp.encode("utf-8"))


def run_classifier_self_test() -> dict:
    """Tự kiểm tra 6 mẫu chuẩn của bộ phân loại classify() phục vụ Ghế Giám Sát AUDITOR-3.1 & AUDITOR-9.1."""
    samples = {
        "FT_MONITOR": "Name of FT staff member accompanying to supervise: Paung Aung Soe - 19/10/2026 TNI0213 + 660L",
        "REFUELED": "DG Type\nDate: 19/10/2026\nDG ID: TNI0004\nRunning Hour: 100\nBefore:\nCSU Reading (L): 10\nAfter:\nCSU Reading (L): 200\nActual Filled Qty (L): 190",
        "LETTER_SUBMIT": "Letter Submit: 19/10/2026",
        "LETTER_APPROVED": "Approved Letter: 19/10/2026",
        "PLAN": "Team 1 Plan refuel 20/10/2026 : TNI0061 440L",
        "REQUEST": "Team 1 request 20/10/2026: TNI0129: 440L",
    }
    ok_cats = []
    failed = {}
    for expected, sample_text in samples.items():
        got = classify(sample_text)
        if got == expected:
            ok_cats.append(expected)
        else:
            failed[expected] = got
    return {
        "passed": len(failed) == 0,
        "categories_ok": ok_cats,
        "failed": failed,
    }


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not _tg_secret_ok(self.headers, "REFUEL_WEBHOOK_SECRET"):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'{"error":"Forbidden"}')
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            update = json.loads(body)
            process_update(update)
        except Exception as e:
            logger.error(f"Webhook error: {e}")
        finally:
            # Luôn trả 200 để Telegram không retry
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())

    def do_GET(self):
        st = run_classifier_self_test()
        resp = {
            "status": "ok" if st["passed"] else "error",
            "service": "TNI Refuel Collector",
            "classifier_self_test": "PASS" if st["passed"] else "FAIL",
            "categories_ok": st["categories_ok"],
            "failed": st["failed"],
        }
        self.send_response(200 if st["passed"] else 500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())

    def log_message(self, fmt, *args):
        logger.info(fmt % args)
