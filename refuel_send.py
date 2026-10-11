import os
import sys
import re
import requests
import csv
import io
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

from tg_utils import get_msg_id, set_msg_id, tg_delete, tg_delete_by_title

import openpyxl

# Cấu hình bot và chat ID mặc định của group 9 TNI REQUEST REFUEL
REFUEL_BOT_TOKEN = os.getenv("REFUEL_BOT_TOKEN", "")
REFUEL_CHAT_ID   = os.getenv("REFUEL_CHAT_ID", "-5469544739")
# URL Apps Script của bảng tính Refuel riêng, nếu không có sẽ tự động dùng chung APPS_SCRIPT_URL
REFUEL_APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", os.getenv("REFUEL_APPS_SCRIPT_URL", ""))

TZ_MM = timezone(timedelta(hours=6, minutes=30))  # Múi giờ Myanmar UTC+6:30


def fetch_refuel_data() -> list[str] | None:
    """
    Tải trực tiếp 100% dữ liệu sống từ Google Sheet:
    - Tab 'Request Partner Auto' (GID 1188751570):
      + Ô AL5: Header App Approved & Ngày cập nhật
      + Cột B: DG ID (chỉ lấy mã DG cột B, giữ nguyên _1, _2 không gộp)
      + Cột V: Ngày yêu cầu (chỉ lấy dòng khi Cột V có ngày)
      + Cột W (fallback Q): Số lít yêu cầu
      + Cột AB: Phân đội (Team 1, T1 S1, Team 2, T2 S1, Team 3, T3 S1, Team 4)
    - Tab 'Team request': Các yêu cầu bổ sung của thành viên chưa hoàn thành
    - Tab 'Refueled': Loại trừ các trạm/máy phát đã đổ dầu
    """
    SPREADSHEET_ID = "1JxrA4pJo92Xx_SpwLnOQxphVYwE2iFhLrCOHmyVVuuM"
    xlsx_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=xlsx"
    xlsx_path = "scratch/sheet_refuel.xlsx"

    # 1. Tải mới nhất từ Google Sheets
    try:
        os.makedirs("scratch", exist_ok=True)
        resp = requests.get(xlsx_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=40)
        resp.raise_for_status()
        with open(xlsx_path, "wb") as f:
            f.write(resp.content)
        print(f"📥 Downloaded fresh {xlsx_path} ({len(resp.content)} bytes)")
    except Exception as e:
        print(f"⚠️ Warning downloading spreadsheet: {e}", file=sys.stderr)
        if not os.path.exists(xlsx_path):
            print("❌ No spreadsheet available, exiting", file=sys.stderr)
            return None

    try:
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        if "Request Partner Auto" not in wb.sheetnames:
            print("❌ Sheet 'Request Partner Auto' not found", file=sys.stderr)
            return None
        ws_req = wb["Request Partner Auto"]

        # Master DG ID map
        all_dgs = set()
        site_to_dg = {}
        dg_to_team = {}
        for r in range(6, ws_req.max_row + 1):
            b = str(ws_req.cell(row=r, column=2).value or "").strip().upper()
            c = str(ws_req.cell(row=r, column=3).value or "").strip().upper()
            ab = str(ws_req.cell(row=r, column=28).value or "").strip()
            if b and b.startswith("TNI"):
                all_dgs.add(b)
                if ab and ab != "0":
                    dg_to_team[b] = ab
                if c:
                    site_to_dg.setdefault(c, []).append(b)

        def norm_dg(name: str, team: str = "") -> str:
            s = str(name or "").strip().upper()
            if s in all_dgs:
                return s
            m = re.search(r"\(DG\s*([12])\)", s)
            if m:
                cand = re.sub(r"\(DG\s*[12]\)", "", s).strip() + "_" + m.group(1)
                if cand in all_dgs:
                    return cand
            if s in site_to_dg:
                dgs = site_to_dg[s]
                if len(dgs) == 1:
                    return dgs[0]
                for dg in dgs:
                    if dg_to_team.get(dg) == team:
                        return dg
                return dgs[0]
            return f"{s}_1" if s.startswith("TNI") and not re.search(r"_\d+$", s) else s

        def normalize_team(raw_team: str) -> str:
            """Chuẩn hóa tên team theo Cột AB (Team 1, Team 1 S1, Team 2, Team 2 S1, Team 3, Team 3 S1, Team 4)."""
            s = str(raw_team or "").strip().upper()
            if re.search(r"\b(TEAM\s*1\s*S1|T1\s*S1)\b", s) or s == "T1 S1":
                return "Team 1 S1"
            if re.search(r"\b(TEAM\s*2\s*S1|T2\s*S1)\b", s) or s == "Team 2 S1" or s == "T2 S1":
                return "Team 2 S1"
            if re.search(r"\b(TEAM\s*3\s*S1|T3\s*S1)\b", s) or s == "Team 3 S1" or s == "T3 S1":
                return "Team 3 S1"
            if re.search(r"\b(TEAM\s*4\s*S1|T4\s*S1)\b", s) or s == "Team 4 S1" or s == "T4 S1":
                return "Team 4 S1"
            if re.search(r"\b(TEAM\s*1|T1)\b", s) or s == "T1":
                return "Team 1"
            if re.search(r"\b(TEAM\s*2|T2)\b", s) or s == "T2":
                return "Team 2"
            if re.search(r"\b(TEAM\s*3|T3)\b", s) or s == "T3":
                return "Team 3"
            if re.search(r"\b(TEAM\s*4|T4)\b", s) or s == "T4":
                return "Team 4"
            return "Team 1"

        def to_date_obj(v):
            if isinstance(v, datetime):
                return v.date()
            s = str(v or "").strip()
            if len(s) >= 10 and s[2] == "/" and s[5] == "/":
                try:
                    return datetime.strptime(s[:10], "%d/%m/%Y").date()
                except Exception:
                    pass
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(s[:len(fmt)], fmt).date()
                except Exception:
                    pass
            return None

        # Đọc danh sách đã đổ dầu (Refueled)
        latest_refueled = {}
        if "Refueled" in wb.sheetnames:
            ws_ref = wb["Refueled"]
            for r in range(2, ws_ref.max_row + 1):
                dt = to_date_obj(ws_ref.cell(row=r, column=2).value)
                if not dt:
                    continue
                dg_c = norm_dg(ws_ref.cell(row=r, column=3).value)
                site_d = norm_dg(ws_ref.cell(row=r, column=4).value)
                for dg in (dg_c, site_d):
                    if dg:
                        if dg not in latest_refueled or dt > latest_refueled[dg]:
                            latest_refueled[dg] = dt

        req_by_team_date = {}

        # 1. Đọc trực tiếp 100% từ Request Partner Auto: Cột V (Ngày) -> Cột B (DG ID) : Cột W (Lít)
        for r in range(6, ws_req.max_row + 1):
            dg_id = str(ws_req.cell(row=r, column=2).value or "").strip().upper()
            if not dg_id or not dg_id.startswith("TNI"):
                continue
            dt_req = to_date_obj(ws_req.cell(row=r, column=22).value)  # Col V: Date
            if not dt_req:
                continue

            # Bỏ qua nếu Cột Y đã có ngày đổ dầu (đã refuel xong)
            val_y = str(ws_req.cell(row=r, column=25).value or "").strip()  # Col Y
            if val_y and val_y not in ("-", "none", "0", ""):
                continue

            if dg_id in latest_refueled and latest_refueled[dg_id] >= dt_req:
                continue

            team_raw = str(ws_req.cell(row=r, column=28).value or "").strip()  # Col AB
            team = normalize_team(team_raw)

            qty_val = ws_req.cell(row=r, column=23).value  # Col W
            if not qty_val or str(qty_val).strip() in ("", "0"):
                qty_val = ws_req.cell(row=r, column=17).value  # Col Q
            try:
                qty = int(float(str(qty_val).strip()))
            except Exception:
                qty = 440

            dt_str = dt_req.strftime("%d/%m/%Y")
            req_by_team_date.setdefault(team, {}).setdefault(dt_str, []).append((dg_id, qty))

        # Đếm tổng số site duy nhất
        all_unique_sites = set()
        for team, dates in req_by_team_date.items():
            for dt, items in dates.items():
                for dg_id, qty in items:
                    all_unique_sites.add(dg_id)

        total_sites_count = len(all_unique_sites)

        # Xây dựng các khối nội dung báo cáo
        output_rows = []

        # Header từ ô AL5
        al5 = str(ws_req["AL5"].value or "").strip()
        if not al5:
            al5 = "🟣 /No /Approved App: /41 case < + > /Last updated: /04/09/26"
        header_line = f"{al5} => /Needs updating /Need request Refuel: /{total_sites_count} Site"
        output_rows.append(header_line)

        team_emojis = {
            "Team 1": "🔴",
            "Team 1 S1": "🔴",
            "Team 2": "🔵",
            "Team 2 S1": "🔵",
            "Team 3": "🟢",
            "Team 3 S1": "🟢",
            "Team 4": "🟡"
        }

        teams_order = ["Team 1", "Team 1 S1", "Team 2", "Team 2 S1", "Team 3", "Team 3 S1", "Team 4"]

        for team in teams_order:
            dates = req_by_team_date.get(team, {})
            if not dates:
                continue
            sorted_dates = sorted(dates.keys(), key=lambda d: datetime.strptime(d, "%d/%m/%Y"))
            emoji = team_emojis.get(team, "🔴")

            team_lines = [f"{emoji} {team}"]
            for dt in sorted_dates:
                items = dates[dt]
                item_str = " ".join([f"/{dg}: {q}" for dg, q in items])
                team_lines.append(f"{dt}: {item_str}")
            output_rows.append("\n".join(team_lines))

        # Footer
        footer = "/Note: According to the list of stations and the required number of liters, refuel at the correct station with the correct number of liters. ❓ /No request on group 9 TNI REQUEST REFUEL = ❌ /No refueling allowed."
        output_rows.append(footer)

        return output_rows
    except Exception as ex:
        print(f"❌ Error parsing refuel spreadsheet: {ex}", file=sys.stderr)
        return None


