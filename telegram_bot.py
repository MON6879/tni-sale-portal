import os
import re
import io
import html
import time
import asyncio
import logging
import threading
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    MessageHandler, CommandHandler, filters,
)

# ===================== CONFIG =====================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
TOKEN          = os.getenv("TELEGRAM_TOKEN")

# ── Health-check HTTP server cho Render Web Service ──
def _start_health_server():
    import http.server, socketserver
    port = int(os.getenv("PORT", "8080"))
    class HealthHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, format, *args):
            pass
    try:
        with socketserver.TCPServer(("", port), HealthHandler) as httpd:
            logger.info(f"Health check server listening on port {port}")
            httpd.serve_forever()
    except Exception as e:
        logger.warning(f"Health server error: {e}")

threading.Thread(target=_start_health_server, daemon=True).start()
SPREADSHEET_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8"
# gviz/tq endpoint: trả CSV trực tiếp, không redirect sang CDN googleusercontent.com
BASE_URL       = (
    f"https://docs.google.com/spreadsheets/d/"
    f"{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid="
)

GID_SITE       = "1095689918"   # 'Site down now'   – col B=TNI, cols R,T,U,V,Y,AA = alarm durations
GID_TASK       = "1755404595"   # 'Input task'      – col T=TNI, col J=""=pending, D:E:K+H
GID_WO         = "1429089905"   # 'Input WO'(matrix)– col E=TNI, A+B:C+F
GID_SITE_CLEAR = "610944071"    # Tab: Search Site Clear
GID_STAFF      = "1684930643"   # 'Staff' – col A=Telegram ID, row 1=headers (mysite/mycable/...)

df_site:  pd.DataFrame = None
df_task:  pd.DataFrame = None
df_wo:    pd.DataFrame = None
df_staff: pd.DataFrame = None

# ===================== DAILY REPORT CONFIG =====================
DAILY_APPS_SCRIPT_URL = os.getenv("DAILY_APPS_SCRIPT_URL", "")
DAILY_PHOTO_WINDOW    = 3600   # 60 phút — ảnh gửi sau báo cáo được attach tự động
TZ_MM = timezone(timedelta(hours=6, minutes=30))  # Myanmar UTC+6:30

# Theo dõi lần gửi báo cáo cuối: {chat_id: timestamp}
# Dùng để attach ảnh vào đúng dòng trong vòng 60 phút
_last_daily: dict[int, float] = {}

# Cache fields từ GAS
_daily_fields: list[str]  = []
_daily_fields_ts: float   = 0.0
DAILY_FIELDS_CACHE_SEC    = 600   # refresh mỗi 10 phút

# Fallback fields khi GAS chưa deploy
DAILY_FIELDS_DEFAULT = [
    "Daily report",
    "Transportation Used", "Full Name", "Detail WO", "Detail task",
    "Name Site rescue", "Name Cell rescue", "Resuce Cable",
    "Name and detail Site repair alarm",
    "Name Site follow partner refuel", "Other task",
    "Name and detail Site go busines trip start go",
    "Name and detail Site go busines trip end go",
    "Km moto bike start", "Km moto bike the end",
]

# ===================== LOAD DATA =====================
def fetch_csv(gid: str, has_header: bool = True) -> pd.DataFrame:
    """Tải CSV từ Google Sheet qua requests (xử lý redirect tốt hơn urllib)."""
    url = BASE_URL + gid
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        content = resp.content.decode("utf-8", errors="replace")
        if has_header:
            return pd.read_csv(io.StringIO(content), dtype=str, on_bad_lines="skip")
        else:
            return pd.read_csv(io.StringIO(content), header=None,
                               dtype=str, on_bad_lines="skip")
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            raise RuntimeError("❌ Google Sheet đang bị Khóa (Restricted). Bạn hãy đổi quyền Chia sẻ của Sheet sang 'Bất kỳ ai có đường link đều có thể xem (Viewer)' để Bot đọc dữ liệu.") from e
        raise e


