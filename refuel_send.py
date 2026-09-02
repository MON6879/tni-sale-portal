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

# Cấu hình bot và chat ID mặc định của group 9 TNI REQUEST REFUEL
REFUEL_BOT_TOKEN = os.getenv("REFUEL_BOT_TOKEN", "8811503647:AAEVIToiaPbDeNTUPLsoI5xhdnufKdChsME")
REFUEL_CHAT_ID   = os.getenv("REFUEL_CHAT_ID", "-5469544739")
# URL Apps Script của bảng tính Refuel riêng, nếu không có sẽ tự động dùng chung APPS_SCRIPT_URL
REFUEL_APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", os.getenv("REFUEL_APPS_SCRIPT_URL", ""))

TZ_MM = timezone(timedelta(hours=6, minutes=30))  # Múi giờ Myanmar UTC+6:30


def fetch_refuel_data() -> list[str] | None:
    """Tải trực tiếp nội dung các ô Y2 trở đi (Column Y) của tab Need Refuel từ Google Sheets CSV Export."""
    csv_url = "https://docs.google.com/spreadsheets/d/1JxrA4pJo92Xx_SpwLnOQxphVYwE2iFhLrCOHmyVVuuM/export?format=csv&gid=0"
    try:
        resp = requests.get(csv_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        resp.encoding = "utf-8"
        reader = list(csv.reader(io.StringIO(resp.text)))
        data = []
        for r in reader[1:10]:  # Read rows 2 to 10 (Y2:Y10)
            if len(r) > 24 and r[24].strip():
                data.append(r[24].strip())
        if data:
            return data
    except Exception as e:
        print(f"⚠️ Direct CSV fetch warning: {e}", file=sys.stderr)

    # Fallback qua Apps Script API
    gas_url = (
        REFUEL_APPS_SCRIPT_URL or
        "https://script.google.com/macros/s/AKfycbwHyzulEMVGjslfjN_m38HzpFZHRfk2qwbQmdwb6MMqBM8xNm20JJxxzW_4zTNzp3n24Q/exec"
    )
    if gas_url:
        try:
            resp = requests.get(gas_url, params={"action": "get_refuel_data"}, timeout=30)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                return resp.json()["data"]
        except Exception as ex:
            print(f"⚠️ GAS fallback warning: {ex}", file=sys.stderr)
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
    """Xóa triệt để 100% tất cả các tin nhắn Refuel cũ trong nhóm."""
    saved_ids = get_saved_msg_ids(key)
    deleted_set = set()

    for msg_id in saved_ids:
        if delete_refuel_msg(chat_id, msg_id, timeout=3):
            deleted_set.add(str(msg_id))
        try:
            base_id = int(msg_id)
            for offset in range(-3, 4):
                target_id = base_id + offset
                if target_id > 0 and str(target_id) not in deleted_set:
                    if delete_refuel_msg(chat_id, target_id, timeout=3):
                        deleted_set.add(str(target_id))
        except Exception:
            pass


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

            # 2. CHỈ CHO DUY NHẤT 'Team 1 request' xuống dòng mới bên dưới văn bản header
            clean = re.sub(r'([^\n])\s*(?:🔴|🔵|🟢|🟡|🟠|🟣)?\s*(Team\s*1\s*request)', r'\1\n\n🔴 \2', clean, flags=re.IGNORECASE)

            # Đảm bảo dòng bắt đầu bằng Team 1 có chấm đỏ 🔴
            if re.search(r'^Team\s*1\b', clean, re.IGNORECASE) and not clean.startswith("🔴"):
                clean = "🔴 " + clean

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

    # 1. XÓA TRIỆT ĐỂ 100% TẤT CẢ TIN CỦ BẰNG SMART SCANNER & REFUEL_BOT_TOKEN
    delete_all_previous_refuel_msgs(REFUEL_CHAT_ID, STATE_KEY)
    tg_delete_by_title(REFUEL_CHAT_ID, "TNI REQUEST REFUEL", bot_token=REFUEL_BOT_TOKEN)
    tg_delete_by_title(REFUEL_CHAT_ID, "Report 1", bot_token=REFUEL_BOT_TOKEN)

    for idx, chunk_lines in enumerate(chunks):
        title = "🔄 <b>[Report 1] TNI REQUEST REFUEL — Daily Report</b>"
        if len(chunks) > 1:
            title += f" (Phần {idx + 1}/{len(chunks)})"

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
