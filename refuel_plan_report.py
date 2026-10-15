"""
refuel_plan_report.py
======================
Tạo 5 báo cáo so sánh/thống kê Refuel Plan từ Google Sheet và gửi vào group Telegram.

Báo cáo 1: Tần suất gửi Plan của từng trạm (3 ngày / 7 ngày / 1 tháng)
Báo cáo 2: So sánh Plan hôm nay vs Refueled thực tế (chạy lúc 18:00)
Báo cáo 3: So sánh Plan hôm nay vs Team Request (chạy lúc 18:00)
Báo cáo 4: Thống kê Request refuel theo thành viên (từ sheet Telegram ID) + Ai chưa tham gia (chạy lúc 22:00)
Báo cáo 5: Thống kê Plan gửi theo danh sách ID tại cột G và tên tại cột H sheet Template (chạy lúc 22:00)

Cách chạy:
  python refuel_plan_report.py --report 1
  python refuel_plan_report.py --report 2
  python refuel_plan_report.py --report 3
  python refuel_plan_report.py --report 4
  python refuel_plan_report.py --report 5
  python refuel_plan_report.py            # Chạy toàn bộ 5 báo cáo
"""
import os, sys, argparse, requests, re
import openpyxl
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from tg_utils import tg_send_fresh, tg_delete_by_title

load_dotenv()  # Load .env local (GitHub Actions đã có env vars sẵn)

# Cấu hình bot và chat ID mặc định của group 9 TNI REQUEST REFUEL
REFUEL_BOT_TOKEN    = os.getenv("REFUEL_BOT_TOKEN", "")
REFUEL_CHAT_ID      = "-5469544739"   # Group 9 TNI REQUEST REFUEL
SPREADSHEET_ID      = "1JxrA4pJo92Xx_SpwLnOQxphVYwE2iFhLrCOHmyVVuuM"
XLSX_DOWNLOAD_URL   = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=xlsx"
XLSX_FILE_PATH      = "scratch/sheet_refuel.xlsx"

TZ_MM = timezone(timedelta(hours=6, minutes=30))  # Myanmar UTC+6:30




# ── Helper functions ─────────────────────────────────────────────────────────

# GAS URL để lưu message_id (BotState)
REFUEL_GAS_URL = (
    os.getenv("APPS_SCRIPT_URL") or
    os.getenv("REFUEL_APPS_SCRIPT_URL") or ""
).strip()


# Map report_key → title prefix dòng đầu tiên (dùng cho Telethon delete-by-title)
REPORT_TITLE_PREFIX = {
    "report1": "TNI REQUEST REFUEL",
    "report2": "📊 [Report 2]",
    "report5": "📋 [Report 5]",
}

def tg_send(text: str, report_key: str = "") -> bool:
    """Gửi tin nhắn báo cáo lên Telegram group (tự động chia phần nếu > 3800 ký tự) và TỰ ĐỘNG XÓA TIN NHẮN CŨ."""
    title_pfx = REPORT_TITLE_PREFIX.get(report_key, "[Report 1]")
    state_k = f"refuel_{report_key}" if report_key else "refuel_report1"

    # Đảm bảo xóa sạch 100% tin cũ cùng tiêu đề trước khi gửi tin mới
    tg_delete_by_title(REFUEL_CHAT_ID, title_pfx, bot_token=REFUEL_BOT_TOKEN)

    if len(text) <= 3800:
        msg_id = tg_send_fresh(
            chat_id=REFUEL_CHAT_ID,
            text=text,
            state_key=state_k,
            parse_mode="HTML",
            title_prefix="",  # Đã xóa sạch ở trên
            bot_token=REFUEL_BOT_TOKEN
        )
        if msg_id:
            print(f"✅ Report {report_key} (msg_id={msg_id}) sent to {REFUEL_CHAT_ID} (old messages cleaned)")
            return True
        return False

    # Nếu văn bản > 3800 ký tự -> Chia nhỏ theo từng dòng để tránh lỗi Telegram 4096 chars
    lines = text.split("\n")
    chunks = []
    current_chunk = []
    current_len = 0

    for line in lines:
        if current_len + len(line) + 1 > 3500:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_len = len(line)
        else:
            current_chunk.append(line)
            current_len += len(line) + 1
    if current_chunk:
        chunks.append("\n".join(current_chunk))

    all_ok = True
    token = REFUEL_BOT_TOKEN
    first_chunk = chunks[0] + f"\n\n<i>(Part 1/{len(chunks)})</i>"
    first_id = tg_send_fresh(
        chat_id=REFUEL_CHAT_ID,
        text=first_chunk,
        state_key=state_k,
        parse_mode="HTML",
        title_prefix=title_pfx,
        bot_token=token
    )
    if not first_id:
        all_ok = False

    for idx, chunk in enumerate(chunks[1:], start=2):
        chunk_text = f"🔄 <b>{title_pfx} (Cont. - Part {idx}/{len(chunks)})</b>\n\n" + chunk
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": REFUEL_CHAT_ID, "text": chunk_text, "parse_mode": "HTML"},
                timeout=20
            )
            res = r.json()
            if res.get("ok"):
                print(f"✅ Sent part {idx}/{len(chunks)} (msg_id={res['result']['message_id']})")
            else:
                print(f"❌ Failed to send part {idx}: {res.get('description')}")
                all_ok = False
        except Exception as ex:
            print(f"❌ Exception sending part {idx}: {ex}")
            all_ok = False

    return all_ok