def load_all_sheets():
    global df_site, df_task, df_wo, df_staff
    logger.info("Dang tai 4 sheet tu Google Sheet...")
    # gviz/tq với header=None: row 0 = labels, row 1+ = data
    df_site  = fetch_csv(GID_SITE,  has_header=False)
    df_task  = fetch_csv(GID_TASK,  has_header=False)
    df_wo    = fetch_csv(GID_WO,    has_header=False)
    df_staff = fetch_csv(GID_STAFF, has_header=False)  # Staff: col A=TelegramID, row 1=headers
    logger.info(
        f"OK – Site:{len(df_site)} Task:{len(df_task)} WO:{len(df_wo)} Staff:{len(df_staff)}"
    )


# ===================== HELPER =====================
def safe(row_or_series, idx: int) -> str:
    """Return stripped string value at position idx, or '' if missing/NaN."""
    try:
        v = row_or_series.iloc[idx]
        if pd.isna(v):
            return ""
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none") else s
    except Exception:
        return ""


# ===================== SITE INFO (Formula 1) =====================
def get_site_info(tni: str) -> str:
    """
    'Site down now' (gviz/tq, header=None):
      iloc[0]  = labels (gviz kết hợp tất cả header rows thành 1 dòng)
      iloc[1+] = data   (col index 1 = TNI code = cột B)
    Target alarm cols: R=17, T=19, U=20, V=21, Y=24, AA=26
    """
    if df_site is None or df_site.empty:
        return ""
    try:
        label_row = df_site.iloc[0]   # labels
        data      = df_site.iloc[1:]  # data bắt đầu từ row 1

        # Tìm TNI ở cột số 1 (col B) bằng integer index
        matched = data[data.iloc[:, 1].str.upper() == tni.upper()]
        if matched.empty:
            return ""

        row     = matched.iloc[0]
        targets = [17, 19, 20, 21, 24, 26]  # R, T, U, V, Y, AA
        parts   = []

        for idx in targets:
            label = safe(label_row, idx)
            val   = safe(row, idx)

            if not label or val in ("", "0", "0.0"):
                continue
            try:
                num = round(float(val), 1)
                if num:
                    parts.append(f"{label}: {num}")
            except ValueError:
                if val:
                    parts.append(f"{label}: {val}")

        return ", ".join(parts)
    except Exception as e:
        logger.error(f"get_site_info: {e}")


# ===================== TASKS (Formula 2) =====================
def get_tasks(tni: str) -> list:
    """
    Sheet 'Input task' (gid=1755404595):
      iloc[0] = header (T=19:'Site Name', J=9:'Date complete',
                        D=3:'Group assign', E=4:'Detailed content',
                        K=10:'Remain day', H=7:'Team leader note')
      iloc[1] = summary/totals row
      iloc[2+] = data rows
      Filter: col T==TNI  AND  col J=="" (pending, no completion date)
      Output:  D : E : K + H
    """
    if df_task is None or df_task.empty:
        return []
    tasks = []
    try:
        for _, row in df_task.iloc[2:].iterrows():
            t_val = safe(row, 19)   # T = Site Name
            j_val = safe(row, 9)    # J = completion date (empty = pending)
            if t_val.upper() != tni.upper():
                continue
            if j_val:               # already done
                continue
            d = safe(row, 3)        # D = Group assign
            e = safe(row, 4)        # E = Detailed content
            k = safe(row, 10)       # K = Remain day
            h = safe(row, 7)        # H = Team leader note
            tasks.append(f"{d} : {e} : {k} + {h}")
    except Exception as e:
        logger.error(f"get_tasks: {e}")
    return tasks


# ===================== WORK ORDERS (Formula 3) =====================
def get_wos(tni: str) -> list:
    """
    Sheet 'Input WO' matrix (gid=1429089905):
      iloc[0,1,2] = 3 header rows
      iloc[3+]    = data rows
      col E(4) = site TNI code
      Filter: col E==TNI
      Output: A + B : C + F
    """
    if df_wo is None or df_wo.empty:
        return []
    wos = []
    try:
        for _, row in df_wo.iloc[3:].iterrows():
            e_val = safe(row, 4)    # E = Name Site
            if e_val.upper() != tni.upper():
                continue
            a = safe(row, 0)        # A = WO code
            b = safe(row, 1)        # B = WO Name
            c = safe(row, 2)        # C = amount / score
            f = safe(row, 5)        # F = FT assignee
            wos.append(f"{a} + {b} : {c} + {f}")
    except Exception as e:
        logger.error(f"get_wos: {e}")
    return wos


