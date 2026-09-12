"""
cable_link_down_report.py
==========================
Ghế BOT-CABLE-15 / Toa Cable Link Down (:16 & :46 MMT)
Gửi báo cáo sự cố cáp (Cột C, tab 'Link down now', sheet Cable Collect Database +MDG)
vào nhóm Telegram: 8 TNI CABLE BROKEN SOS (CABLE_CHAT_ID: -5531350787).
Cơ chế: Tin nào xóa tin nấy (xóa tin cũ trước khi gửi tin mới).
"""

import os
import sys
import csv
import io
import re
import html
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

# ── Cấu hình ─────────────────────────────────────────────────────────────
CABLE_BOT_TOKEN = os.getenv("CABLE_BOT_TOKEN") or "8758104446:AAH3o7lMCxBXn70ThAXweH1DddmRkJrgwWo"
MAIN_GAS_FALLBACK = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
_raw_url = os.getenv("APPS_SCRIPT_URL", "").strip()
if not _raw_url or "AKfycbzGFdnE" in _raw_url or "AKfycbz-" not in _raw_url:
    APPS_SCRIPT_URL = MAIN_GAS_FALLBACK
else:
    APPS_SCRIPT_URL = _raw_url

CABLE_SHEET_ID  = "1C8hU8SXpOdq-v6z7iLGoqwDJmO9DYudZ3rhflb7LC8Y"
LINK_DOWN_GID   = "263097982"
SHEET_CSV_URL   = f"https://docs.google.com/spreadsheets/d/{CABLE_SHEET_ID}/export?format=csv&gid={LINK_DOWN_GID}"

TZ_MM           = timezone(timedelta(hours=6, minutes=30))  # Myanmar UTC+6:30
DELETE_KEY      = "CABLE_LINK_DOWN_REPORT"

# Import helper xóa tin cũ
try:
    from delete_old_helper import delete_old_messages_bot, save_msgids
except ImportError:
    def delete_old_messages_bot(token, cid, gas_url, key):
        return 0
    def save_msgids(gas_url, key, msgids):
        pass


TEAM_EMOJIS = {
    "1": "🟠",
    "2": "🔵",
    "3": "🟢",
    "4": "🟡",
}


def get_team_info(team_raw: str, text_val: str) -> tuple[str, str]:
    """
    Trả về (emoji, team_display) ví dụ: ('🟠', '🟠T1'), ('🟠', '🟠T1 S1'), ('🔵', '🔵T2s1')
    Quy tắc: Màu T1 và T1S1 giống nhau (🟠), T2 và T2S1 giống nhau (🔵), v.v. giống Site Down.
    """
    t = (team_raw or "").strip()
    if not t:
        m = re.search(r'\b(T[1-4](?:[sS]\d+|\s*S\d+)?)\b', text_val, flags=re.IGNORECASE)
        if m:
            t = m.group(1)
        else:
            m2 = re.search(r'\bTeam\s*([1-4])\b', text_val, flags=re.IGNORECASE)
            if m2:
                t = f"T{m2.group(1)}"
    m = re.search(r'(?:Team\s*|T)([1-4])', t, flags=re.IGNORECASE)
    if m:
        num = m.group(1)
        emoji = TEAM_EMOJIS.get(num, "")
        clean = re.sub(r'^[🔴🔵🟢🟡🟠🟣⚪⚫]\s*', '', t)
        clean = re.sub(r'^Team\s*', 'T', clean, flags=re.IGNORECASE)
        return emoji, f"{emoji}{clean}"
    return ("", t)


def colorize_team_in_text(text: str) -> str:
    """
    Đưa chấm màu theo T1 vào giống Site Down:
    - T1 và T1S1 (T1 S1, T1s1) -> 🟠T1, 🟠T1 S1
    - T2 và T2S1 (T2 S1, T2s1) -> 🔵T2, 🔵T2 S1
    - T3 và T3S1 (T3 S1, T3s1) -> 🟢T3, 🟢T3 S1
    - T4 và T4S1 (T4 S1, T4s1) -> 🟡T4, 🟡T4 S1
    """
    # Escape HTML đặc biệt (<, >, &) để Telegram không bị lỗi parse entities
    text = html.escape(text)

    # Colorize team tokens
    text = re.sub(r'(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?\b(T1(?:[sS]\d+|\s*S\d+)?)\b', r'🟠\1', text)
    text = re.sub(r'(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?\b(T2(?:[sS]\d+|\s*S\d+)?)\b', r'🔵\1', text)
    text = re.sub(r'(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?\b(T3(?:[sS]\d+|\s*S\d+)?)\b', r'🟢\1', text)
    text = re.sub(r'(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?\b(T4(?:[sS]\d+|\s*S\d+)?)\b', r'🟡\1', text)
    text = re.sub(r'(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?\bTeam\s*1\b', r'🟠Team 1', text, flags=re.IGNORECASE)
    text = re.sub(r'(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?\bTeam\s*2\b', r'🔵Team 2', text, flags=re.IGNORECASE)
    text = re.sub(r'(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?\bTeam\s*3\b', r'🟢Team 3', text, flags=re.IGNORECASE)
    text = re.sub(r'(?:[🔴🔵🟢🟡🟠🟣⚪⚫]\s*)?\bTeam\s*4\b', r'🟡Team 4', text, flags=re.IGNORECASE)
    # Ngắt dòng cho link down và thêm icon
    text = re.sub(r'\s+(link down\s*[:\-])', r'\n🔗 \1', text, flags=re.IGNORECASE)
    # Ngắt dòng cho Plz note
    text = re.sub(r'\s+(Plz\s+note\b)', r'\n\1', text, flags=re.IGNORECASE)
    return text


