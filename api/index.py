import os, re, io, html, json, logging, requests, pandas as pd
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN           = os.environ.get("TELEGRAM_TOKEN", "").strip().strip("\ufeff")
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "").strip().strip("\ufeff")
logger.info(f"APPS_SCRIPT_URL = '{APPS_SCRIPT_URL[:60]}...'")

SPREADSHEET_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8"
BASE_URL       = (f"https://docs.google.com/spreadsheets/d/"
                  f"{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid=")
GID_SITE, GID_TASK, GID_WO = "1095689918", "1755404595", "1429089905"
GID_INFO = "171059303"   # Tab: Name Site / Site / Cable / Gpon / DIA (col A=TNI, B=Site, C=Cable, D=Gpon, E=DIA)
GID_SITE_CLEAR = "610944071"  # Tab: Search Site  Clear
MAX_LEN = 4096
TZ_MM   = timezone(timedelta(hours=6, minutes=30))

_allowed_info_ids = None
_allowed_info_ids_ts = 0.0
ALLOWED_IDS_TTL = 300

def get_allowed_info_search_ids():
    global _allowed_info_ids, _allowed_info_ids_ts
    import time
    if _allowed_info_ids is not None and time.time() - _allowed_info_ids_ts < ALLOWED_IDS_TTL:
        return _allowed_info_ids
    try:
        df = fetch("1236389870")
        allowed_ids = set()
        for idx in range(1, len(df)):
            row = df.iloc[idx]
            if len(row) > 4:
                val = str(row.iloc[4]).strip()
                if val and val != "-" and val.lower() != "nan" and val.lower() != "none":
                    if val.endswith(".0"):
                        val = val[:-2]
                    allowed_ids.add(val)
        _allowed_info_ids = allowed_ids
        _allowed_info_ids_ts = time.time()
        logger.info(f"Loaded allowed Info search IDs: {allowed_ids}")
        return allowed_ids
    except Exception as e:
        logger.error(f"Error fetching allowed info search IDs: {e}")
        if _allowed_info_ids is not None:
            return _allowed_info_ids
        return set()


# ── Telegram helper: gửi tin nhắn ────────────────────────────────────────
def tg_send(chat_id, text, parse_mode="HTML"):
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN chưa cấu hình")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=60,
        )
        if not r.ok:
            logger.error(f"Telegram sendMessage lỗi: {r.text[:200]}")
    except Exception as e:
        logger.error(f"tg_send error: {e}")


# ── Google Sheet helpers ──────────────────────────────────────────────────
def fetch(gid):
    r = requests.get(BASE_URL + gid,
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.content.decode("utf-8", "replace")),
                       header=None, dtype=str, on_bad_lines="skip")

def sv(row, i):
    try:
        v = row.iloc[i]
        s = "" if pd.isna(v) else str(v).strip()
        return "" if s.lower() in ("nan", "none") else s
    except:
        return ""

def site_info(df, tni):
    try:
        lbl  = df.iloc[0]
        rows = df.iloc[1:]
        hit  = rows[rows.iloc[:, 1].str.upper() == tni.upper()]
        if hit.empty:
            return ""
        row, parts = hit.iloc[0], []
        for i in [17, 19, 20, 21, 24, 26]:
            l, v = sv(lbl, i), sv(row, i)
            if not l or v in ("", "0", "0.0"):
                continue
            try:
                n = round(float(v), 1)
                if n:
                    parts.append(f"{l}: {n}")
            except:
                if v:
                    parts.append(f"{l}: {v}")
        return ", ".join(parts)
    except Exception as e:
        logger.error(f"site_info: {e}")
        return ""

def get_tasks(df, tni):
    out = []
    try:
        for _, r in df.iloc[2:].iterrows():
            if sv(r, 19).upper() != tni.upper() or sv(r, 9):
                continue
            out.append(f"{sv(r,3)} : {sv(r,4)} : {sv(r,10)} + {sv(r,7)}")
    except Exception as e:
        logger.error(f"tasks: {e}")
    return out