def send_telegram(chat_id: str, text: str) -> tuple[bool, int | None]:
    """Gửi tin nhắn định dạng HTML lên group Telegram (có tự động retry bằng Plain Text nếu lỗi)."""
    url = f"https://api.telegram.org/bot{REFUEL_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=60,
    )
    res_json = resp.json()
    ok = res_json.get("ok", False)
    msg_id = None
    if ok:
        print(f"✅ Report sent to {chat_id}")
        msg_id = res_json.get("result", {}).get("message_id")
    else:
        print(f"⚠️ HTML send failed, retrying plain text: {resp.text[:200]}", file=sys.stderr)
        plain_text = re.sub(r'<[^>]*>', '', text)
        resp_fallback = requests.post(
            url,
            json={"chat_id": chat_id, "text": plain_text},
            timeout=60,
        )
        res_json_fb = resp_fallback.json()
        ok = res_json_fb.get("ok", False)
        if ok:
            print(f"✅ Report sent to {chat_id} (Plain Text fallback)")
            msg_id = res_json_fb.get("result", {}).get("message_id")
        else:
            print(f"❌ Send failed: {resp_fallback.text[:200]}", file=sys.stderr)
    return ok, msg_id


def deduplicate_refuel_rows(rows: list[str]) -> list[str]:
    """
    Bỏ trùng các mã trạm / máy phát (ví dụ: TNI0013_1) trong báo cáo tổng hợp Request Refuel.
    - Thu thập dữ liệu: Thu thập 100% tất cả yêu cầu gửi về (cho phép dính trùng do yêu cầu chưa thực hiện theo kế hoạch cũ).
    - Lập báo cáo tổng hợp: Tự động lọc BỎ TRÙNG theo mã trạm/máy phát để so sánh chính xác với Kế hoạch (Plan).
    """
    if not rows:
        return []

    deduped = []
    seen_sites = set()

    for line in rows:
        line_clean = str(line).strip()
        if not line_clean:
            continue

        # Tìm các mã trạm dạng TNIxxxx hoặc TNIxxxx_1
        site_matches = re.findall(r'TNI\d+(?:_\d+)?', line_clean, re.IGNORECASE)
        if site_matches:
            # Nếu tất cả mã trạm trong dòng này đã từng xuất hiện ở dòng trước -> Bỏ qua dòng trùng
            all_seen = all(s.upper() in seen_sites for s in site_matches)
            if all_seen:
                continue

            # Đánh dấu các mã trạm mới vào danh sách đã thấy
            for s in site_matches:
                seen_sites.add(s.upper())

        deduped.append(line_clean)

    return deduped