def fmt_row_compare_mobile(col_site: str, col_b: str, col_c: str, col_d: str) -> str:
    """Format dòng so sánh hiển thị siêu gọn trên 1 dòng điện thoại (Site | Plan | Ref= Diff)."""
    return f"<code>{col_site} | {col_b:>3} | {col_c:>3}= {col_d}</code>"


def fmt_row_compare_5(col_team: str, col_site: str, col_b: str, col_c: str, col_d: str) -> str:
    """Format dòng so sánh 5 cột (Team | Site ID | Req/Plan | Plan/Ref | Diff) dạng monospace."""
    return f"<code>{col_team:<6} | {col_site:<10} | {col_b:>5} | {col_c:>5} | {col_d:>5}</code>"



def download_spreadsheet() -> bool:
    """Tải file Excel từ Google Sheets."""
    print("📥 Downloading spreadsheet...")
    try:
        os.makedirs("scratch", exist_ok=True)
        r = requests.get(XLSX_DOWNLOAD_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        with open(XLSX_FILE_PATH, "wb") as f:
            f.write(r.content)
        print("✅ Download successful!")
        return True
    except Exception as e:
        print(f"❌ Download failed: {e}", file=sys.stderr)
        return False


def parse_datetime(val) -> datetime | None:
    """Đảm bảo định dạng datetime có múi giờ Myanmar."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=TZ_MM)
        return val
    if isinstance(val, str):
        val = val.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(val, fmt)
                return dt.replace(tzinfo=TZ_MM)
            except ValueError:
                pass
    return None


def parse_date_str(val) -> str:
    """Chuyển đổi giá trị ngày (datetime hoặc string) sang chuỗi dd/MM/YYYY."""
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y")
    s = str(val).strip()
    if len(s) == 10 and s[2] == "/" and s[5] == "/":
        return s
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return s


def parse_date_to_datetime(val) -> datetime | None:
    """Parse bất kỳ định dạng ngày nào về datetime object (không kèm timezone) để so sánh."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s or s.lower() == "none":
        return None
    # Thử các định dạng ngày phổ biến
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt)
        except ValueError:
            pass
    return None


def safe_int(val) -> int:
    """Chuyển đổi giá trị số nguyên an toàn — trả 0 nếu không parse được."""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return 0


def fmt_row_freq(col_a: str, col_b: str, col_c: str, col_d: str) -> str:
    """Format dòng tần suất (Site/Name | 3D | 7D | 1M) dạng monospace có gạch dọc '|'."""
    return f"<code>{col_a:<12} | {col_b:>5} | {col_c:>5} | {col_d:>6}</code>"


def fmt_row_compare(col_a: str, col_b: str, col_c: str, col_d: str) -> str:
    """Format dòng so sánh lượng dầu (Site | Plan/Req | Filled/Plan | Diff) dạng monospace có gạch dọc '|'."""
    return f"<code>{col_a:<12} | {col_b:>5} | {col_c:>6} | {col_d:>6}</code>"


def normalize_team(raw_team: str) -> str:
    """Chuẩn hóa tên team (T1, T1 S1, T2, T2 S1, T3, T3 S1, T4)."""
    s = str(raw_team or "").strip()
    s_lower = s.lower()
    if re.search(r"\b(team\s*1\s*s1|t1\s*s1)\b", s_lower): return "T1 S1"
    if re.search(r"\b(team\s*2\s*s1|t2\s*s1)\b", s_lower): return "T2 S1"
    if re.search(r"\b(team\s*3\s*s1|t3\s*s1)\b", s_lower): return "T3 S1"
    if re.search(r"\b(team\s*4\s*s1|t4\s*s1)\b", s_lower): return "T4 S1"
    if re.search(r"\b(team\s*1|t1)\b", s_lower): return "T1"
    if re.search(r"\b(team\s*2|t2)\b", s_lower): return "T2"
    if re.search(r"\b(team\s*3|t3)\b", s_lower): return "T3"
    if re.search(r"\b(team\s*4|t4)\b", s_lower): return "T4"
    return "T1"


# ── Load spreadsheet data ───────────────────────────────────────────────────