def get_wos(df, tni):
    out = []
    try:
        for _, r in df.iloc[3:].iterrows():
            if sv(r, 4).upper() != tni.upper():
                continue
            out.append(f"{sv(r,0)} + {sv(r,1)} : {sv(r,2)} + {sv(r,5)}")
    except Exception as e:
        logger.error(f"wos: {e}")
    return out

def get_info(tni):
    """Tìm TNI trong cột A của sheet gid=171059303, trả về B-E."""
    try:
        df = fetch(GID_INFO)
        # Hàng 0 = header (Name Site, Site, Cable, Gpon, DIA)
        rows = df.iloc[1:] if len(df) > 1 else df
        for _, row in rows.iterrows():
            a = sv(row, 0)  # Col A = Name Site (TNI code)
            if a.upper() == tni.upper():
                b = sv(row, 1)  # Col B = Site
                c = sv(row, 2)  # Col C = Cable
                d = sv(row, 3)  # Col D = Gpon
                e_ = sv(row, 4) # Col E = DIA
                return {"site": b, "cable": c, "gpon": d, "dia": e_}
        return None
    except Exception as ex:
        logger.error(f"get_info error: {ex}")
        return None

def build_info_reply(tni, info):
    """Tạo tin nhắn đẹp từ kết quả Info."""
    e = html.escape
    lines = [f"📡 <b>Info: {e(tni)}</b>\n━━━━━━━━━━━━━━━━━━━━"]
    if info.get("site"):
        lines.append(f"\n🏢 <b>Site</b>\n{e(info['site'])}")
    if info.get("cable"):
        lines.append(f"\n🔌 <b>Cable</b>\n{e(info['cable'])}")
    if info.get("gpon"):
        lines.append(f"\n📶 <b>Gpon</b>\n{e(info['gpon'])}")
    if info.get("dia"):
        lines.append(f"\n🌐 <b>DIA</b>\n{e(info['dia'])}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def lookup_clear_site(tni: str) -> str:
    """Tra cứu TNIxxxx trong dòng 4 (index 3) của sheet Search Site Clear (GID 610944071).
    Sheet này nằm trên Spreadsheet Site Down: 1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow."""
    def e(s): return html.escape(str(s))
    tni_upper = tni.upper()

    # Sử dụng Spreadsheet ID riêng biệt của Site Down
    sd_sheet_id = "1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow"
    url = f"https://docs.google.com/spreadsheets/d/{sd_sheet_id}/export?format=csv&gid={GID_SITE_CLEAR}"

    try:
        hdrs = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=hdrs, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        content = resp.content.decode("utf-8", errors="replace")
        df = pd.read_csv(io.StringIO(content), header=None, dtype=str, on_bad_lines="skip")
    except Exception as ex:
        logger.error(f"lookup_clear_site fetch error: {ex}")
        return f"❌ Error loading data: {e(str(ex)[:80])}"

    if df is None or df.empty:
        return "❌ No data available."

    # Dòng 4 trong Sheet là index 3 (0-based) trong pandas DataFrame
    if len(df) <= 3:
        return "❌ Sheet has fewer than 4 rows."

    col_idx = None
    row_3 = df.iloc[3]
    for col in range(1, len(df.columns)):
        val = str(row_3.iloc[col]).strip().upper() if col < len(row_3) else ""
        if val == tni_upper:
            col_idx = col
            break

    if col_idx is None:
        return f"❌ Not found <b>{e(tni_upper)}</b> in Row 4 of Search Site Clear."

    # Lấy toàn bộ dữ liệu của cột đó
    lines = []
    lines.append(f"🔍 <b>Clear History for {e(tni_upper)}</b>")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    for r in range(len(df)):
        val = str(df.iloc[r, col_idx]).strip() if col_idx < len(df.columns) else ""
        label = str(df.iloc[r, 0]).strip() if 0 < len(df.columns) else ""

        # Bỏ qua các giá trị rỗng, nan hoặc gạch ngang
        if not val or val.lower() in ("nan", "", "-"):
            continue

        # Format label cho ngắn gọn
        if label and label.lower() not in ("nan", ""):
            if "newsite" in label.lower() or "salary" in label.lower():
                label = "Site Code"
            lines.append(f"• <b>{e(label)}:</b> {e(val)}")
        else:
            lines.append(f"• {e(val)}")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def build_reply(tni):
    e  = html.escape
    ds = fetch(GID_SITE)
    dt = fetch(GID_TASK)
    dw = fetch(GID_WO)
    si = site_info(ds, tni)
    tk = get_tasks(dt, tni)
    wo = get_wos(dw, tni)
    lines = [f"🔍 <b>{e(tni)}</b>\n━━━━━━━━━━━━━━━━━━━━"]
    if si:
        lines.append(f"\n📍 <b>Site Info</b>\n{e(si)}")
    lines.append(f"\n📋 <b>Task ({len(tk)})</b>")
    lines += [f"• {e(t)}" for t in tk] or ["• No see"]
    lines.append(f"\n🔧 <b>WO ({len(wo)})</b>")
    lines += [f"• {e(w)}" for w in wo] or ["• No see"]
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def split_chunks(text):
    parts, cur = [], ""
    for line in text.split("\n"):
        cand = (cur + "\n" + line) if cur else line
        if len(cand) <= MAX_LEN:
            cur = cand
        else:
            if cur:
                parts.append(cur)
            while len(line) > MAX_LEN:
                parts.append(line[:MAX_LEN])
                line = line[MAX_LEN:]
            cur = line
    if cur:
        parts.append(cur)
    return parts

def send_to_sheet(payload):
    if not APPS_SCRIPT_URL:
        return None
    try:
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=60)
        return r.json()
    except Exception as e:
        logger.error(f"Apps Script error: {e}")
        return None