def parse_sites_from_row(line_text: str) -> list[tuple[str, str]]:
    """
    Tách các trạm và dung tích dầu từ dòng Request Refuel, tự động LỌC BỎ các mốc ngày (DD/MM/YYYY).
    Trả về list [(site_code, qty_str), ...]
    Ví dụ: 'TNI0129_1: 660 + TNI0006_1: 660 < + > 01/08/2026: TNI0031_1: 440' -> [('TNI0129_1', '660L'), ('TNI0006_1', '660L'), ('TNI0031_1', '440L')]
    """
    if not line_text:
        return []

    # Loại bỏ phần tiêu đề "Team X request" nếu có
    clean_line = re.sub(r'^Team\s*\d+\s*request\s*', '', line_text, flags=re.IGNORECASE)

    # Tách chuỗi theo dấu + hoặc < + >
    raw_segments = re.split(r'\s*\+\s*|\s*<\s*\+\s*>\s*', clean_line)
    sites = []
    seen = set()

    for seg in raw_segments:
        seg_clean = seg.strip()
        if not seg_clean:
            continue

        # Tìm mã trạm TNIxxxx_y và dung tích L
        m = re.search(r'(TNI\d+(?:_\d+)?)\s*:\s*(\d+)', seg_clean, re.IGNORECASE)
        if m:
            site_code = m.group(1).upper()
            qty = m.group(2) + "L"
            if site_code not in seen:
                seen.add(site_code)
                sites.append((site_code, qty))

    return sites


