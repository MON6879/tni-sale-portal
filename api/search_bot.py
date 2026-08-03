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
import os, re, io, json, html, time, asyncio, logging, requests, threading
import pandas as pd
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
BOT_VERSION = "v3.6"

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN                 = os.environ.get("TELEGRAM_TOKEN", "").strip().strip("\ufeff")
DAILY_APPS_SCRIPT_URL = os.environ.get("DAILY_APPS_SCRIPT_URL", "").strip().strip("\ufeff")
APPS_SCRIPT_URL       = os.environ.get("APPS_SCRIPT_URL", "").strip().strip("\ufeff")
SPREADSHEET_ID        = os.environ.get("SPREADSHEET_ID", "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8").strip().strip("\ufeff")
BASE_URL              = (
    f"https://docs.google.com/spreadsheets/d/"
    f"{SPREADSHEET_ID}/export?format=csv&gid="
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

# ── CSV loader with per-GID caching ───────────────────────────────────────────
_csv_cache = {}
_csv_cache_ts = {}
CSV_CACHE_TTL = 1800   # 30 phút cache cho mỗi GID (giảm latency từ 6s xuống <0.001s, chống Telegram Webhook Retry)

def fetch_csv(gid: str) -> pd.DataFrame:
    now = time.time()
    if gid in _csv_cache and (now - _csv_cache_ts.get(gid, 0)) < CSV_CACHE_TTL:
        return _csv_cache[gid]
    try:
        url  = BASE_URL + gid
        hdrs = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=hdrs, timeout=8, allow_redirects=True)
        resp.raise_for_status()
        content = resp.content.decode("utf-8", errors="replace")
        df = pd.read_csv(io.StringIO(content), header=None, dtype=str, on_bad_lines="skip")
        _csv_cache[gid] = df
        _csv_cache_ts[gid] = now
        return df
    except Exception as e:
        logger.error(f"fetch_csv error [gid={gid}]: {e}")
        if gid in _csv_cache:
            return _csv_cache[gid]
        raise e

def get_site_access_template(site_id: str = "TNI0401", date_str: str = None) -> str:
    if not site_id or site_id.startswith("/"):
        site_id = "TNI0401"
    if not date_str:
        from datetime import datetime
        mm_now = datetime.now(TZ_MM)
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

# ── Data cache (module-level, shared within Vercel instance) ──────────────────
_df_site: pd.DataFrame | None = None
_df_task: pd.DataFrame | None = None
_df_wo:   pd.DataFrame | None = None
_cache_ts: float = 0.0
CACHE_TTL = 1800   # 30 phút

# ── Daily fields cache ────────────────────────────────────────────────────────
_daily_fields: list[str] = []
_daily_fields_ts: float  = 0.0
DAILY_FIELDS_TTL = 600   # 10 phút

_df_staff: pd.DataFrame | None = None
_df_staff_ts: float = 0.0
STAFF_TTL = 900   # 15 phút

def get_staff_df() -> pd.DataFrame:
    global _df_staff, _df_staff_ts
    import time
    now_ts = time.time()
    
    should_reload = False
    if _df_staff is None:
        should_reload = True
    else:
        try:
            # Check if it has passed 23:00 MM time on a new day
            last_mm = datetime.fromtimestamp(_df_staff_ts, tz=TZ_MM)
            now_mm = datetime.now(TZ_MM)
            if now_mm.date() > last_mm.date():
                if now_mm.hour >= 23:
                    should_reload = True
            elif (now_ts - _df_staff_ts) > 86400:  # Fallback 24 hours
                should_reload = True
        except Exception:
            should_reload = True

    if _df_staff is not None and not should_reload:
        return _df_staff

    try:
        df = fetch_csv(GID_STAFF)
        _df_staff = df
        _df_staff_ts = now_ts
        return df
    except Exception as e:
        logger.error(f"get_staff_df fetch error: {e}")
        if _df_staff is not None:
            return _df_staff
        raise e

_allowed_info_ids: set[str] | None = None
_allowed_info_ids_ts: float = 0.0
ALLOWED_IDS_TTL = 300 # 5 minutes cache

def get_allowed_info_search_ids() -> set[str]:
    global _allowed_info_ids, _allowed_info_ids_ts
    import time
    if _allowed_info_ids is not None and time.time() - _allowed_info_ids_ts < ALLOWED_IDS_TTL:
        return _allowed_info_ids
    try:
        df = fetch_csv("1236389870")
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

DAILY_FIELDS_DEFAULT = [
    "Daily Result",
    "Full Name",
    "Transportation Used",
    "I. Hot task rescue Site down >24 :",
    "II Hot task Cell rescue",
    "III. Hot task Repair DG abnomal",
    "IV. Hot task Repair DG run>16H:",
    "V. Hot task other:",
    "VII. Detail WO",
    "VII. Detail task",
    "Name and detail Site go busines trip start go",
    "Name and detail Site go busines trip end go",
    "Km moto bike start",
    "Km moto bike the end",
]

# ── Telegram API helper ───────────────────────────────────────────────────────
TG_API = f"https://api.telegram.org/bot{TOKEN}"