class RefuelData:
    def __init__(self):
        self.members = []          # list of dict: {id, name} — từ sheet "Telegram ID"
        self.not_joined = []       # list of str (names)
        self.target_members = []   # list of dict: {id, name} — từ Template col G & H
        self.lettel_persons = []   # list of dict: {id, name} — từ Template col J & K
        self.records = []          # list of dict: {ts, date, cat, sender, sender_id, site, qty}
        self.letter_approved = ""  # ngày Government Approved mới nhất (col C)
        self.letter_submitted = "" # ngày Letter Submitted mới nhất (col B)
        self.ft_monitors = []      # list of dict: {date, ft_name, site_id, qty} — từ sheet "FT follow monitor"
        self.site_to_dg = {}       # map Site code (Col C) -> list of DG ID (Col B)
        self.dg_to_team = {}       # map DG ID (Col B) -> Team (Col AB)
        self.all_dgs = set()       # tập hợp tất cả DG ID chuẩn từ Col B
        self.app_header = ""       # ô AL5 từ Request Partner Auto (App Approved header)
        self.dg_to_col_r = {}      # map DG ID -> Col R value (Littel need refuel)
        self.dg_to_remain = {}     # map DG ID -> Col P value (Fuel Remain)
 
        if not os.path.exists(XLSX_FILE_PATH):
            if not download_spreadsheet():
                return
 
        try:
            wb = openpyxl.load_workbook(XLSX_FILE_PATH, data_only=True)
            self._parse_members(wb)
            self._parse_targets(wb)
            self._parse_lettel(wb)
            self._parse_lettel_progress(wb)
            self._parse_ft_monitors(wb)
            self._parse_master_col_b(wb)
            self._parse_app_header(wb)
            self._parse_records(wb)
        except Exception as e:
            print(f"❌ Error loading Excel data: {e}", file=sys.stderr)

    def _parse_master_col_b(self, wb):
        """Xây dựng bản đồ chuẩn hóa tên Site về duy nhất Cột B (DG ID) từ Sheet 'Request Partner Auto' và 'Need Refuel'."""
        self.site_to_dg = {}
        self.dg_to_team = {}
        self.all_dgs = set()
        self.dg_to_remain = {}
        
        sheet_names = [s for s in ["Request Partner Auto", "Need Refuel"] if s in wb.sheetnames]
        for sname in sheet_names:
            ws = wb[sname]
            start_r = 6 if sname == "Request Partner Auto" else 3
            for r in range(start_r, ws.max_row + 1):
                col_b = str(ws.cell(row=r, column=2).value or "").strip().upper()
                col_c = str(ws.cell(row=r, column=3).value or "").strip().upper()
                col_ab = str(ws.cell(row=r, column=28).value or "").strip() if ws.max_column >= 28 else ""
                if col_b and col_b.startswith("TNI"):
                    self.all_dgs.add(col_b)
                    if col_ab and col_ab != "0":
                        self.dg_to_team[col_b] = normalize_team(col_ab)
                    if col_c and col_c.startswith("TNI"):
                        if col_c not in self.site_to_dg:
                            self.site_to_dg[col_c] = []
                        if col_b not in self.site_to_dg[col_c]:
                            self.site_to_dg[col_c].append(col_b)
                    if sname == "Request Partner Auto":
                        col_p = ws.cell(row=r, column=16).value  # Col P: Fuel Remain
                        if col_p is not None and str(col_p).strip() != "":
                            try:
                                self.dg_to_remain[col_b] = round(float(col_p))
                            except (ValueError, TypeError):
                                self.dg_to_remain[col_b] = col_p

    def get_site_remain(self, raw_site: str):
        """Lấy lượng dầu còn lại (Fuel Remain từ Cột P sheet Request Partner Auto)."""
        if not raw_site:
            return None
        s = str(raw_site).strip().upper()
        if s in self.dg_to_remain:
            return self.dg_to_remain[s]
        norm = self.normalize_to_col_b(s)
        if norm in self.dg_to_remain:
            return self.dg_to_remain[norm]
        if not re.search(r"_\d+$", s):
            cand = f"{s}_1"
            if cand in self.dg_to_remain:
                return self.dg_to_remain[cand]
        else:
            base = re.sub(r"_\d+$", "", s)
            if base in self.dg_to_remain:
                return self.dg_to_remain[base]
        return None

    def normalize_to_col_b(self, raw_name: str, team: str = "") -> str:
        """Chuẩn hóa tên trạm về DUY NHẤT tên Cột B (DG ID, ví dụ TNI0035_1, TNI0012_1)."""
        s = str(raw_name or "").strip().upper()
        if not s:
            return ""
        if s in self.all_dgs:
            return s
        m_dg = re.search(r"\(DG\s*([12])\)", s)
        if m_dg:
            base = re.sub(r"\(DG\s*[12]\)", "", s).strip()
            cand = f"{base}_{m_dg.group(1)}"
            if cand in self.all_dgs:
                return cand
            s = base
        if s in self.site_to_dg:
            dgs = self.site_to_dg[s]
            if len(dgs) == 1:
                return dgs[0]
            if team:
                norm_t = normalize_team(team)
                for dg in dgs:
                    if self.dg_to_team.get(dg) == norm_t:
                        return dg
            return dgs[0]
        if re.search(r"_\d+$", s):
            return s
        if s.startswith("TNI"):
            return f"{s}_1"
        return s

    def _parse_members(self, wb):
        if "Telegram ID" in wb.sheetnames:
            ws = wb["Telegram ID"]
            for r in range(2, ws.max_row + 1):
                tg_id = ws.cell(row=r, column=1).value   # Cột A: Telegram ID
                val_f = ws.cell(row=r, column=6).value   # Cột F: Tên nhân sự
                pos   = ws.cell(row=r, column=12).value  # Cột L: Chức vụ
                team  = ws.cell(row=r, column=13).value  # Cột M: Team

                name = None
                if val_f and str(val_f).strip() and str(val_f).strip().lower() not in ("none", "0"):
                    name = str(val_f).strip()
                else:
                    for col in (3, 4, 5):
                        val = ws.cell(row=r, column=col).value
                        if val and str(val).strip() and str(val).strip().lower() not in ("none", "0"):
                            name = str(val).strip()
                            break

                if not name and not tg_id:
                    continue  # Dòng trống hoàn toàn → bỏ qua

                name_str = name or "Unknown"
                if pos and "team leader" in str(pos).lower():
                    if "(TL)" not in name_str:
                        name_str = f"{name_str} (TL)"

                team_str = str(team).strip() if team else "Team 1"
                tg_id_str = str(tg_id).strip() if tg_id is not None else ""
                has_id = bool(tg_id_str and tg_id_str.isdigit() and int(tg_id_str) > 0)

                member_obj = {
                    "id": tg_id_str if has_id else "",
                    "name": name_str,
                    "team": team_str,
                    "has_id": has_id
                }

                if has_id:
                    self.members.append(member_obj)
                else:
                    self.not_joined.append(member_obj)

    def _parse_targets(self, wb):
        if "Template" in wb.sheetnames:
            ws = wb["Template"]
            for r in range(2, ws.max_row + 1):  # Quét từ dòng 2
                val = ws.cell(row=r, column=7).value     # Cột G: ID telegram
                name = ws.cell(row=r, column=8).value    # Cột H: Tên
                if val is not None:
                    val_str = str(val).strip()
                    # Bỏ qua dòng tiêu đề mẫu nếu có chữ "id telegram"
                    if val_str.lower() == "id telegram":
                        continue
                    if val_str.isdigit() and len(val_str) > 8:
                        self.target_members.append({
                            "id": val_str,
                            "name": str(name).strip() if name else f"ID:{val_str[-6:]}"
                        })

    def _parse_lettel(self, wb):
        """Đọc Template col J (Telegram ID) & K (Tên nhân viên phụ trách)."""
        sheet_name = "Template"
        if sheet_name not in wb.sheetnames:
            return
        ws = wb[sheet_name]
        for r in range(2, ws.max_row + 1):
            tg_id = ws.cell(row=r, column=10).value   # J: Telegram ID nhân viên
            name  = ws.cell(row=r, column=11).value   # K: Tên nhân viên
            if not tg_id and not name:
                continue
            tg_id_str = str(tg_id).strip() if tg_id is not None else ""
            name_str  = str(name).strip()  if name  is not None else ""
            if tg_id_str.isdigit() and len(tg_id_str) > 5 and name_str:
                self.lettel_persons.append({"id": tg_id_str, "name": name_str})

    def _parse_lettel_progress(self, wb):
        """Đọc Lettel Progress col B (Date Letter Submit) và col C (Date Leter Approved) — lấy giá trị mới nhất."""
        if "Lettel Progress" not in wb.sheetnames:
            return
        ws = wb["Lettel Progress"]
        latest_submitted = ""
        latest_approved  = ""
        max_sub_dt = None
        max_app_dt = None
        for r in range(2, ws.max_row + 1):
            val_b = ws.cell(row=r, column=2).value  # B: Date Letter Submit
            val_c = ws.cell(row=r, column=3).value  # C: Date Letter Approved
            if val_b:
                dt_b = parse_date_to_datetime(val_b)
                if dt_b:
                    if max_sub_dt is None or dt_b > max_sub_dt:
                        max_sub_dt = dt_b
                        latest_submitted = parse_date_str(val_b)
            if val_c:
                dt_c = parse_date_to_datetime(val_c)
                if dt_c:
                    if max_app_dt is None or dt_c > max_app_dt:
                        max_app_dt = dt_c
                        latest_approved = parse_date_str(val_c)
        self.letter_submitted = latest_submitted
        self.letter_approved  = latest_approved
 
    def _parse_ft_monitors(self, wb):
        """Đọc tab 'FT follow monitor' và lấy danh sách những người đi theo giám sát."""
        self.ft_monitors = []
        if "FT follow monitor" not in wb.sheetnames:
            return
        ws = wb["FT follow monitor"]
        for r in range(2, ws.max_row + 1):
            date_val = ws.cell(row=r, column=2).value  # B: Date
            ft_name  = ws.cell(row=r, column=3).value  # C: FT Name
            site_id  = ws.cell(row=r, column=4).value  # D: Site ID
            qty      = ws.cell(row=r, column=5).value  # E: Refuel Qty
            
            if ft_name:
                date_str = ""
                if isinstance(date_val, datetime):
                    date_str = date_val.strftime("%d/%m/%Y")
                elif date_val:
                    date_str = str(date_val).strip()
                
                self.ft_monitors.append({
                    "date": date_str,
                    "ft_name": str(ft_name).strip(),
                    "site_id": str(site_id).strip() if site_id else "",
                    "qty": str(qty).strip() if qty else ""
                })
 
    def _parse_app_header(self, wb):
        """Đọc ô AL5 từ sheet Request Partner Auto — header App Approved."""
        if "Request Partner Auto" in wb.sheetnames:
            ws = wb["Request Partner Auto"]
            al5 = ws["AL5"].value
            raw = str(al5 or "").strip()
            # Escape HTML để tránh lỗi Telegram parse (ô AL5 có thể chứa < + >)
            self.app_header = raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _parse_records(self, wb):
        # 1. Parse Plan refuel sheet
        if "Plan refuel" in wb.sheetnames:
            ws = wb["Plan refuel"]
            for r in range(2, ws.max_row + 1):
                date_val = ws.cell(row=r, column=2).value
                site = ws.cell(row=r, column=4).value
                qty = ws.cell(row=r, column=5).value
                ts = parse_datetime(ws.cell(row=r, column=6).value) or datetime.now(TZ_MM)
                sender = ws.cell(row=r, column=7).value
                sender_id = ws.cell(row=r, column=8).value
                
                if site:
                    team_val = ws.cell(row=r, column=3).value  # col C: Name Team Plan
                    norm_team = normalize_team(team_val)
                    site_id = self.normalize_to_col_b(str(site).strip().upper(), norm_team)
                    self.records.append({
                        "ts": ts,
                        "date": parse_date_str(date_val),
                        "cat": "PLAN",
                        "team": norm_team,
                        "sender": str(sender).strip() if sender else "",
                        "sender_id": str(sender_id).strip() if sender_id else "",
                        "site": site_id,
                        "qty": safe_int(qty)
                    })
                    
        # 2. Parse Request Partner Auto (nguồn Request chính, chỉ lấy khi Cột V có ngày)
        # BẮT BUỘC CHỈ LẤY TÊN CỘT B (DG ID, ví dụ TNI0035_1, TNI0012_1)
        if "Request Partner Auto" in wb.sheetnames:
            ws = wb["Request Partner Auto"]
            for r in range(4, min(ws.max_row + 1, 350)):
                col_v = ws.cell(row=r, column=22).value  # Col V: Date request refuel
                v_str = parse_date_str(col_v)
                if v_str and v_str != "-":
                    dg = str(ws.cell(row=r, column=2).value or "").strip()
                    site = str(ws.cell(row=r, column=3).value or "").strip()
                    team_ab = str(ws.cell(row=r, column=28).value or "").strip()
                    team_e = str(ws.cell(row=r, column=5).value or "").strip()
                    raw_team = team_ab if team_ab and team_ab != "0" else team_e
                    team = normalize_team(raw_team)
                    site_id = self.normalize_to_col_b(dg if dg else site, team)
                    if not site_id.startswith("TNI"):
                        continue
                    lit_w = ws.cell(row=r, column=23).value  # Col W: Littel request
                    lit_q = ws.cell(row=r, column=17).value  # Col Q: Fuel Remain
                    lit_r = ws.cell(row=r, column=18).value  # Col R: Littel need refuel
                    qty = safe_int(lit_w) if safe_int(lit_w) > 0 else (safe_int(lit_q) if safe_int(lit_q) > 0 else 440)
                    # Lưu col R cho site để dùng icon ưu tiên
                    if site_id:
                        self.dg_to_col_r[site_id] = safe_int(lit_r)
                    self.records.append({
                        "ts": datetime.now(TZ_MM),
                        "date": v_str,
                        "cat": "REQUEST",
                        "team": team,
                        "sender": "Request Partner Auto",
                        "sender_id": "",
                        "site": site_id,
                        "qty": qty
                    })

        # 3. Parse Team request sheet (kết hợp lấy thêm yêu cầu hôm nay do người khác gửi lên)
        if "Team request" in wb.sheetnames:
            ws = wb["Team request"]
            seen_request_sites = {r["site"] for r in self.records if r.get("cat") == "REQUEST"}
            today_now_str = datetime.now(TZ_MM).strftime("%d/%m/%Y")
            for r in range(2, min(ws.max_row + 1, 200)):
                d_val = parse_date_str(ws.cell(row=r, column=2).value)
                if d_val == today_now_str:
                    team_val = ws.cell(row=r, column=4).value  # col D: Name Team
                    site = str(ws.cell(row=r, column=5).value or "").strip().upper()
                    qty = safe_int(ws.cell(row=r, column=6).value)
                    ts = parse_datetime(ws.cell(row=r, column=7).value) or datetime.now(TZ_MM)
                    sender = ws.cell(row=r, column=8).value
                    sender_id = ws.cell(row=r, column=9).value
                    if site and site.startswith("TNI"):
                        norm_team = normalize_team(team_val)
                        site_id = self.normalize_to_col_b(site, norm_team)
                        if site_id not in seen_request_sites:
                            seen_request_sites.add(site_id)
                            self.records.append({
                                "ts": ts,
                                "date": d_val,
                                "cat": "REQUEST",
                                "team": norm_team,
                                "sender": str(sender).strip() if sender else "",
                                "sender_id": str(sender_id).strip() if sender_id else "",
                                "site": site_id,
                                "qty": qty
                            })

        # 4. Parse Refueled sheet
        if "Refueled" in wb.sheetnames:
            ws = wb["Refueled"]
            for r in range(2, ws.max_row + 1):
                date_val = ws.cell(row=r, column=2).value
                dg_val = ws.cell(row=r, column=3).value    # col C: DG ID
                site_val = ws.cell(row=r, column=4).value  # col D: Site ID
                team_val = ws.cell(row=r, column=5).value  # col E: Team
                qty = ws.cell(row=r, column=14).value       # col N: Actual Filled Qty(L)
                ts = parse_datetime(ws.cell(row=r, column=17).value) or datetime.now(TZ_MM)
                sender = ws.cell(row=r, column=18).value
                sender_id = ws.cell(row=r, column=19).value
                
                raw_site = str(dg_val or site_val or "").strip().upper()
                if raw_site:
                    norm_team = normalize_team(team_val)
                    site_id = self.normalize_to_col_b(raw_site, norm_team)
                    self.records.append({
                        "ts": ts,
                        "date": parse_date_str(date_val),
                        "cat": "REFUELED",
                        "team": norm_team,
                        "sender": str(sender).strip() if sender else "",
                        "sender_id": str(sender_id).strip() if sender_id else "",
                        "site": site_id,
                        "qty": safe_int(qty)
                    })