LOCAL_STATE_FILE = "scratch/refuel_msg_ids.json"

def get_saved_msg_ids(key: str) -> list[str]:
    """Lấy danh sách ID tin nhắn cũ từ file cục bộ và GAS BotState."""
    ids = []
    if os.path.exists(LOCAL_STATE_FILE):
        try:
            with open(LOCAL_STATE_FILE, "r", encoding="utf-8") as f:
                import json
                data = json.load(f)
                val = data.get(key, "")
                if val:
                    ids.extend(str(val).split(","))
        except Exception:
            pass
    gas_val = get_msg_id(key)
    if gas_val:
        for item in str(gas_val).split(","):
            if item and item not in ids:
                ids.append(item)
    return [i.strip() for i in ids if i.strip()]

def save_saved_msg_ids(key: str, sent_ids: list[int | str]):
    """Lưu danh sách ID tin mới vào file cục bộ và GAS BotState."""
    id_str = ",".join(map(str, sent_ids))
    try:
        import json
        os.makedirs("scratch", exist_ok=True)
        data = {}
        if os.path.exists(LOCAL_STATE_FILE):
            with open(LOCAL_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        data[key] = id_str
        with open(LOCAL_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"⚠️ Error saving local state: {e}", file=sys.stderr)
    set_msg_id(key, id_str)

def delete_refuel_msg(chat_id: str, msg_id: int | str, timeout: int = 3) -> bool:
    """Xóa tin nhắn cũ bằng REFUEL_BOT_TOKEN."""
    if not msg_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{REFUEL_BOT_TOKEN}/deleteMessage"
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "message_id": int(msg_id)},
            timeout=timeout
        )
        res_json = resp.json()
        if res_json.get("ok"):
            print(f"🗑️ Deleted old refuel msg #{msg_id}")
            return True
    except Exception:
        pass
    return False