def tg_send(chat_id: int, text: str, parse_mode: str = "HTML", reply_markup: dict | None = None) -> None:
    """Gửi tin nhắn Telegram, tự chia chunk nếu > 4096 ký tự."""
    chunks = split_messages(text)
    for i, chunk in enumerate(chunks):
        markup = reply_markup if i == len(chunks) - 1 else None
        if chat_id > 0 and not markup:
            markup = {"remove_keyboard": True}
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if markup:
            payload["reply_markup"] = markup
        try:
            r = requests.post(
                f"{TG_API}/sendMessage",
                json=payload,
                timeout=10,
            )
            if r.status_code != 200:
                logger.error(f"tg_send API error: {r.status_code} {r.text[:200]}")
                # Fallback: nếu lỗi HTML parse entity -> tự động gửi dạng plain text để không bị mất tin!
                if "can't parse entities" in r.text or "BAD_REQUEST" in r.text or "parse" in r.text.lower():
                    payload.pop("parse_mode", None)
                    payload["text"] = re.sub(r"<[^>]+>", "", chunk)
                    requests.post(f"{TG_API}/sendMessage", json=payload, timeout=10)
        except Exception as ex:
            logger.error(f"tg_send error: {ex}")

def tg_get_file(file_id: str) -> str | None:
    """Lấy file_path từ Telegram."""
    try:
        resp = requests.get(f"{TG_API}/getFile?file_id={file_id}", timeout=10)
        data = resp.json()
        if data.get("ok"):
            return data["result"]["file_path"]
    except Exception as ex:
        logger.error(f"tg_get_file: {ex}")
    return None

# ── CSV loader: duplicate def đã xóa — dùng cached version ở trên ──────────

def log_search_bg(user_name: str, user_id, tni_code: str) -> None:
    """Ghi log search — non-daemon, join(3s) để chạy trong Vercel window."""
    if not APPS_SCRIPT_URL:
        return
    def _do():
        try:
            now_mm = datetime.now(TZ_MM)
            requests.post(APPS_SCRIPT_URL, json={
                "action":    "log_search",
                "user_name": user_name,
                "user_id":   str(user_id),
                "tni_code":  tni_code,
                "date":      now_mm.strftime("%d/%m/%Y"),
                "time":      now_mm.strftime("%H:%M"),
                "date_iso":  now_mm.strftime("%d/%m/%Y"),
            }, timeout=3)
        except Exception as e:
            logger.error(f"log_search_bg failed: {e}")
    # Daemon=True: log analytics không critical — chấp nhận mất trên Vercel
    threading.Thread(target=_do, daemon=True).start()

def load_all_sheets():
    """Load TẤT CẢ 5 sheet SONG SONG — giảm tổng thời gian từ 15s xuống 1.5s."""
    global _df_site, _df_task, _df_wo, _df_staff, _cache_ts
    if time.time() - _cache_ts < CACHE_TTL and _df_site is not None:
        return
    import concurrent.futures
    try:
        logger.info("Loading 5 sheets in parallel...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            f_site  = executor.submit(fetch_csv, GID_SITE)
            f_task  = executor.submit(fetch_csv, GID_TASK)
            f_wo    = executor.submit(fetch_csv, GID_WO)
            f_staff = executor.submit(fetch_csv, GID_STAFF)
            f_tlwc  = executor.submit(fetch_csv, GID_TL_WAITCD)
            _df_site  = f_site.result(timeout=10)
            _df_task  = f_task.result(timeout=10)
            _df_wo    = f_wo.result(timeout=10)
            _df_staff = f_staff.result(timeout=10)
            _f_tlwc_res = f_tlwc.result(timeout=10)
        _cache_ts = time.time()
        logger.info(f"Loaded ALL 5 sheets OK — Site:{len(_df_site)} Task:{len(_df_task)} WO:{len(_df_wo)} Staff:{len(_df_staff)}")
    except Exception as ex:
        logger.error(f"load_all_sheets error: {ex}")

# ── TNI lookup helpers ────────────────────────────────────────────────────────
def safe(row, idx: int) -> str:
    try:
        v = row.iloc[idx]
        if pd.isna(v): return ""
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none") else s
    except Exception:
        return ""

def get_site_info(tni: str) -> str:
    if _df_site is None or _df_site.empty: return ""
    try:
        label_row = _df_site.iloc[0]
        data      = _df_site.iloc[1:]
        matched   = data[data.iloc[:, 1].str.upper() == tni.upper()]
        if matched.empty: return ""
        row  = matched.iloc[0]
        parts = []
        for idx in [17, 19, 20, 21, 24, 26]:
            label = safe(label_row, idx)
            val   = safe(row, idx)
            if not label or val in ("", "0", "0.0"): continue
            try:
                num = round(float(val), 1)
                if num: parts.append(f"{label}: {num}")
            except ValueError:
                if val: parts.append(f"{label}: {val}")
        return ", ".join(parts)
    except Exception as ex:
        logger.error(f"get_site_info: {ex}")
        return ""

def get_tasks(tni: str) -> list:
    if _df_task is None or _df_task.empty: return []
    tasks = []
    try:
        for _, row in _df_task.iloc[2:].iterrows():
            if safe(row, 19).upper() != tni.upper(): continue
            if safe(row, 9): continue   # already done
            d = safe(row, 3); e = safe(row, 4)
            k = safe(row, 10); h = safe(row, 7)
            tasks.append(f"{d} : {e} : {k} + {h}")
    except Exception as ex:
        logger.error(f"get_tasks: {ex}")
    return tasks

def get_wos(tni: str) -> list:
    if _df_wo is None or _df_wo.empty: return []
    wos = []
    try:
        for _, row in _df_wo.iloc[3:].iterrows():
            if safe(row, 4).upper() != tni.upper(): continue
            a = safe(row, 0); b = safe(row, 1)
            c = safe(row, 2); f = safe(row, 5)
            wos.append(f"{a} + {b} : {c} + {f}")
    except Exception as ex:
        logger.error(f"get_wos: {ex}")
    return wos

def lookup_tni(tni: str) -> str:
    """Tra cứu TNIxxxx từ cột H (nội dung gộp sẵn) trong sheet Tên Sum WO."""
    def e(s): return html.escape(str(s))
    tni_upper = tni.upper()

    try:
        df = fetch_csv(GID_TEAM_SUM)
    except Exception as ex:
        logger.error(f"lookup_tni fetch error: {ex}")
        return f"❌ Error loading data: {e(str(ex)[:80])}"

    if df is None or df.empty:
        return "❌ No data available."

    # Tìm row có cột B (index 1) = TNI code
    for _, row in df.iterrows():
        col_b = safe(row, 1).strip().upper()
        if col_b != tni_upper:
            continue
        col_h = safe(row, 7)  # Cột H (index 7) = nội dung gộp sẵn
        if not col_h:
            continue

        # Hiển thị nguyên nội dung cột H
        clean = col_h.strip().lstrip("~ ").strip()
        return f"🔍 <b>{e(tni_upper)}</b>\n━━━━━━━━━━━━━━━━━━━━\n{e(clean)}\n━━━━━━━━━━━━━━━━━━━━"

    return f"❌ No data found for <b>{e(tni_upper)}</b>"

def lookup_clear_site(tni: str) -> str:
    """Tra cứu TNIxxxx trong dòng 4 (index 3) của sheet Search Site Clear (GID 610944071).
    Sheet này nằm trên Spreadsheet Site Down: 1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow."""
    def e(s): return html.escape(str(s))
    tni_upper = tni.upper()

    # Sử dụng Spreadsheet ID riêng biệt của Site Down
    sd_sheet_id = os.environ.get("SD_SPREADSHEET_ID", "1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow").strip()
    url = f"https://docs.google.com/spreadsheets/d/{sd_sheet_id}/export?format=csv&gid={GID_SITE_CLEAR}"

    try:
        hdrs = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=hdrs, timeout=10, allow_redirects=True)
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