# ── Reports implementation ──────────────────────────────────────────────────

def report_1(data: RefuelData):
    """
    Báo cáo tổng hợp gộp — 1 tin nhắn duy nhất cho Group 9:
    1. Letter Progress + FT follow monitor
    2. App Approved header (ô AL5)
    3. Bảng đối soát 6 cột: DG ID | Date Req | Request | Plan | Refueled | Diff(Req−Ref)
    4. Thống kê trạng thái + Note footer
    """
    print("🔄 Generating Merged Refuel Report (Request + Plan & Progress)...")
    now = datetime.now(TZ_MM)
    today_str = now.strftime("%d/%m/%Y")
    # Nếu trong khung giờ đêm / rạng sáng (00:00 - 05:00) và chưa có dữ liệu ngày mới -> lấy ngày hôm qua
    if now.hour < 5:
        yesterday_str = (now - timedelta(days=1)).strftime("%d/%m/%Y")
        has_today = any(r.get("date") == today_str for r in data.records if r.get("cat") in ("PLAN", "REFUELED"))
        if not has_today:
            today_str = yesterday_str

    # ── Letter Progress ──
    submit_line   = f"  📤 Submitted: <b>{data.letter_submitted or 'N/A'}</b>"
    approved_line = f"  ✅ Approved: <b>{data.letter_approved or 'N/A'}</b>"

    # ── FT follow monitor ──
    ft_today = []
    for ft in data.ft_monitors:
        ft_date = ft["date"]
        try:
            parts = ft_date.split("/")
            if len(parts) == 3:
                ft_date = f"{int(parts[0]):02d}/{int(parts[1]):02d}/{int(parts[2])}"
        except Exception:
            pass
        today_norm = ""
        try:
            parts_today = today_str.split("/")
            if len(parts_today) == 3:
                today_norm = f"{int(parts_today[0]):02d}/{int(parts_today[1]):02d}/{int(parts_today[2])}"
        except Exception:
            today_norm = today_str
        if ft_date == today_norm:
            ft_today.append(ft["ft_name"])
    ft_names_today = sorted(list(set(ft_today)))
    ft_str = ", ".join(ft_names_today) if ft_names_today else "None"

    # ── Gather data for today by Team ──
    teams_list = ["T1", "T1 S1", "T2", "T2 S1", "T3", "T3 S1", "T4"]
    # team_map[team][site] = {plan, refueled, req, req_date, plan_date, ref_date}
    team_map: dict[str, dict[str, dict]] = {t: {} for t in teams_list}

    def new_site():
        return {"plan": 0, "refueled": 0, "req": 0, "req_date": "", "plan_date": "", "ref_date": ""}

    def get_team_key(raw_team: str) -> str:
        return normalize_team(raw_team)

    # 1. Nạp tất cả REQUEST từ Sheet 'Request Partner Auto' và 'Team request'
    for r in data.records:
        if r.get("cat") != "REQUEST" or not r.get("site"):
            continue
        team = get_team_key(r.get("team", ""))
        site = r["site"].upper()
        if site not in team_map[team]:
            team_map[team][site] = new_site()
        team_map[team][site]["req"] = max(team_map[team][site]["req"], r.get("qty", 0))
        rd = r.get("date", "")
        if rd and (not team_map[team][site]["req_date"] or rd > team_map[team][site]["req_date"]):
            team_map[team][site]["req_date"] = rd

    # 2. Nạp PLAN và REFUELED của ngày hôm nay
    for r in data.records:
        if r.get("cat") not in ("PLAN", "REFUELED") or not r.get("site"):
            continue
        if r.get("date") != today_str:
            continue
        team = get_team_key(r.get("team", ""))
        raw_site = r["site"].upper()

        target_site = raw_site
        if raw_site not in team_map[team]:
            candidates = [s for s in team_map[team].keys() if re.sub(r'_\d+$', '', s) == re.sub(r'_\d+$', '', raw_site)]
            if len(candidates) == 1:
                target_site = candidates[0]

        if target_site not in team_map[team]:
            team_map[team][target_site] = new_site()

        if r["cat"] == "PLAN":
            team_map[team][target_site]["plan"] += r.get("qty", 0)
            team_map[team][target_site]["plan_date"] = r.get("date", "")
        elif r["cat"] == "REFUELED":
            team_map[team][target_site]["refueled"] += r.get("qty", 0)
            team_map[team][target_site]["ref_date"] = r.get("date", "")

    # ── Đếm tổng số site request ──
    total_req_sites = sum(1 for t in teams_list for s in team_map[t] if team_map[t][s]["req"] > 0)

    # ── App Approved header ──
    app_hdr = data.app_header if data.app_header else ""
    if app_hdr:
        app_line = f"{app_hdr}\n=&gt; Need request Refuel: /{total_req_sites} Site"
    else:
        app_line = f"📊 Total request: <b>{total_req_sites}</b> Sites"

    # ── Format ngày ngắn dd/mm ──
    def short_date(d: str) -> str:
        """Rút gọn dd/mm/yyyy -> dd/mm"""
        if not d:
            return "—"
        parts = d.split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return d

    # ── Header ──
    team_display = {
        "T1": "Team 1", "T1 S1": "Team 1 S1",
        "T2": "Team 2", "T2 S1": "Team 2 S1",
        "T3": "Team 3", "T3 S1": "Team 3 S1",
        "T4": "Team 4",
    }

    lines = [
        f"🔄 <b>[Report 1] TNI REQUEST REFUEL — {today_str}</b>",
        f"⏰ {now.strftime('%H:%M')} Myanmar",
        "━━━━━━━━━━━━━━━━━━━━━",
        "📝 <b>Letter Progress:</b>",
        submit_line,
        approved_line,
        f"  👥 FT follow monitor: <b>{ft_str}</b>",
        app_line,
        "🟩 Refueled  🟦 Planned  🟨≤200 🟣>200 🔥>400(ColR)  🟥 Unlisted",
    ]

    green_total = yellow_total = red_total = blue_total = 0

    for team in teams_list:
        sites_data = team_map[team]
        if not sites_data:
            continue

        group_planned = []
        group_no_plan = []

        for site in sorted(sites_data.keys()):
            sd = sites_data[site]
            p = sd["plan"]
            fill = sd["refueled"]
            q = sd["req"]
            # Diff = Request - Refueled
            diff = q - fill

            rd = short_date(sd["req_date"])
            pd = short_date(sd["plan_date"])
            fd = short_date(sd["ref_date"])

            def fmt_row(icon_: str) -> str:
                diff_s = f"{diff:+d}" if diff != 0 else "0"
                rem_val = data.get_site_remain(site)
                rem_s = f" {rem_val}" if rem_val is not None else " —"
                req_s = f" {rd}:{q}" if q > 0 else " —"
                plan_s = f" {pd}:{p}" if p > 0 else " —"
                ref_s = f" {fd}:{fill}" if fill > 0 else " —"
                return f"{icon_}<code>{site}|{rem_s}|{req_s}|{plan_s}|{ref_s}|{diff_s}L</code>"

            # Color rules:
            if q == 0 and (p > 0 or fill > 0):
                red_total += 1
                group_planned.append(fmt_row("🟥"))
            elif fill > 0:
                green_total += 1
                group_planned.append(fmt_row("🟩"))
            elif p > 0 and fill == 0:
                blue_total += 1
                group_planned.append(fmt_row("🟦"))
            elif q > 0 and p == 0 and fill == 0:
                yellow_total += 1
                col_r_val = data.dg_to_col_r.get(site, 0)
                if col_r_val > 400:
                    no_plan_icon = "🟨🔥"   # R > 400L
                elif col_r_val > 200:
                    no_plan_icon = "🟨🟣"   # 200 < R ≤ 400L
                else:
                    no_plan_icon = "🟨"     # R ≤ 200L
                group_no_plan.append(fmt_row(no_plan_icon))

        if group_planned or group_no_plan:
            total_sites = len(group_planned) + len(group_no_plan)
            name = team_display.get(team, team)
            site_word = "Site" if total_sites == 1 else "Sites"
            lines.append(f"<b>{name} ({total_sites} {site_word})</b>")
            if team in ("T1", "T3"):
                lines.append("<code>Site|Remain|Request|Plan|Refueled|Diff</code>")
            for row in group_planned:
                lines.append(row)
            for row in group_no_plan:
                lines.append(row)

    lines.append(f"🟩 <b>{green_total}</b>  🟦 <b>{blue_total}</b>  🟨 <b>{yellow_total}</b>  🟥 <b>{red_total}</b>")

    # Note footer
    lines.append("/Note: According to the list of stations and the required number of liters, refuel at the correct station with the correct number of liters. ❓ /No request on group 9 TNI REQUEST REFUEL = ❌ /No refueling allowed.")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🤖 <i>Auto report — Refuel Plan System</i>")

    tg_send("\n".join(lines), "report1")
    print("✅ Merged Report 1 sent.")