def delete_all_previous_refuel_msgs(chat_id: str, key: str):
    """Xóa đúng 100% các tin nhắn Refuel cũ đã lưu theo key (TIN NÀO XÓA TIN NẤY - tuyệt đối không xóa offset lân cận)."""
    saved_ids = get_saved_msg_ids(key)
    for msg_id in saved_ids:
        delete_refuel_msg(chat_id, msg_id, timeout=3)


def format_and_send_report(rows: list[str]) -> list[int]:
    """Gửi nguyên văn nội dung các ô Y2:Y5 giữ đúng mẫu ngắn gọn (tự động xóa tin cũ trước khi gửi tin mới)."""
    now = datetime.now(TZ_MM)
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M")
    
    msg_lines = []
    for line in rows:
        line_clean = str(line).strip()
        if line_clean and "Report need refuel" not in line_clean:
            if line_clean.lower().startswith("/note:") or line_clean.lower().startswith("note:"):
                msg_lines.append(line_clean)
                msg_lines.append("")
                continue

            # Escape HTML characters < >
            clean = line_clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            # 1. Loại bỏ các dòng chỉ chứa đơn độc emoji chấm màu (🔴 🔵 🟢 🟡 🟠 🟣)
            clean_lines = []
            for l in clean.split('\n'):
                l_strip = l.strip()
                if l_strip in ["🔴", "🔵", "🟢", "🟡", "🟠", "🟣"]:
                    continue
                clean_lines.append(l)

            clean = "\n".join(clean_lines).strip()
            msg_lines.append(clean)
            msg_lines.append("")  # Dòng trống giữa các Team
            
    if not msg_lines:
        msg_lines.append("📭 No refuel requests today.")
        msg_lines.append("")
        
    # Chia nhỏ dòng thô thành các phần an toàn (< 3800 ký tự)
    chunks = []
    current_chunk = []
    current_len = 0
    
    for line in msg_lines:
        if current_len + len(line) + 1 > 3800:
            chunks.append(current_chunk)
            current_chunk = [line]
            current_len = len(line)
        else:
            current_chunk.append(line)
            current_len += len(line) + 1
            
    if current_chunk:
        chunks.append(current_chunk)
        
    sent_ids = []
    STATE_KEY = f"refuel_msg_ids_{REFUEL_CHAT_ID}"

    # 1. XÓA TRIỆT ĐỂ TIN CŨ CỦA CHÍNH BẢN TIN NÀY (TIN NÀO XÓA TIN NẤY - KHÔNG XÓA CHÉO SANG PLAN & PROGRESS)
    delete_all_previous_refuel_msgs(REFUEL_CHAT_ID, STATE_KEY)
    tg_delete_by_title(REFUEL_CHAT_ID, "TNI REQUEST REFUEL", bot_token=REFUEL_BOT_TOKEN)

    for idx, chunk_lines in enumerate(chunks):
        title = "🔄 <b>[Report 1] TNI REQUEST REFUEL — Daily Report</b>"
        if len(chunks) > 1:
            title += f" (Part {idx + 1}/{len(chunks)})"

        lines = [
            title,
            f"📅 {date_str}  ⏰ {time_str} (Myanmar)",
            "━━━━━━━━━━━━━━━━━━━━━",
            ""
        ]
        for line in chunk_lines:
            lines.append(line)
        if lines[-1] != "🤖 <i>Auto report by @TNI_REFUEL_BOT</i>":
            if lines[-1] != "":
                lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━━")
            lines.append("🤖 <i>Auto report by @TNI_REFUEL_BOT</i>")

        msg = "\n".join(lines)
        ok, msg_id = send_telegram(REFUEL_CHAT_ID, msg)
        if ok and msg_id:
            sent_ids.append(msg_id)

    # 2. LƯU ID CÁC TIN VỪA GỬI MỚI VÀO CẢ LOCAL FILE VÀ GAS BOTSTATE
    if sent_ids:
        save_saved_msg_ids(STATE_KEY, sent_ids)

    return sent_ids