def handle(data):
    try:
        from api.search_bot import handle as search_bot_handle
        return search_bot_handle(data)
    except Exception as ex:
        try:
            from search_bot import handle as search_bot_handle
            return search_bot_handle(data)
        except Exception:
            logger.error(f"Delegate search_bot_handle failed: {ex}")
    
    msg = data.get("message") or data.get("edited_message")
    if not msg:
        return

    text    = (msg.get("text") or "").strip()
    chat_id = msg.get("chat", {}).get("id")
    user    = msg.get("from") or {}

    if not text or not chat_id:
        return

    user_id   = str(user.get("id", ""))
    full_name = " ".join(filter(None, [
        user.get("first_name", ""),
        user.get("last_name", ""),
    ])).strip() or user.get("username", "Unknown")

    logger.info(f"MSG chat={chat_id} user={user_id} text={text[:60]}")

    # ── /start ────────────────────────────────────────────────────────────
    if text.startswith("/start"):
        tg_send(chat_id,
            "👋 <b>Bot tra cứu TNI</b>\n\n"
            "📌 Gõ mã TNI, ví dụ: <code>TNI0154</code>\n\n"
            "Bot trả về:\n"
            "• 📍 Site Info (alarm)\n"
            "• 📋 Task còn tồn\n"
            "• 🔧 Work Orders\n\n"
            "👤 /myid — Xem Telegram ID của bạn\n"
            "💬 /id   — Xem ID chat này"
        )
        return

    # ── /myid ─────────────────────────────────────────────────────────────
    if text.startswith("/myid"):
        msg_extra = ""
        if APPS_SCRIPT_URL and user_id:
            res = send_to_sheet({
                "action":    "register_user",
                "user_id":   user_id,
                "user_name": full_name,
            })
            if res:
                if res.get("status") == "ok":
                    msg_extra = "\n✅ Đã lưu vào danh sách"
                elif res.get("status") == "duplicate":
                    msg_extra = "\n⚠️ Bạn đã có trong danh sách rồi"
        tg_send(chat_id,
            f"👤 <b>{html.escape(full_name)}</b>\n"
            f"🔑 ID: <code>{user_id}</code>"
            + msg_extra
        )
        return

    # ── /id ───────────────────────────────────────────────────────────────
    if text.startswith("/id"):
        chat      = msg.get("chat", {})
        title     = chat.get("title") or chat.get("username") or "Private"
        chat_type = chat.get("type", "")
        msg_extra = ""
        if APPS_SCRIPT_URL:
            res = send_to_sheet({
                "action":     "register_chat",
                "chat_id":    str(chat_id),
                "chat_title": title,
                "chat_type":  chat_type,
                "reg_by":     full_name,
            })
            if res:
                if res.get("status") == "ok":
                    msg_extra = "\n✅ Đã lưu vào sheet <b>Chat IDs</b>"
                elif res.get("status") == "duplicate":
                    msg_extra = "\n⚠️ Đã có trong sheet rồi"
        tg_send(chat_id,
            f"💬 <b>{html.escape(title)}</b>\n"
            f"🔑 <code>{chat_id}</code>\n"
            f"📍 Type: {chat_type}"
            + msg_extra
        )
        return

    # ── Done: #ID ─────────────────────────────────────────────────────────
    done_match = re.match(r"^done[:\s]+#?(\d+)", text, re.IGNORECASE)
    if done_match:
        ref_id = done_match.group(1)
        now    = datetime.now(TZ_MM)
        res    = send_to_sheet({
            "action":    "done",
            "ref_id":    ref_id,
            "done":      "Done",
            "done_date": now.strftime("%d/%m/%Y"),
            "done_time": now.strftime("%H:%M"),
            "chat_id":   user_id,
        })
        if res and res.get("status") == "ok":
            tg_send(chat_id, f"✅ <b>Marked as Done</b> – Request <b>#{ref_id}</b>")
        elif res and res.get("status") == "denied":
            tg_send(chat_id,
                f"🚫 <b>Not authorised.</b>\n"
                f"ID <code>{user_id}</code> chưa có trong danh sách Config."
            )
        else:
            err = res.get("message", "unknown") if res else "no response"
            tg_send(chat_id, f"⚠️ Không thể update #{ref_id}: {html.escape(str(err))}")
        return

    # ── CLEAR SITE SEARCH (CLEAR TNIxxxx) ────────────────────────
    clear_match = re.match(r"^clear[:\s]+\s*(TNI\w+)", text.strip(), re.IGNORECASE)
    if clear_match:
        tni = clear_match.group(1).upper()
        logger.info(f"Clear site lookup: {tni} | chat={chat_id}")
        tg_send(chat_id, f"⏳ Loading clear data for <b>{html.escape(tni)}</b>...")
        # Ghi log search
        if APPS_SCRIPT_URL and user_id:
            try:
                now = datetime.now(TZ_MM)
                send_to_sheet({
                    "action":    "log_search",
                    "user_name": full_name,
                    "user_id":   user_id,
                    "tni_code":  f"CLEAR {tni}",
                    "date":      now.strftime("%d/%m/%Y"),
                    "time":      now.strftime("%H:%M"),
                })
            except Exception as e:
                logger.error(f"log_search failed: {e}")
        try:
            message = lookup_clear_site(tni)
            tg_send(chat_id, message)
        except Exception as err:
            logger.error(f"Clear lookup error [{tni}]: {err}")
            tg_send(chat_id, f"❌ Error: {html.escape(str(err)[:80])}")
        return

    # ── Info: TNIxxxx — tra cứu cột A→B:E từ sheet gid=171059303 ──────────
    info_match = re.match(r"^info[:\s]+\s*(TNI\w+)", text, re.IGNORECASE)
    if info_match:
        tni = info_match.group(1).upper()
        logger.info(f"Info lookup: {tni} | chat={chat_id}")
        
        # Access control: Only Telegram IDs in Column E of Config sheet (GID 1236389870)
        allowed_ids = get_allowed_info_search_ids()
        user_id_str = str(user_id).strip()
        if user_id_str not in allowed_ids:
            # Simulate searching then return "Not found"
            tg_send(chat_id, f"⏳ Đang tìm thông tin <b>{html.escape(tni)}</b>...")
            import time
            time.sleep(1)
            tg_send(chat_id, f"❌ Không tìm thấy <b>{html.escape(tni)}</b> trong danh sách Site Info.")
            return

        tg_send(chat_id, f"⏳ Đang tìm thông tin <b>{html.escape(tni)}</b>...")
        try:
            info = get_info(tni)
            if info and any(info.values()):
                tg_send(chat_id, build_info_reply(tni, info))
            else:
                tg_send(chat_id,
                    f"❌ Không tìm thấy <b>{html.escape(tni)}</b> trong danh sách Site Info."
                )
        except Exception as err:
            logger.error(f"Info error [{tni}]: {err}")
            tg_send(chat_id, f"❌ Lỗi tra cứu: {html.escape(str(err))}")
        return

    # ── Collector: Order/Revoke/Export/Move ───────────────────────────────
    COLLECTOR_KEYWORDS = ["order:", "revoke:", "export:", "move:"]
    if any(k in text.lower() for k in COLLECTOR_KEYWORDS):
        now = datetime.now(TZ_MM)
        res = send_to_sheet({
            "action":  "add",
            "date":    now.strftime("%d/%m/%Y %H:%M"),
            "chat_id": user_id,
            "msg":     text,
        })
        if res and res.get("status") == "ok":
            row_id = res.get("row", "?")
            tg_send(chat_id,
                f"REQUEST_BOT ✅ Recorded — 🆔 #{row_id}📅 {now.strftime('%d/%m/%Y %H:%M')}"
            )
        else:
            err = res.get("message", "unknown") if res else "no response"
            tg_send(chat_id, f"⚠️ Ghi thất bại: {html.escape(str(err))}")
        return

    # ── TNI lookup ────────────────────────────────────────────────────────
    m = re.search(r"(TNI\w+)", text, re.IGNORECASE)
    if not m:
        return

    tni = m.group(1).upper()
    logger.info(f"Lookup TNI: {tni} | chat={chat_id}")

    tg_send(chat_id, f"⏳ Đang tìm <b>{html.escape(tni)}</b>...")
    try:
        reply  = build_reply(tni)
        parts  = split_chunks(reply)
        # Gửi từng chunk
        for part in parts:
            tg_send(chat_id, part)
        # Log tìm kiếm lên sheet
        if APPS_SCRIPT_URL and user_id:
            now = datetime.now(TZ_MM)
            send_to_sheet({
                "action":    "log_search",
                "user_name": full_name,
                "user_id":   user_id,
                "tni_code":  tni,
                "date":      now.strftime("%d/%m/%Y"),
                "time":      now.strftime("%H:%M"),
            })
    except Exception as err:
        logger.error(f"TNI lookup error [{tni}]: {err}")
        tg_send(chat_id,
            f"❌ <b>Fail</b> – {html.escape(tni)}\n"
            f"<i>{html.escape(str(err))}</i>"
        )


# ── Vercel serverless entry point ─────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            data   = json.loads(self.rfile.read(length))
            handle(data)
        except Exception as e:
            logger.error(f"Webhook error: {e}")
        finally:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def do_GET(self):
        try:
            path = self.path.lower().split("?")[0]
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            target_file = "executive_dashboard.html" if "executive" in path or "dashboard" in path else "index.html"
            file_path = os.path.join(base_dir, target_file)
            
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
        except Exception as e:
            logger.error(f"do_GET serve html error: {e}")

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"TNI BI Platform OK")

    def log_message(self, *a):
        pass