# ===================== STAFF SHEET LOOKUP =====================
def get_staff_data(sender_id: str, field_name: str | None = None) -> str:
    """
    Tra cứu dữ liệu cá nhân từ Staff sheet (gid=1684930643).
    - Col A (index 0): Telegram ID người dùng
    - Row 1 (index 0): headers — ví dụ: mysite, mycable, myolt, mysn, mydia ...

    field_name=None  → trả về tất cả cột có header bắt đầu bằng 'my'
    field_name=str   → trả về giá trị cột đó cho người dùng
    """
    def e(s): return html.escape(str(s))

    # Lấy data mới nhất (fetch trực tiếp không dùng cache global, luôn fresh)
    try:
        df = fetch_csv(GID_STAFF, has_header=False)
    except Exception as ex:
        logger.error(f"get_staff_data fetch: {ex}")
        return f"❌ Error loading Staff data: {e(str(ex)[:80])}"

    if df is None or df.empty:
        return "❌ Staff sheet empty."

    # Row 0 = header, Row 1+ = data
    headers = df.iloc[0]
    data    = df.iloc[1:]

    # Tìm row có col A = sender_id
    matched = data[data.iloc[:, 0].astype(str).str.strip() == str(sender_id).strip()]
    if matched.empty:
        return f"❌ No data found for your Telegram ID in Staff sheet.\nYour ID: <code>{e(sender_id)}</code>"

    row = matched.iloc[0]

    def clean_val(v: str) -> str:
        """Bỏ các giá trị rỗng / lỗi công thức."""
        return "" if v.lower() in ("nan", "none", "", "#n/a", "#na", "#ref!", "#value!") else v

    if field_name is None:
        # Trả về TẤT CẢ cột có header chứa 'my' (Q1:U1 và các cột tương tự)
        results = []
        for col_idx in range(len(headers)):
            h = str(headers.iloc[col_idx]).strip()
            if h.lower().startswith("my") and h.lower() not in ("nan", "none", ""):
                val = clean_val(safe(row, col_idx))
                results.append(f"• <b>{e(h)}:</b> {e(val) if val else '—'}")
        if not results:
            return "ℹ️ No 'my*' columns found in Staff sheet."
        return (
            "👤 <b>My Stats</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(results)
            + "\n━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        # Tìm cột có header khớp field_name (case-insensitive)
        target_col = None
        for col_idx in range(len(headers)):
            h = str(headers.iloc[col_idx]).strip().lower()
            if h == field_name.lower():
                target_col = col_idx
                break
        if target_col is None:
            return f"❌ Column '<b>{e(field_name)}</b>' not found in Staff sheet headers."
        val = clean_val(safe(row, target_col))
        if not val:
            return f"ℹ️ <b>{e(field_name)}:</b> (empty)"
        return f"📊 <b>{e(field_name)}:</b>\n{e(val)}"


# ===================== MAIN LOOKUP =====================
def lookup_tni(tni: str) -> str:
    """Delegates to SSOT perform_unified_tni_search for Toa 1 Task & WO lookup."""
    try:
        from api.search_bot import perform_unified_tni_search
        return perform_unified_tni_search(tni, full_info=False)
    except Exception as err:
        logger.error(f"lookup_tni error fallback: {err}")
        def e(s: str) -> str: return html.escape(str(s))
        lines = [f"🔍 <b>{e(tni)}</b>\n━━━━━━━━━━━━━━━━━━━━"]
        tasks = get_tasks(tni)
        lines.append(f"\n📋 <b>Task ({len(tasks)})</b>")
        if tasks:
            lines += [f"• {e(t)}" for t in tasks]
        wos = get_wos(tni)
        lines.append(f"\n🔧 <b>WO ({len(wos)})</b>")
        if wos:
            lines += [f"• {e(w)}" for w in wos]
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


MAX_LEN = 4096

def split_messages(text: str) -> list:
    """Tách text thành các chunk ≤ 4096 ký tự, cắt theo dòng."""
    chunks = []
    current = ""
    for line in text.split("\n"):
        candidate = (current + "\n" + line) if current else line
        if len(candidate) <= MAX_LEN:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # Nếu 1 dòng đơn lẻ vẫn quá dài, cắt cứng
            while len(line) > MAX_LEN:
                chunks.append(line[:MAX_LEN])
                line = line[MAX_LEN:]
            current = line
    if current:
        chunks.append(current)
    return chunks


# ================================================================
#  DAILY REPORT — Thu thập báo cáo hàng ngày + công tác
# ================================================================

def fetch_daily_fields() -> list[str]:
    """Lấy danh sách field từ GAS (cached 10 phút)."""
    global _daily_fields, _daily_fields_ts
    now = time.time()
    if _daily_fields and (now - _daily_fields_ts) < DAILY_FIELDS_CACHE_SEC:
        return _daily_fields
    if not DAILY_APPS_SCRIPT_URL:
        return DAILY_FIELDS_DEFAULT
    try:
        resp = requests.get(
            DAILY_APPS_SCRIPT_URL + "?action=get_fields",
            timeout=10          # GAS phải trả về < 10s, không retry
        )
        data = resp.json()
        if data.get("status") == "ok" and data.get("fields"):
            _daily_fields    = data["fields"]
            _daily_fields_ts = now
            logger.info(f"📋 Daily fields loaded: {_daily_fields}")
            return _daily_fields
    except Exception as ex:
        logger.warning(f"⚠️ fetch_daily_fields: {ex}")
    return _daily_fields or DAILY_FIELDS_DEFAULT


def parse_daily_report(text: str, fields: list[str]) -> dict:
    """
    Parse nội dung người dùng gửi dạng 'Field: value'.
    Hỗ trợ nhiều dòng, ghép nội dung xuống dòng vào field trước.
    """
    result: dict[str, str] = {}
    cur_key: str | None = None
    cur_val: list[str]  = []

    def flush():
        if cur_key:
            result[cur_key] = " ".join(cur_val).strip()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            colon  = line.index(":")
            label  = line[:colon].strip()
            val    = line[colon + 1:].strip()
            # Tìm field khớp (không phân biệt hoa thường)
            matched = None
            label_l = label.lower()
            
            # Nếu label chứa chữ "result" hoặc "daily", tự động khớp với "Daily report"
            if "result" in label_l or "daily" in label_l:
                for f in fields:
                    if f.lower() == "daily report":
                        matched = f
                        break
            
            if not matched:
                for f in fields:
                    f_l = f.lower()
                    if f_l in label_l or label_l in f_l:
                        matched = f
                        break
            if matched:
                flush()
                cur_key = matched
                cur_val = [val] if val else []
                continue
        # Dòng không khớp field → nối vào field trước
        if cur_key:
            cur_val.append(line)

    flush()
    return result


def is_daily_report(text: str) -> bool:
    """Có chữ 'daily' hoặc 'result' (không phân biệt hoa thường) là daily report.
    Loại trừ các tin báo cáo tự động của hệ thống (Report 5, 6, site down...).
    """
    text_l = text.lower()
    # Bỏ qua tin báo cáo tự động — không phải daily report của nhân viên
    skip_keywords = [
        "note read report",     # Report 6 — Daily Note Read Report
        "read window:",         # Report 6 header
        "submission history",   # Report 5C — Plan Morning
        "3-day completion",     # Report 5C
        "5.1 report",           # Report 5C header
        "5. report",            # Report 5 header
        "plan content:",        # Report 5C plan content section
        "team leader: submitted",
        "team leader: not submitted",
        "site down",            # Site down reports
        "1. report", "2. report", "3. report", "4. report",
        "6. report", "7. report",
    ]
    if any(kw in text_l for kw in skip_keywords):
        return False
    return "daily" in text_l or "result" in text_l


async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /daily — Gửi mẫu báo cáo để nhân viên copy-paste."""
    fields = fetch_daily_fields()
    now_mm = datetime.now(TZ_MM)
    date_s = now_mm.strftime("%d/%m/%Y")

    lines = [f"Daily report: {date_s}"]
    for f in fields[1:]:
        lines.append(f"{f}:")
    template = "\n".join(lines)

    await update.message.reply_text(template)


async def submit_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Tự động nhận báo cáo khi tin nhắn chứa chữ 'daily'.
    Trả về True nếu đã xử lý.
    """
    text = update.message.text or ""
    if not is_daily_report(text):
        return False

    fields  = fetch_daily_fields()
    parsed  = parse_daily_report(text, fields)
    now_mm  = datetime.now(TZ_MM)
    user    = update.effective_user
    chat_id = update.effective_chat.id

    # Tự thêm ngày nếu chưa có
    if "Daily report" not in parsed:
        parsed["Daily report"] = now_mm.strftime("%d/%m/%Y")

    if not DAILY_APPS_SCRIPT_URL or DAILY_APPS_SCRIPT_URL.startswith("CHƯA"):
        await update.message.reply_text(
            "❌ Bot chưa cấu hình DAILY_APPS_SCRIPT_URL"
        )
        return True

    payload = {
        "action":      "daily_add",
        "telegram_id": str(user.id),
        "fields":      parsed,
    }

    def _post_gas():
        """Blocking POST tới GAS — chạy trong thread pool (không block event loop)."""
        for attempt in range(2):          # thử tối đa 2 lần
            try:
                r = requests.post(DAILY_APPS_SCRIPT_URL, json=payload, timeout=30)
                return r.json()
            except Exception:
                if attempt == 1:
                    raise

    try:
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _post_gas)
        if result.get("status") == "ok":
            name = result.get("name") or user.first_name or str(user.id)
            ref  = result.get("ref", "")
            _last_daily[chat_id] = time.time()   # lưu để attach ảnh
            ref_line = f" | REF:{ref}" if ref else ""
            await update.message.reply_text(
                f"✅ Đã lưu{ref_line} — {html.escape(str(name))}\n"
                f"📅 {now_mm.strftime('%d/%m/%Y %H:%M')}"
            )
        else:
            await update.message.reply_text(
                f"❌ Lỗi lưu\n{result.get('message', '')[:120]}"
            )
    except Exception as ex:
        logger.error(f"submit_daily_report: {ex}")
        await update.message.reply_text(f"❌ Kết nối GAS timeout, thử lại sau\n{str(ex)[:60]}")

    return True