# ── Staff personal lookup ──────────────────────────────────────────────
def get_staff_data(sender_id: int | str, field_name: str | None = None) -> str:
    """
    Tra cứu dữ liệu cá nhân từ Staff sheet (gid=1684930643).
    - Col A (index 0) : Telegram ID người dùng
    - Row 1 (index 0) : headers — mysite, mycable, myolt, mysn, mydia ...
    field_name=None → trả tất cả cột bắt đầu bằng 'my'
    field_name=str  → trả cột đó
    """
    def e(s): return html.escape(str(s))
    try:
        df = get_staff_df()   # row 0 = headers, row 1+ = data
    except Exception as ex:
        logger.error(f"get_staff_data fetch: {ex}")
        return f"❌ Error loading Staff data: {e(str(ex)[:80])}"
    if df is None or df.empty:
        return "❌ Staff sheet empty."

    headers = df.iloc[0]
    data    = df.iloc[1:]

    # Tìm row có col A = sender_id (so sánh string, bỏ ".0" nếu có)
    sid = str(sender_id).strip()
    col_a = data.iloc[:, 0].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    matched = data[col_a == sid]
    if matched.empty:
        return (
            f"❌ No data found for your Telegram ID in Staff sheet.\n"
            f"Your ID: <code>{e(sid)}</code>"
        )
    row = matched.iloc[0]

    def clean(v: str) -> str:
        return "" if v.strip().lower() in ("nan","none","","#n/a","#na","#ref!","#value!") else v.strip()

    if field_name is None or field_name.lower() == "mydata":
        # Trả tất cả cột 'my*'
        parts = []
        for i in range(len(headers)):
            h = clean(str(headers.iloc[i]))
            if h.lower().startswith("my"):
                v = clean(safe(row, i))
                parts.append(f"• <b>{e(h)}:</b> {e(v) if v else '—'}")
        if not parts:
            return "ℹ️ No 'my*' columns found in Staff sheet."
        return "\n".join([
            "👤 <b>My Stats Summary</b>",
            "━" * 20,
            *parts,
            "━" * 20,
        ])
    else:
        # Tìm cột khớp field_name
        target = None
        fn_low = field_name.lower()
        for i in range(len(headers)):
            if clean(str(headers.iloc[i])).lower() == fn_low:
                target = i
                break
        if target is None:
            return f"❌ Column '<b>{e(field_name)}</b>' not found in Staff sheet."
        v = clean(safe(row, target))
        if not v:
            return f"ℹ️ <b>{e(field_name)}:</b> (empty)"
        return f"📊 <b>{e(field_name)}:</b>\n{e(v)}"


def split_messages(text: str) -> list:
    chunks, current = [], ""
    for line in text.split("\n"):
        candidate = (current + "\n" + line) if current else line
        if len(candidate) <= MAX_LEN:
            current = candidate
        else:
            if current: chunks.append(current)
            while len(line) > MAX_LEN:
                chunks.append(line[:MAX_LEN]); line = line[MAX_LEN:]
            current = line
    if current: chunks.append(current)
    return chunks

def split_by_site_blocks(blocks: list[str]) -> list[str]:
    """Ghép các site block lại thành tin nhắn, mỗi tin <= MAX_LEN.
    Mỗi block là 1 site hoàn chỉnh — không bao giờ bị cắt giữa chừng."""
    messages, current = [], ""
    for block in blocks:
        candidate = (current + "\n" + block) if current else block
        if len(candidate) <= MAX_LEN:
            current = candidate
        else:
            if current:
                messages.append(current)
            # Nếu 1 block > MAX_LEN, dùng split_messages để chia nhỏ
            if len(block) > MAX_LEN:
                messages.extend(split_messages(block))
                current = ""
            else:
                current = block
    if current:
        messages.append(current)
    return messages