def fetch_cell_o1() -> str:
    """Tải động giá trị ô O1 (Cột O, Dòng 1) từ tab gid=201295323 của Google Sheets Refuel."""
    csv_url = "https://docs.google.com/spreadsheets/d/1JxrA4pJo92Xx_SpwLnOQxphVYwE2iFhLrCOHmyVVuuM/export?format=csv&gid=201295323"
    try:
        resp = requests.get(csv_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        resp.encoding = "utf-8"
        reader = list(csv.reader(io.StringIO(resp.text)))
        if reader and len(reader[0]) >= 15 and reader[0][14].strip():
            return reader[0][14].strip()
    except Exception as e:
        print(f"⚠️ Error fetching cell O1: {e}", file=sys.stderr)
    return "@Raja HO @Sunil @Sunil Fuel @Aung Naing Refuel Team Sent Plan and Sent result refuel before go out Site. Team leader assign follow template who go to monitor refuel @Paing Aung @Naing @Myint Ko Ko Aung @MinPaing_VCM Nay Myo @Pyae Phyo Zaw @thureinnaing"


def send_note_reply_as_phongha79(reply_to_msg_id: int):
    """Gửi Note reply bằng tài khoản user @Phongha79 (Telethon) TRẢ LỜI BÁO CÁO DẦU cho Report 6 theo dõi."""
    tele_session = os.getenv("TELEGRAM_SESSION", "").strip()
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()

    if not (tele_session and api_id and api_hash):
        print("⚠️ TELEGRAM_SESSION not set — skipping Telethon Note reply", file=sys.stderr)
        return

    note_text = fetch_cell_o1()
    if not note_text:
        return

    import asyncio
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    async def _send():
        async with TelegramClient(StringSession(tele_session), int(api_id), api_hash) as client:
            cid = int(REFUEL_CHAT_ID) if str(REFUEL_CHAT_ID).startswith("-") else REFUEL_CHAT_ID
            await client.send_message(cid, note_text, reply_to=reply_to_msg_id)
            print(f"📝 Note reply (@Phongha79) sent to {cid} replying to #{reply_to_msg_id}")

    try:
        asyncio.run(_send())
    except Exception as err:
        print(f"⚠️ Error sending Note reply as @Phongha79: {err}", file=sys.stderr)


def main():
    # ⛔ VÔ HIỆU HÓA: Report này đã được gộp vào refuel_plan_report.py report_1()
    # Tin gộp: [Report 1] TNI REQUEST REFUEL (6 cột: DG ID | Date | Req | Plan | Ref | Diff)
    # Disabled: 06/09/2026
    print("⛔ refuel_send.py DISABLED — merged into refuel_plan_report.py report_1()")
    return

    print(f"⛽ Refuel Report — {datetime.now(TZ_MM).strftime('%d/%m/%Y %H:%M')} Myanmar")

    if not REFUEL_BOT_TOKEN:
        print("❌ REFUEL_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    # Lấy dữ liệu mới từ Apps Script
    rows = fetch_refuel_data()
    if rows is None:
        print("⚠️ No data available from spreadsheet, exiting")
        sys.exit(1)

    # Gửi báo cáo (xóa tin cũ tự động qua tg_send_fresh)
    sent_ids = format_and_send_report(rows)
    
    # Gửi Note reply bằng tài khoản user @Phongha79 (lấy nội dung từ ô O1)
    if sent_ids:
        send_note_reply_as_phongha79(sent_ids[-1])


if __name__ == "__main__":
    main()