async def handle_daily_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Nhận ảnh trong vòng 60 phút sau khi gửi báo cáo → lưu Drive qua GAS."""
    chat_id = update.effective_chat.id
    last_ts = _last_daily.get(chat_id, 0)

    # Chỉ xử lý nếu trong vòng DAILY_PHOTO_WINDOW giây kể từ lần gửi báo cáo cuối
    if time.time() - last_ts > DAILY_PHOTO_WINDOW:
        return
    if not DAILY_APPS_SCRIPT_URL or DAILY_APPS_SCRIPT_URL.startswith("CHƯA"):
        return

    user  = update.effective_user
    photo = update.message.photo[-1]   # chất lượng cao nhất
    try:
        f       = await context.bot.get_file(photo.file_id)
        tg_url  = f"https://api.telegram.org/file/bot{TOKEN}/{f.file_path}"
        payload = {
            "action":      "daily_photo",
            "telegram_id": str(user.id),
            "tg_url":      tg_url,
        }
        resp   = requests.post(DAILY_APPS_SCRIPT_URL, json=payload, timeout=60)
        result = resp.json()
        _last_daily[chat_id] = time.time()   # gia hạn window
        await update.message.reply_text("📷 ✅" if result.get("status") == "ok" else "📷 ❌")
    except Exception as ex:
        logger.error(f"handle_daily_photo: {ex}")
        await update.message.reply_text("📷 ❌")


# ===================== BOT HANDLERS =====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # ── 1. Daily report: tin nhắn có chữ "daily" → lưu sheet
    if is_daily_report(text):
        await submit_daily_report(update, context)
        return

    # ── 1.3 Staff lookup: "mysite", "mycable", "mydia"... hoặc range "Q1:U1"
    #    → Tra cứu dữ liệu cá nhân theo Telegram ID người gửi
    text_lower = text.lower().strip()
    is_my_field = (
        text_lower.startswith("my")
        and len(text_lower) > 2
        and " " not in text_lower
        and not text_lower.startswith("myo")    # tránh khớp MyOther keywords
    )
    is_range_query = bool(re.match(r'^[A-Z]\d+:[A-Z]\d+$', text, re.IGNORECASE))
    if is_my_field or is_range_query:
        sender_id = str(update.effective_user.id)
        # Range → trả về tất cả cột my*; field cụ thể → trả về đúng cột
        field = None if is_range_query else text_lower
        reply = get_staff_data(sender_id, field)
        chunks = split_messages(reply)
        await update.message.reply_text(chunks[0], parse_mode="HTML")
        for chunk in chunks[1:]:
            await update.message.reply_text(chunk, parse_mode="HTML")
        return

    # ── 1.5 CLEAR Site Search
    clear_match = re.match(r"^clear[:\s]+\s*(TNI\w+)", text, re.IGNORECASE)
    if clear_match:
        tni = clear_match.group(1).upper()
        logger.info(f"Clear site lookup: {tni}")
        wait_msg = await update.message.reply_text(
            f"⏳ Loading clear data for <b>{html.escape(tni)}</b>...", parse_mode="HTML"
        )
        try:
            reply = lookup_clear_site(tni)
            chunks = split_messages(reply)
            await wait_msg.edit_text(chunks[0], parse_mode="HTML")
            for chunk in chunks[1:]:
                await update.message.reply_text(chunk, parse_mode="HTML")

            # Log tìm kiếm (fire & forget)
            apps_url = os.getenv("APPS_SCRIPT_URL", "")
            if apps_url:
                user = update.effective_user
                from datetime import datetime, timezone, timedelta
                now_mm = datetime.now(timezone(timedelta(hours=6, minutes=30)))
                payload = {
                    "action":    "log_search",
                    "user_name": user.full_name or user.first_name or str(user.id),
                    "user_id":   str(user.id),
                    "tni_code":  tni,            # log TNI code thuần, không có prefix CLEAR
                    "date":      now_mm.strftime("%d/%m/%Y"),
                    "time":      now_mm.strftime("%H:%M"),
                }
                threading.Thread(
                    target=lambda p=payload, u=apps_url: requests.post(u, json=p, timeout=8),
                    daemon=True,
                ).start()
        except Exception as err:
            logger.error(f"Clear search error [{tni}]: {err}")
            await wait_msg.edit_text(
                f"❌ <b>Error</b> – CLEAR {html.escape(tni)}\n<i>{html.escape(str(err))}</i>",
                parse_mode="HTML",
            )
        return

    # ── 1.8 INFO Site Search (info: TNIxxxx / info TNIxxxx) ──────────────
    info_match = re.match(r"^\s*(?:/info|info)[:\s]+\s*(TNI\d{4}(?:_\d+)?)\s*$", text.strip(), re.IGNORECASE)
    if info_match:
        tni = info_match.group(1).upper()
        logger.info(f"Info site lookup: {tni}")
        try:
            info = _tni_info_index.get(tni)
            if not info or not any(info.values()):
                await update.message.reply_text(f"❌ No site/cable/DIA info for <b>{html.escape(tni)}</b>", parse_mode="HTML")
                return
            lines = [f"🔍 <b>{html.escape(tni)}</b>\n━━━━━━━━━━━━━━━━━━━━"]
            if info.get("site"):
                site_raw = info['site']
                clean_lines = []
                for line in site_raw.splitlines():
                    ll = line.lower()
                    if "📋 task" in ll or "🔧 wo" in ll or "task (" in ll or "wo (" in ll:
                        break
                    clean_lines.append(line)
                clean_site = "\n".join(clean_lines).strip()
                if clean_site:
                    lines.append(f"\n🏢 <b>Site Info</b>\n{html.escape(clean_site[:500])}")
            if info.get("cable"):
                lines.append(f"\n🔌 <b>Cable</b>\n{html.escape(info['cable'][:500])}")
            if info.get("gpon"):
                lines.append(f"\n📶 <b>Gpon</b>\n{html.escape(info['gpon'][:300])}")
            if info.get("dia"):
                dia_text = info["dia"]
                suffix = "..." if len(dia_text) > 500 else ""
                lines.append(f"\n🌐 <b>DIA</b>\n{html.escape(dia_text[:500])}{suffix}")
            reply = "\n".join(lines)
            for chunk in split_messages(reply):
                await update.message.reply_text(chunk, parse_mode="HTML")
        except Exception as err:
            logger.error(f"Info search error [{tni}]: {err}")
            await update.message.reply_text(f"❌ <b>Error</b> – INFO {html.escape(tni)}", parse_mode="HTML")
        return

    # ── 2. TNI Lookup (existing logic)
    tni_match = re.match(r"^\s*(?:/tni|/find|tni)?[:\s]*\b(TNI\d{4}(?:_\d+)?)\s*$", text.strip(), re.IGNORECASE)
    if not tni_match:
        return
    tni      = tni_match.group(1).upper()
    logger.info(f"Lookup: {tni}")
    wait_msg = await update.message.reply_text(
        f"⏳ Searching <b>{html.escape(tni)}</b>...", parse_mode="HTML"
    )
    try:
        reply  = lookup_tni(tni)
        chunks = split_messages(reply)
        # Sửa tin nhắn "đang tìm" thành chunk đầu tiên
        await wait_msg.edit_text(chunks[0], parse_mode="HTML")
        # Gửi các chunk còn lại (nếu tin nhắn quá dài)
        for chunk in chunks[1:]:
            await update.message.reply_text(chunk, parse_mode="HTML")

        # ── Ghi log tìm kiếm (fire & forget, không chờ) ──
        apps_url = os.getenv("APPS_SCRIPT_URL", "")
        if apps_url:
            user      = update.effective_user
            from datetime import datetime, timezone, timedelta
            now_mm    = datetime.now(timezone(timedelta(hours=6, minutes=30)))
            # Normalize: bỏ suffix _01, _02 → base site code cho dashboard
            tni_log   = re.sub(r"_\d+$", "", tni)
            payload   = {
                "action":    "log_search",
                "user_name": user.full_name or user.first_name or str(user.id),
                "user_id":   str(user.id),
                "tni_code":  tni_log,
                "date":      now_mm.strftime("%d/%m/%Y"),
                "time":      now_mm.strftime("%H:%M"),
            }
            threading.Thread(
                target=lambda p=payload, u=apps_url: requests.post(u, json=p, timeout=10),
                daemon=True,
            ).start()

    except Exception as err:
        logger.error(f"handle_message error [{tni}]: {err}")
        await wait_msg.edit_text(
            f"❌ <b>Error</b> – {html.escape(tni)}\n<i>{html.escape(str(err))}</i>",
            parse_mode="HTML",
        )


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trả về tên + ID của chat hiện tại và lưu vào Google Sheet."""
    chat     = update.effective_chat
    user     = update.effective_user
    chat_id  = str(chat.id)
    title    = chat.title or chat.full_name or "Private"
    reg_by   = user.full_name or user.first_name or str(user.id)

    apps_url = os.getenv("APPS_SCRIPT_URL", "")
    saved    = False
    msg_extra = ""
    if apps_url:
        try:
            r = requests.post(apps_url, json={
                "action":     "register_chat",
                "chat_id":    chat_id,
                "chat_title": title,
                "chat_type":  chat.type,
                "reg_by":     reg_by,
            }, timeout=60)
            res = r.json()
            if res.get("status") == "ok":
                saved     = True
                msg_extra = "\n✅ Saved to <b>Chat IDs</b> sheet"
            elif res.get("status") == "duplicate":
                msg_extra = "\n⚠️ Already exists in sheet"
        except Exception as ex:
            logger.error(f"register_chat error: {ex}")

    await update.message.reply_text(
        f"💬 <b>{html.escape(title)}</b>\n"
        f"🔑 <code>{chat_id}</code>\n"
        f"📍 Type: {chat.type}"
        + msg_extra,
        parse_mode="HTML",
    )


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mỗi người tự gõ /myid → bot hiện ID cá nhân + lưu vào Config sheet."""
    user      = update.effective_user
    user_id   = str(user.id)
    full_name = user.full_name or user.first_name or "Unknown"

    apps_url  = os.getenv("APPS_SCRIPT_URL", "")
    msg_extra = ""
    if apps_url:
        try:
            r = requests.post(apps_url, json={
                "action":    "register_user",
                "user_id":   user_id,
                "user_name": full_name,
            }, timeout=60)
            res = r.json()
            if res.get("status") == "ok":
                msg_extra = "\n✅ Added to report list"
            elif res.get("status") == "duplicate":
                msg_extra = "\n⚠️ You are already in the list"
        except Exception as ex:
            logger.error(f"register_user error: {ex}")

    await update.message.reply_text(
        f"👤 <b>{html.escape(full_name)}</b>\n"
        f"🔑 ID: <code>{user_id}</code>"
        + msg_extra,
        parse_mode="HTML",
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>TNI Search Bot</b>\n\n"
        "📌 Type TNI code, e.g.: <code>TNI0154</code>\n\n"
        "Bot returns:\n"
        "• 📍 Site Info (alarm)\n"
        "• 📋 Pending Tasks\n"
        "• 🔧 Work Orders\n\n"
        "⚙️ /reload – Reload data\n"
        "⚙️ /help   – Help",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Help</b>\n\n"
        "Type any TNI code, e.g.: <code>TNI0154</code>\n\n"
        "/reload – Reload data from Google Sheet",
        parse_mode="HTML",
    )


async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Reloading data...")
    try:
        load_all_sheets()
        await update.message.reply_text(
            f"✅ <b>Reload successful!</b>\n"
            f"• Site: {max(0,len(df_site)-2)} sites\n"
            f"• Task: {max(0,len(df_task)-2)} tasks\n"
            f"• WO:   {max(0,len(df_wo)-3)} WOs",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {html.escape(str(e))}",
                                        parse_mode="HTML")


def get_site_access_template(site_id: str = "TNI0401", date_str: str = None) -> str:
    if not site_id or site_id.startswith("/"):
        site_id = "TNI0401"
    if not date_str:
        from datetime import datetime, timezone, timedelta
        mm_now = datetime.now(timezone(timedelta(hours=6, minutes=30)))
        date_str = mm_now.strftime("%d/%m/%Y")
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


async def cmd_siteaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    site_id = "TNI0401"
    if context.args:
        site_id = context.args[0].upper().strip()
    reply = get_site_access_template(site_id)
    await update.message.reply_text(reply)


async def post_init(application):
    from telegram import BotCommand, BotCommandScopeAllPrivateChats
    commands = [
        BotCommand("request_enter_site", "Request enter Site towerco format"),
        BotCommand("mysite", "All Site you control"),
        BotCommand("mycable", "All your cable route"),
        BotCommand("mymw", "All your MW link"),
        BotCommand("mydia", "All your customer DIA control"),
        BotCommand("myolt", "All Site have OLT"),
        BotCommand("mysn", "All SN you control"),
        BotCommand("mydata", "All your personal stats"),
        BotCommand("daily", "Daily report template"),
        BotCommand("plan", "Daily plan template"),
        BotCommand("help", "Show help menu"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        await application.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
        logger.info("✅ Set bot menu commands successfully")
    except Exception as e:
        logger.warning(f"set_my_commands error: {e}")


# ===================== ENTRY POINT =====================
async def main():
    if not TOKEN:
        raise RuntimeError("Thieu TELEGRAM_TOKEN trong file .env!")

    load_all_sheets()

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler(["request_enter_site", "request_site_enter", "site_access", "siteaccess", "site_enter", "request_site"], cmd_siteaccess))
    app.add_handler(CommandHandler("start",  start_command))
    app.add_handler(CommandHandler("help",   help_command))
    app.add_handler(CommandHandler("reload", reload_command))
    app.add_handler(CommandHandler("id",     id_command))
    app.add_handler(CommandHandler("myid",   myid_command))
    app.add_handler(CommandHandler("daily",  cmd_daily))        # Daily report
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message
    ))
    app.add_handler(MessageHandler(
        filters.PHOTO, handle_daily_photo                        # Ảnh daily report
    ))

    logger.info("Bot TNI dang lang nghe...")
    async with app:
        await app.start()
        await app.updater.start_polling()
        logger.info("Bot ONLINE!")
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