# ── Team Leader search (T1/T2/T3/T4) ─────────────────────────────────────
def lookup_team(team_code: str) -> list[str]:
    """Tra cứu tất cả site thuộc team (T1/T2/T3/T4) từ sheet Tên Sum WO.
    Đọc trực tiếp cột G (index 6) — nội dung đã gộp sẵn."""
    team_code_upper = team_code.upper()
    team_names = {
        "T1": "Team 1 — Dawei",
        "T2": "Team 2 — Myeik",
        "T3": "Team 3 — Bokpyin",
        "T4": "Team 4 — Kawthoung",
    }
    team_label = team_names.get(team_code_upper, team_code_upper)

    try:
        df = fetch_csv(GID_TEAM_SUM)
    except Exception as ex:
        logger.error(f"lookup_team fetch error: {ex}")
        return [f"❌ Error loading data: {html.escape(str(ex)[:80])}"]

    if df is None or df.empty:
        return ["❌ No data available."]

    # Gom nội dung cột J từ các row có cột I = team code
    raw_entries = []
    for _, row in df.iterrows():
        col_i = safe(row, 8).strip().upper()  # Cột I = filter tag
        if col_i != team_code_upper:
            continue
        col_j = safe(row, 9)  # Cột J = nội dung gộp sẵn
        if col_j:
            raw_entries.append(col_j)

    if not raw_entries:
        return [f"❌ No sites found for <b>{html.escape(team_code_upper)}</b>"]

    # Gộp tất cả rồi tách theo ~ cho mỗi site
    full_raw = " ".join(raw_entries)
    sites = [s.strip() for s in full_raw.split("~") if s.strip()]

    # Header
    now_mm = datetime.now(TZ_MM)
    header = (
        f"🔍 <b>{html.escape(team_label)}</b> — "
        f"{len(sites)} sites\n"
        f"📅 {now_mm.strftime('%d/%m/%Y %H:%M')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    # Build site blocks — mỗi site 1 block
    site_blocks = []
    for site_text in sites:
        # Tách <+> thành các dòng riêng với bullet
        parts = [p.strip() for p in site_text.split("<+>") if p.strip()]
        lines = []
        for p in parts:
            lines.append(f"• {html.escape(p)}")
        site_blocks.append("\n".join(lines))

    if not site_blocks:
        return [f"❌ No sites found for <b>{html.escape(team_code_upper)}</b>"]

    # Ghép header vào block đầu
    site_blocks[0] = header + site_blocks[0]
    site_blocks[-1] = site_blocks[-1] + "\n━━━━━━━━━━━━━━━━━━━━"

    return split_by_site_blocks(site_blocks)


# ── Not Close search (T1notclose / T2notclose / ...) ─────────────────────────
def lookup_notclose(team_code: str) -> list[str]:
    """Tra cứu WO chưa close của team từ sheet 'Team leader Wait CD + Not Close'.
    Lọc theo cột H (index 7). Hiển thị cột B,C,E,F,G (bỏ D)."""
    tag = f"{team_code.upper()}NOTCLOSE"  # e.g. "T1NOTCLOSE"
    team_names = {
        "T1": "Team 1 — Dawei",
        "T2": "Team 2 — Myeik",
        "T3": "Team 3 — Bokpyin",
        "T4": "Team 4 — Kawthoung",
    }
    team_label = team_names.get(team_code.upper(), team_code.upper())

    try:
        df = fetch_csv(GID_TL_WAITCD)
    except Exception as ex:
        logger.error(f"lookup_notclose fetch error: {ex}")
        return [f"❌ Error loading data: {html.escape(str(ex)[:80])}"]

    if df is None or df.empty:
        return ["❌ No data available."]

    entries = []
    for _, row in df.iterrows():
        col_ar = safe(row, 43).strip().upper()  # Cột AR = filter tag
        if col_ar != tag:
            continue
        col_as = safe(row, 44)  # Cột AS = nội dung gộp sẵn
        if col_as:
            entries.append(col_as)

    if not entries:
        return [f"❌ No WO Not Close found for <b>{html.escape(team_code.upper())}</b>"]

    # Gộp tất cả rồi tách theo ~ cho mỗi WO
    full_raw = " ".join(entries)
    items = [s.strip() for s in full_raw.split("~") if s.strip()]

    now_mm = datetime.now(TZ_MM)
    header = (
        f"🔴 <b>{html.escape(team_label)} — WO Not Close</b>\n"
        f"📅 {now_mm.strftime('%d/%m/%Y %H:%M')}\n"
        f"📊 Total: {len(items)} WOs\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    # Mỗi item hiển thị nguyên, tách | thành dòng mới
    lines = []
    for item in items:
        parts = [p.strip() for p in item.split("|") if p.strip()]
        lines.append("• " + "\n  ".join(html.escape(p) for p in parts))

    full_text = header + "\n".join(lines) + "\n━━━━━━━━━━━━━━━━━━━━"
    return split_messages(full_text)


# ── Wait CD search (T1waitcd / T2waitcd / ...) ───────────────────────────────
def lookup_waitcd(team_code: str) -> list[str]:
    """Tra cứu WO đang chờ CD của team từ sheet 'Team leader Wait CD + Not Close'.
    Lọc theo cột AM (index 38). Hiển thị cột AG,AH,AJ,AK,AL (bỏ AI)."""
    tag = f"{team_code.upper()}WAITCD"  # e.g. "T1WAITCD"
    team_names = {
        "T1": "Team 1 — Dawei",
        "T2": "Team 2 — Myeik",
        "T3": "Team 3 — Bokpyin",
        "T4": "Team 4 — Kawthoung",
    }
    team_label = team_names.get(team_code.upper(), team_code.upper())

    try:
        df = fetch_csv(GID_TL_WAITCD)
    except Exception as ex:
        logger.error(f"lookup_waitcd fetch error: {ex}")
        return [f"❌ Error loading data: {html.escape(str(ex)[:80])}"]

    if df is None or df.empty:
        return ["❌ No data available."]

    entries = []
    for _, row in df.iterrows():
        col_ao = safe(row, 40).strip().upper()  # Cột AO = filter tag
        if col_ao != tag:
            continue
        col_ap = safe(row, 41)  # Cột AP = nội dung gộp sẵn
        if col_ap:
            entries.append(col_ap)

    if not entries:
        return [f"❌ No WO Wait CD found for <b>{html.escape(team_code.upper())}</b>"]

    # Gộp tất cả rồi tách theo ~ cho mỗi WO
    full_raw = " ".join(entries)
    items = [s.strip() for s in full_raw.split("~") if s.strip()]

    now_mm = datetime.now(TZ_MM)
    header = (
        f"🟡 <b>{html.escape(team_label)} — WO Wait CD</b>\n"
        f"📅 {now_mm.strftime('%d/%m/%Y %H:%M')}\n"
        f"📊 Total: {len(items)} WOs\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
    )

    lines = []
    for item in items:
        parts = [p.strip() for p in item.split("|") if p.strip()]
        lines.append("• " + "\n  ".join(html.escape(p) for p in parts))

    full_text = header + "\n".join(lines) + "\n━━━━━━━━━━━━━━━━━━━━"
    return split_messages(full_text)


# ── Info lookup (Site/Cable/Gpon/DIA) ─────────────────────────────────────
def get_info(tni: str) -> dict | None:
    """Tìm TNI trong sheet gid=171059303, trả về Site/Cable/Gpon/DIA."""
    try:
        df = fetch_csv(GID_INFO)
        if df is None or df.empty:
            return None
        tni_upper = tni.upper().strip()
        rows = df.iloc[1:] if len(df) > 1 else df
        for _, row in rows.iterrows():
            col_a = safe(row, 0).upper().strip()
            if not col_a:
                continue
            code_part = col_a.split(":")[0].strip()
            if code_part == tni_upper or col_a == tni_upper or col_a.startswith(tni_upper):
                site_val  = safe(row, 1)
                cable_val = safe(row, 2)
                gpon_val  = safe(row, 3)
                dia_val   = safe(row, 4)
                if any([site_val, cable_val, gpon_val, dia_val]):
                    return {
                        "site":  site_val,
                        "cable": cable_val,
                        "gpon":  gpon_val,
                        "dia":   dia_val,
                    }
        return None
    except Exception as ex:
        logger.error(f"get_info error: {ex}")
        return None

def build_info_reply(tni: str, info: dict) -> str:
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

# ── Daily Report ──────────────────────────────────────────────────────────────
def fetch_daily_fields() -> list[str]:
    global _daily_fields, _daily_fields_ts
    now = time.time()
    if _daily_fields and (now - _daily_fields_ts) < DAILY_FIELDS_TTL:
        return _daily_fields
    if not DAILY_APPS_SCRIPT_URL:
        return DAILY_FIELDS_DEFAULT
    try:
        resp = requests.get(DAILY_APPS_SCRIPT_URL + "?action=get_fields", timeout=10)
        data = resp.json()
        if data.get("status") == "ok" and data.get("fields"):
            _daily_fields    = data["fields"]
            _daily_fields_ts = now
            return _daily_fields
    except Exception as ex:
        logger.warning(f"fetch_daily_fields: {ex}")
    return _daily_fields or DAILY_FIELDS_DEFAULT

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
            
            # Nếu label chứa chữ "result" hoặc "daily", tự động khớp với "Daily report"
            if "result" in label_l or "daily" in label_l:
                for f in fields:
                    if f.lower() == "daily report":
                        matched = f
                        break
            
            if not matched:
                for f in fields:
                    if f.lower() in label_l or label_l in f.lower():
                        matched = f; break
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
    if "daily result" not in text_l:
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

def send_daily_template(chat_id: int) -> None:
    fields = fetch_daily_fields()
    now_mm = datetime.now(TZ_MM)
    lines  = [f"Daily result: {now_mm.strftime('%d/%m/%Y')}"]
    for i, f in enumerate(fields[1:], start=1):
        lines.append(f"{i}. {f}:")
    template = "\n".join(lines)
    
    tg_send(chat_id,
        f"📋 <b>Daily Result Template</b>\n"
        f"Copy → Edit → Send back:\n\n"
        f"<pre>{html.escape(template)}</pre>"
    )

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

def get_plan_template_text(team_num: int) -> str:
    try:
        df = get_staff_df()
        if df is None or df.empty:
            return "Error loading staff data"
        
        data = df.iloc[2:]
        team_str = f"Team 0{team_num}"
        
        matched_staff = []
        for idx, row in data.iterrows():
            row_team = str(row.iloc[12]).strip()
            probation_status = str(row.iloc[13]).strip().lower()
            if "resign" in probation_status or "nghi" in probation_status or "nghỉ" in probation_status:
                continue
                
            if row_team.lower() == team_str.lower() or row_team.lower() == f"team {team_num}":
                full_name = str(row.iloc[5]).strip()
                if full_name and full_name.lower() != "nan" and full_name != "-":
                    if full_name not in matched_staff:
                        matched_staff.append(full_name)
                    
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
        
        for i, name in enumerate(matched_staff, start=1):
            lines.append(f"{i}. {name}: ")
            
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"get_plan_template_text error: {e}")
        return f"Error: {str(e)}"

_recent_plan_sends = {}

def send_daily_plan_template(chat_id: int, team_num: int) -> None:
    now_ts = time.time()
    key = f"{chat_id}:{team_num}"
    if (now_ts - _recent_plan_sends.get(key, 0)) < 6.0:
        logger.info(f"Skipping duplicate send_daily_plan_template for chat {chat_id}")
        return
    _recent_plan_sends[key] = now_ts

    template = get_plan_template_text(team_num)
    tg_send(chat_id,
        f"📋 <b>Daily Plan Template (Team {team_num})</b>\n"
        f"Copy → Edit → Send back:\n\n"
        f"<pre>{html.escape(template)}</pre>"
    )

_recent_help_sends = {}

def send_help_menu(chat_id: int) -> None:
    now_ts = time.time()
    if (now_ts - _recent_help_sends.get(chat_id, 0)) < 6.0:
        logger.info(f"Skipping duplicate send_help_menu for chat {chat_id}")
        return
    _recent_help_sends[chat_id] = now_ts

    tg_send(chat_id,
        "👋 <b>TNI Search Bot</b>\n\n"
        "• Lookup Task/WO: Type <code>TNI0001</code> or <code>/tni TNI0001</code>\n"
        "• Lookup Not Close: Type <code>t1notclose</code>, <code>t2notclose</code>...\n"
        "• Lookup Wait CD: Type <code>t1waitcd</code>, <code>t2waitcd</code>...\n"
        "• Personal Lookup: Type <code>mysite</code>, <code>mycable</code>, <code>mydata</code>...\n"
        "• Get Report Templates: Type <code>/daily</code> or <code>/plan</code>",
        parse_mode="HTML")

_recent_daily_submits = {}

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
    update_id = update.get("update_id")
    if update_id:
        if update_id in _processed_updates:
            logger.info(f"Ignoring duplicate Telegram update_id: {update_id}")
            return
        _processed_updates.add(update_id)
        if len(_processed_updates) > 1000:
            _processed_updates.clear()

    ensure_webhook_active()
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return

    chat_id    = msg["chat"]["id"]
    user       = msg.get("from", {})
    user_id    = user.get("id", 0)
    first_name = user.get("first_name", "")

    # 🛑 BỎ QUA TIN NHẮN TỪ BOT KHÁC HOẶC BẢN THÂN BOT
    if user.get("is_bot"):
        return

    # Warm-up / ensure all 5 sheets are loaded in parallel
    load_all_sheets()

    # ── PHOTO ──────────────────────────────────────────────────────────────
    if "photo" in msg:
        # Lấy ảnh chất lượng cao nhất
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
    if "plan" in text_l and "📋" in text:
        if "t1" in text_l or "1" in text_l:
            text = "/plan T1"
        elif "t2" in text_l or "2" in text_l:
            text = "/plan T2"
        elif "t3" in text_l or "3" in text_l:
            text = "/plan T3"
        elif "t4" in text_l or "4" in text_l:
            text = "/plan T4"
        else:
            text = "/plan"
    elif text_l in ("help", "❓ help", "help ❓", "/help") or text_l == "❓":
        text = "/help"

    if any(kw in text_l for kw in ("request enter site", "request site enter", "site access format", "site access", "site enter")):
        parts = text.split(maxsplit=1)
        passed_site = parts[1].upper().strip() if len(parts) > 1 and parts[1].upper().startswith("TNI") else "TNI0401"
        reply = get_site_access_template(passed_site)
        tg_send(chat_id, reply)
        return

    # ── UNIFIED COMMAND NORMALIZATION: Tự động loại bỏ '/' và '@bot_username' ──
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        first_word = parts[0][1:].lower().split("@")[0]  # e.g. "/t4notclose@bot" -> "t4notclose"
        rest = parts[1] if len(parts) > 1 else ""
        
        # Xử lý các hệ thống lệnh chính
        if first_word in ("request_enter_site", "request_site_enter", "site_access", "siteaccess", "site_enter", "request_site"):
            passed_site = rest.upper().strip() if rest else "TNI0401"
            reply = get_site_access_template(passed_site)
            tg_send(chat_id, reply)
            return

        # /ping — diagnostic command, phản hồi tức thì
        if first_word == "ping":
            tg_send(chat_id, f"🏓 pong {BOT_VERSION} | chat={chat_id} | user={user_id}")
            return

        elif first_word in ("start", "help"):
            if rest.upper().startswith("PLAN_T"):
                team_num_str = rest[6:]
                if team_num_str.isdigit():
                    send_daily_plan_template(chat_id, int(team_num_str))
                    return
            send_help_menu(chat_id)
            return

        elif first_word == "daily":
            send_daily_template(chat_id)
            return

        elif first_word in ("plan", "dailyplan"):
            team_num = None
            if rest:
                team_arg = rest.upper()
                m = re.match(r"^(T(?:EAM)?\s*([1-4])|[1-4])$", team_arg, re.IGNORECASE)
                if m:
                    team_num = int(m.group(2) if m.group(2) else m.group(1))
            
            title = (msg.get("chat", {}).get("title") or "").upper()
            if not team_num:
                m_title = re.search(r"TEAM\s*([1-4])", title)
                if m_title:
                    team_num = int(m_title.group(1))

            if not team_num:
                TELEGRAM_GROUPS = {
                    "T1": -1004215695747,
                    "T2": -1004480845549,
                    "T3": -1004369170658,
                    "T4": -1004293741999,
                }
                def norm_id(cid):
                    return str(cid).replace("-100", "").replace("-", "")
                for k, gid in TELEGRAM_GROUPS.items():
                    if norm_id(chat_id) == norm_id(gid):
                        if k.startswith("T") and k[1:].isdigit():
                            team_num = int(k[1:])
                            break

            if not team_num:
                team_num = get_user_team_number(user_id)
            
            if not team_num:
                team_num = 1
            
            send_daily_plan_template(chat_id, team_num)
            return

        elif first_word in ("id", "myid"):
            chat_title = msg["chat"].get("title") or first_name or "Private"
            chat_type  = msg["chat"].get("type", "private")
            msg_extra  = ""
            if APPS_SCRIPT_URL:
                try:
                    r = requests.post(APPS_SCRIPT_URL, json={
                        "action":     "register_chat" if first_word == "id" else "register_user",
                        "chat_id":    str(chat_id),
                        "chat_title": chat_title,
                        "chat_type":  chat_type,
                        "reg_by":     first_name,
                        "user_id":    str(user_id),
                        "user_name":  first_name,
                    }, timeout=10)
                    res = r.json()
                    if res.get("status") == "ok":
                        msg_extra = "\n✅ Saved"
                    elif res.get("status") == "duplicate":
                        msg_extra = "\n⚠️ Already exists"
                except Exception:
                    pass
            tg_send(chat_id,
                f"👤 <b>{html.escape(first_name)}</b>\n"
                f"🔑 ID: <code>{user_id}</code>\n"
                f"💬 Chat: <code>{chat_id}</code>\n"
                f"📍 Type: {chat_type}"
                + msg_extra)
            return

        elif first_word == "reload":
            global _cache_ts
            _cache_ts = 0
            load_all_sheets()
            tg_send(chat_id, "✅ Data reloaded")
            return

        elif first_word == "tni":
            if rest:
                text = rest
            else:
                tg_send(chat_id, "🔍 Gõ mã trạm sau lệnh, ví dụ: <code>/tni TNI0001</code>")
                return
        else:
            # Tự động chuyển tất cả các lệnh gõ '/' khác (như /t4notclose, /t1waitcd, /mysite) thành chuỗi thô để tra cứu đồng nhất
            text = f"{first_word} {rest}".strip()

    # ── DAILY REPORT ────────────────────────────────────────────────────────
    if is_daily(text):
        submit_daily(chat_id, user_id, first_name, text)
        return

    # ── STAFF PERSONAL LOOKUP: "mysite" / "mycable" / ... hoặc range "Q1:U1" ──
    text_low = text.lower().strip()
    is_my_field    = (text_low.startswith("my") and len(text_low) > 2 and " " not in text_low)
    is_range_query = bool(re.match(r'^[A-Z]\d+:[A-Z]\d+$', text, re.IGNORECASE))
    if is_my_field or is_range_query:
        field = None if is_range_query else text_low
        reply = get_staff_data(user_id, field)
        tg_send(chat_id, reply)
        return

    # ── TEAM LEADER SEARCH (T1/T2/T3/T4) — BỎ khỏi Nhóm (chỉ chạy trong Chat Riêng) ──
    chat_type = msg.get("chat", {}).get("type", "private")
    team_match = re.match(r"^(T[1-4])$", text.strip(), re.IGNORECASE)
    if team_match:
        if chat_type == "private":
            team_code = team_match.group(1).upper()
            logger.info(f"Team lookup: {team_code} | chat={chat_id}")
            tg_send(chat_id, f"⏳ Loading <b>{html.escape(team_code)}</b> data...")
            log_search_bg(first_name or str(user_id), user_id, team_code)
            try:
                messages = lookup_team(team_code)
                for msg_txt in messages:
                    tg_send(chat_id, msg_txt)
            except Exception as err:
                logger.error(f"Team lookup error [{team_code}]: {err}")
                tg_send(chat_id, f"❌ Error: {html.escape(str(err)[:80])}")
        return

    # ── NOT CLOSE SEARCH (T1notclose / T1 not close / T1_notclose ...) ──────
    nc_match = re.match(r"^(T[1-4])[\s_]?(not[\s_]?close|notclose)$", text.strip(), re.IGNORECASE)
    if nc_match:
        team_code = nc_match.group(1).upper()
        logger.info(f"NotClose lookup: {team_code} | chat={chat_id}")
        tg_send(chat_id, f"⏳ Loading <b>{html.escape(team_code)} Not Close</b> data...")
        log_search_bg(first_name or str(user_id), user_id, f"{team_code}notclose")
        try:
            messages = lookup_notclose(team_code)
            for msg_txt in messages:
                tg_send(chat_id, msg_txt)
        except Exception as err:
            logger.error(f"NotClose lookup error [{team_code}]: {err}")
            tg_send(chat_id, f"❌ Error: {html.escape(str(err)[:80])}")
        return

    # ── WAIT CD SEARCH (T1waitcd / T1 wait cd / T1_waitcd ...) ──────────────
    wc_match = re.match(r"^(T[1-4])[\s_]?(wait[\s_]?cd|waitcd)$", text.strip(), re.IGNORECASE)
    if wc_match:
        team_code = wc_match.group(1).upper()
        logger.info(f"WaitCD lookup: {team_code} | chat={chat_id}")
        tg_send(chat_id, f"⏳ Loading <b>{html.escape(team_code)} Wait CD</b> data...")
        log_search_bg(first_name or str(user_id), user_id, f"{team_code}waitcd")
        try:
            messages = lookup_waitcd(team_code)
            for msg_txt in messages:
                tg_send(chat_id, msg_txt)
        except Exception as err:
            logger.error(f"WaitCD lookup error [{team_code}]: {err}")
            tg_send(chat_id, f"❌ Error: {html.escape(str(err)[:80])}")
        return

    # ── 1. KEY "CLEAR": CLEAR TNIxxxx — tra cứu Lịch sử Clear Site ──────────────
    clear_match = re.search(r"\bclear[:\s]+\s*(TNI\w+)", text.strip(), re.IGNORECASE)
    if clear_match:
        tni = clear_match.group(1).upper()
        logger.info(f"Clear site lookup: {tni} | chat={chat_id}")
        tg_send(chat_id, f"⏳ Loading clear data for <b>{html.escape(tni)}</b>...")
        log_search_bg(first_name or str(user_id), user_id, f"CLEAR {tni}")
        try:
            message = lookup_clear_site(tni)
            tg_send(chat_id, message)
        except Exception as err:
            logger.error(f"Clear lookup error [{tni}]: {err}")
            tg_send(chat_id, f"❌ Error: {html.escape(str(err)[:80])}")
        return

    # ── 2. KEY "INFO": Info: TNIxxxx / Info TNIxxxx / Info:TNIxxxx ───────────────
    info_match = re.search(r"^\s*info[:\s]+\s*(TNI\w+)", text.strip(), re.IGNORECASE)
    if info_match:
        tni = info_match.group(1).upper()
        logger.info(f"Info lookup: {tni} | chat={chat_id}")
        log_search_bg(first_name or str(user_id), user_id, f"Info:{tni}")
        try:
            info = get_info(tni)
            if info and any(info.values()):
                reply = build_info_reply(tni, info)
                for chunk in split_messages(reply):
                    tg_send(chat_id, chunk)
            else:
                # Không tìm thấy trong GID_INFO → CHỈ báo không tìm thấy, KHÔNG fallback sang Task/WO
                tg_send(chat_id, f"❌ <b>Info: {html.escape(tni)}</b> — không tìm thấy trong Site Info sheet.\n💡 Dùng <b>{html.escape(tni)}</b> (không có 'Info:') để tra Task & WO.")
        except Exception as err:
            logger.error(f"Info error [{tni}]: {err}")
            tg_send(chat_id, f"❌ Lookup error: {html.escape(str(err))}")
        return

    # ── 3. KEY "TNI": TNIxxxx — tra cứu Task & WO (chỉ khi câu lệnh BẮT ĐẦU bằng TNI, /tni, /find) ──
    text_clean = text.strip()
    text_l = text_clean.lower()

    # CHỈ TRA CỨU NẾU TIN NHẮN BẮT ĐẦU BẰNG 'tni', '/tni', '/find'
    # Nếu TNI nằm ở giữa/cuối đoạn chat trò chuyện (vd: "V Hot task: TNI0067...") -> KHÔNG TRA CỨU
    if not (text_l.startswith("tni") or text_l.startswith("/tni") or text_l.startswith("/find")):
        return

    if text_l.startswith("/tni") or text_l.startswith("/find"):
        parts = text_clean.split(maxsplit=1)
        if len(parts) > 1:
            text_clean = parts[1].strip()
        else:
            return

    # Tìm tất cả mã TNI (lấy mã TNI đầu tiên chuẩn 4-5 ký tự)
    tni_list = re.findall(r"TNI\d{4}|TNI[A-Z0-9]{4,5}", text_clean, re.IGNORECASE)
    if not tni_list:
        return

    # CHỈ TRA CỨU DUY NHẤT 1 MÃ TNI ĐẦU TIÊN THEO YÊU CẦU
    tni = tni_list[0].upper()

    # Ghi log tìm kiếm mã TNI trong background
    log_search_bg(first_name or str(user_id), user_id, tni)
    result = lookup_tni(tni)
    for chunk in split_messages(result):
        tg_send(chat_id, chunk)


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
            raw    = self.rfile.read(length)
            data   = json.loads(raw)

            # 1. Trả về 200 OK NGAY LẬP TỨC cho Telegram (< 10ms) để Telegram KHÔNG BAO GIỜ retry kết nối
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            try:
                self.wfile.flush()
            except Exception:
                pass

            # 2. Lọc trùng update_id (nếu Telegram có trôi request)
            up_id = data.get("update_id")
            if up_id:
                if up_id in _processed_updates:
                    logger.info(f"Skipping duplicate update_id {up_id}")
                    return
                _processed_updates.add(up_id)
                if len(_processed_updates) > 1000:
                    _processed_updates.clear()

            action = data.get("action")
            if action == "submit_plan":
                chat_id = data.get("chat_id")
                text = data.get("text", "")
                if chat_id and text:
                    tg_send(int(chat_id), text)
                return

            # 3. Chạy handle(data) để xử lý logic
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

        except Exception as ex:
            logger.error(f"Webhook POST parse error: {ex}")

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
                result = {
                    "delete": r1,
                    "set": r2, 
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

        tok_ok  = "SET" if TOKEN else "MISSING"
        gas_ok  = "SET" if DAILY_APPS_SCRIPT_URL else "MISSING"
        log_val = APPS_SCRIPT_URL if APPS_SCRIPT_URL else "MISSING"
        log_ok  = f"SET (...{log_val[-15:]})" if APPS_SCRIPT_URL else "MISSING"
        msg = f"TNI Search Bot {BOT_VERSION} | TOKEN:{tok_ok} | DAILY_GAS:{gas_ok} | APPS_SCRIPT_URL:{log_ok}"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(msg.encode())

    def log_message(self, *a): pass