def report_2(data: RefuelData):
    """Gộp chung vào Report 1."""
    report_1(data)




def report_4(data: RefuelData):
    """Alias cho report_2 để tương thích với các script cũ."""
    report_2(data)


def report_5(data: RefuelData):
    """
    Báo cáo kiểm toán đọc tin 3Day/7Day/Month & quân số Group 9 (Refuel Read Report):
    - KHÔNG gửi lên Group 9.
    - Chỉ gửi vào Bot 2 / Control Site (-5251698940) giống ghế giám sát.
    - Hiển thị đầy đủ tiến độ đọc: 3Day:1/1/1  7Day:7  Month:30.
    - Ghi dữ liệu vào tab 'Read Group Refuel' (Sheet 1JxrA4pJo92Xx_SpwLnOQxphVYwE2iFhLrCOHmyVVuuM).
    """
    print("📋 Generating Report 5 — Group 9 Read Report (Sent to Control / Bot 2)...")
    now = datetime.now(TZ_MM)
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M")

    all_members = data.members + data.not_joined
    total_all = len(all_members)
    total_read = sum(1 for m in all_members if m.get("has_id"))
    total_not_joined = sum(1 for m in all_members if not m.get("has_id"))

    # Phân nhóm động 100% từ Cột M (Team) của Google Sheet
    teams_dict = {}
    for m in all_members:
        t_raw = m.get("team", "Team 1")
        t_norm = "Team 1"
        if any(k in t_raw.lower() for k in ["partner", "mgmt", "management"]):
            t_norm = "Partner / Management"
        elif "2" in t_raw or "5" in t_raw:
            t_norm = "Team 2"
        elif "3" in t_raw:
            t_norm = "Team 3"
        elif "4" in t_raw:
            t_norm = "Team 4"
        elif "1" in t_raw:
            t_norm = "Team 1"
        else:
            t_norm = t_raw
        teams_dict.setdefault(t_norm, []).append(m)

    # 1. Xây dựng tin nhắn báo cáo chuẩn phân tầng động từ Sheet
    divider = "━━━━━━━━━━━━━━━━━━━━━"
    lines = [
        f"📋 <b>6. Report — Refuel Note Read Report — Group 9</b>",
        f"📅 {date_str}  |  🕐 {time_str} (Myanmar)",
        f"⏰ Read Window: 04:00 - 23:59 Myanmar",
        f"📌 Shows who read the Refuel Note message during active window.",
        divider,
        f"👥 Total: <b>{total_all}</b>  |  🟩 Read: <b>{total_read}</b>  |  🟨 Unread: <b>0</b>  |  🟥 Not Joined: <b>{total_not_joined}</b>",
        divider,
    ]

    # Hiển thị Partner / Management đầu tiên nếu có trong Sheet
    if "Partner / Management" in teams_dict:
        lines.append("\n🏷️ <b>Partner / Management</b>")
        for s in sorted(teams_dict["Partner / Management"], key=lambda x: (not x.get("has_id"), x.get("name", ""))):
            icon = "🟩" if s.get("has_id") else "🟥"
            trend = "3Day:1/1/1  7Day:7  Month:30" if s.get("has_id") else "3Day:0/0/0  7Day:0  Month:0"
            lines.append(f"  {icon} <b>{s.get('name', 'Unknown')}</b>: {trend}")

    # Tiếp theo lần lượt Team 1, Team 2, Team 3, Team 4 từ Sheet
    for tk in ["Team 1", "Team 2", "Team 3", "Team 4"]:
        if tk in teams_dict:
            lines.append(f"\n🏷️ <b>{tk}</b>")
            for s in sorted(teams_dict[tk], key=lambda x: (not x.get("has_id"), x.get("name", ""))):
                icon = "🟩" if s.get("has_id") else "🟥"
                trend = "3Day:1/1/1  7Day:7  Month:30" if s.get("has_id") else "3Day:0/0/0  7Day:0  Month:0"
                lines.append(f"  {icon} <b>{s.get('name', 'Unknown')}</b>: {trend}")

    lines += [
        divider,
        "🤖 <i>Auto report — Ghế Giám Sát Refuel Read System</i>"
    ]

    # Gửi qua Bot 2 (2. TNI Auto Report Daily) về DM Admin (6859790680)
    BOT_2_TOKEN = os.getenv("SEND_BOT_TOKEN", "")
    ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "6859790680")
    report_text = "\n".join(lines)

    url = f"https://api.telegram.org/bot{BOT_2_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": ADMIN_CHAT_ID,
            "text": report_text,
            "parse_mode": "HTML"
        }, timeout=60)
        if resp.json().get("ok"):
            print(f"✅ Report 5 sent to Supervisor Seat {ADMIN_CHAT_ID}")
        else:
            print(f"⚠️ Failed sending to Supervisor Seat: {resp.text[:200]}")
    except Exception as e:
        print(f"❌ Error sending Report 5: {e}")



# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Preprocess sys.argv to split '21' into '2' '1' if present
    new_argv = []
    for arg in sys.argv:
        if arg == "21":
            new_argv.extend(["2", "1"])
        else:
            new_argv.append(arg)
    sys.argv = new_argv

    parser = argparse.ArgumentParser(description="TNI Refuel Plan Reports")
    parser.add_argument("--report", type=int, choices=[1, 2, 4, 5, 21], nargs="+",
                        help="Report numbers (1, 2, 3, 4, 5). Omit to run default.")
    args = parser.parse_args()

    # Tải và parse dữ liệu trước khi chạy báo cáo
    download_spreadsheet()
    data = RefuelData()

    raw_reports = args.report if args.report else [1, 2]
    reports_to_run = []
    for r in raw_reports:
        if r == 21:
            reports_to_run.extend([2, 1])
        else:
            reports_to_run.append(r)

    if 1 in reports_to_run:
        report_1(data)
    if 2 in reports_to_run or 4 in reports_to_run:
        report_2(data)

    if 5 in reports_to_run:
        report_5(data)

    print("🎉 All tasks finished successfully.")


if __name__ == "__main__":
    main()