def fetch_link_down_items() -> list[dict]:
    """Đọc dữ liệu sống từ Cột C của tab 'Link down now'."""
    print(f"[Cable Link Down] 🔄 Fetching live data from Google Sheet (GID {LINK_DOWN_GID})...")
    resp = requests.get(SHEET_CSV_URL, timeout=20)
    resp.raise_for_status()
    reader = csv.reader(io.StringIO(resp.text))
    rows = list(reader)

    items = []
    for idx, row in enumerate(rows):
        if idx == 0:
            continue  # Bỏ qua hàng tiêu đề C1 ('link down')
        if len(row) > 2:
            val = row[2].strip()
            if val:
                team = row[3].strip() if len(row) > 3 else ""
                emoji, tag = get_team_info(team, val)
                items.append({
                    "row_idx": idx + 1,
                    "text": colorize_team_in_text(val),
                    "team": team,
                    "emoji": emoji,
                    "tag": tag,
                    "raw": val
                })

    print(f"[Cable Link Down] 📊 Found {len(items)} link down item(s).")
    return items


def build_telegram_message(items: list[dict]) -> str:
    """Xây dựng nội dung tin nhắn gửi vào nhóm Telegram (100% tiếng Anh)."""
    now = datetime.now(TZ_MM)
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M")

    lines = [
        "🔌 <b>15 TNI CABLE — LINK DOWN REPORT</b>",
        f"📅 {date_str}  |  ⏰ {time_str} (Myanmar)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]

    if not items:
        lines.append("✅ <b>All routes normal — No link down at present</b>")
    else:
        for idx, it in enumerate(items, 1):
            if it.get("tag"):
                header = f"{it['emoji']} <b>Link #{idx} | {it['tag']}:</b>"
            else:
                header = f"📍 <b>Link #{idx}:</b>"
            lines.append(header)
            lines.append(it["text"])
            if idx < len(items):
                lines.append("──────────────────────────────")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 Total: <b>{len(items)} link(s) down</b>")
    lines.append("🤖 <i>Auto sent by 15 TNI CABLE</i>")

    return "\n".join(lines)


def send_telegram_report(text: str) -> int | None:
    """Gửi tin nhắn vào nhóm 8 TNI CABLE BROKEN SOS qua Bot 15."""
    url = f"https://api.telegram.org/bot{CABLE_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CABLE_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    resp = requests.post(url, json=payload, timeout=20)
    data = resp.json()
    if data.get("ok"):
        mid = data["result"]["message_id"]
        print(f"[Cable Link Down] ✅ Sent message ID {mid} to group {CABLE_CHAT_ID}")
        return mid
    else:
        print(f"[Cable Link Down] ❌ Send failed: {data}")
        return None


def run_cable_link_down():
    """Hàm chạy chính: Đọc sheet -> Xóa tin cũ -> Gửi tin mới -> Lưu message_id."""
    print("=" * 60)
    print("🔌 KHỞI ĐỘNG TOA BÁO CÁO CABLE LINK DOWN (BOT 15)")
    print("=" * 60)

    try:
        items = fetch_link_down_items()
    except Exception as ex:
        print(f"[Cable Link Down] ❌ Lỗi đọc dữ liệu sheet: {ex}")
        return

    msg_text = build_telegram_message(items)

    print(f"[Cable Link Down] 🗑️ Cleaning up previous link down report for {DELETE_KEY}...")
    delete_old_messages_bot(CABLE_BOT_TOKEN, CABLE_CHAT_ID, APPS_SCRIPT_URL, DELETE_KEY)

    new_mid = send_telegram_report(msg_text)

    if new_mid:
        save_msgids(APPS_SCRIPT_URL, DELETE_KEY, [new_mid])
        print(f"[Cable Link Down] 💾 Saved new message ID {new_mid} to GAS Properties.")

    print("=" * 60)
    print("🏁 TOA BÁO CÁO CABLE LINK DOWN HOÀN TẤT")
    print("=" * 60)


if __name__ == "__main__":
    run_cable_link_down()
