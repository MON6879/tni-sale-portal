import os
import io
import asyncio
import logging
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from delete_old_helper import delete_old_messages_bot, save_msgids

load_dotenv()

# ===================== CẤU HÌNH =====================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

SEND_BOT_TOKEN  = os.getenv("SEND_BOT_TOKEN")
MAIN_GAS_FALLBACK = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "").strip()
if not APPS_SCRIPT_URL or "AKfycbzGFdnE" in APPS_SCRIPT_URL:
    APPS_SCRIPT_URL = MAIN_GAS_FALLBACK
CONTROL_CHAT_ID = -5251698940

SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8"
    "/gviz/tq?tqx=out:csv&sheet=BOD+assign&headers=1"
)

# Timezone Myanmar
TZ_MM = timezone(timedelta(hours=6, minutes=30))

# Trái tim màu cố định cho mỗi Dep (đồng cỡ)
DEP_SQUARES = {
    "admin": "💙", "asset": "💚", "cm": "🟡", "fbb": "🧡",
    "finance": "💜", "hr": "❤️", "m&e": "🤎", "manager": "🤍",
    "pm": "🖤", "transmission": "💙", "construction": "🧡",
    "construction projects": "🧡", "noc": "🖤", "technical": "💙",
    "team 05": "🔵", "team 5": "🔵", "team5": "🔵"
}

# Map gộp các tên alias của Team về tên chuẩn (Team 5 gộp vào Team 2)
ROLE_ALIASES = {
    "team 05": "Team 2",
    "team 5": "Team 2",
    "team5": "Team 2",
    "t5": "Team 2",
    "team 5 merg": "Team 2",
    "team 01": "Team 1",
    "team 02": "Team 2",
    "team 03": "Team 3",
    "team 04": "Team 4",
}

def parse_date(val):
    if pd.isna(val):
        return None
    val_str = str(val).strip().replace(".", "/")
    if not val_str:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parts = val_str.split()
            if parts:
                return datetime.strptime(parts[0], "%d/%m/%Y").date()
        except Exception:
            pass
        try:
            return datetime.strptime(val_str, fmt).date()
        except Exception:
            pass
    return None

async def send_msg(bot: Bot, chat_id: int, text: str, label: str, reply_markup=None):
    """Gửi tin nhắn Telegram an toàn."""
    try:
        sent = await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=reply_markup)
        logger.info(f"✅ Sent message to {chat_id} ({label})")
        return True, [sent.message_id]
    except Exception as e:
        logger.error(f"❌ Error sending message to {chat_id} ({label}): {e}")
        return False, []

async def main():
    if not SEND_BOT_TOKEN:
        logger.error("Missing SEND_BOT_TOKEN environment variable")
        return

    logger.info("🚀 Starting Daily BOD Assign Report...")
    
    # Tải dữ liệu từ sheet
    try:
        resp = requests.get(SHEET_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None)
        logger.info(f"✅ Loaded sheet BOD assign: {len(df)} rows")
    except Exception as e:
        logger.error(f"❌ Error downloading BOD assign sheet: {e}")
        return

    if len(df) <= 1:
        logger.info("Sheet is empty or only has headers.")
        return

    # Dữ liệu từ hàng 1 trở đi (hàng 0 là tiêu đề)
    data_rows = df.iloc[1:]

    today = datetime.now(TZ_MM)
    d0 = today.date()
    d1 = (today - timedelta(days=1)).date()
    d2 = (today - timedelta(days=2)).date()
    d6_limit = (today - timedelta(days=6)).date()

    stats = {}
    bod_new_assigns = {}

    for idx, row in data_rows.iterrows():
        # Đảm bảo hàng có đủ số cột
        if len(row) < 3:
            continue
            
        role_val = row[0]       # Cột A: Chức vụ/Phòng ban
        completed_val = row[7] if len(row) > 7 else None # Cột H: Dep update Date complete
        confirm_val = row[9] if len(row) > 9 else None   # Cột J: Manager Confirm
        assign_date_val = row[3] if len(row) > 3 else None # Cột D: Assign date
        col_o_val = row[14] if len(row) > 14 else ""     # Cột O: BOD New assign formula

        if pd.isna(role_val) or not str(role_val).strip():
            continue
        role_raw = str(role_val).strip()

        # Bỏ qua các hàng tiêu đề phụ nếu có
        if role_raw.lower() in ("nan", "", "assign admin", "chức vụ", "phòng ban"):
            continue

        # Gộp Team 5 / Team 05 về Team 2
        role = ROLE_ALIASES.get(role_raw.lower(), role_raw)

        # Tích lũy số liệu thống kê tổng hợp
        if role not in stats:
            stats[role] = {
                "total_assigned": 0,
                "d0": 0, "d1": 0, "d2": 0,
                "d7": 0, "month": 0, "unconfirmed": 0
            }

        stats[role]["total_assigned"] += 1

        row_date = parse_date(completed_val)
        is_completed = row_date is not None
        is_confirmed = not pd.isna(confirm_val) and str(confirm_val).strip() != ""

        if is_completed:
            if row_date == d0:
                stats[role]["d0"] += 1
            elif row_date == d1:
                stats[role]["d1"] += 1
            elif row_date == d2:
                stats[role]["d2"] += 1

            if row_date >= d6_limit:
                stats[role]["d7"] += 1

            if row_date.year == today.year and row_date.month == today.month:
                stats[role]["month"] += 1

            if not is_confirmed:
                stats[role]["unconfirmed"] += 1

        # Lọc các task "BOD New assign" cho Transmission, M&E, Team 05...
        col_o_str = str(col_o_val).strip().lower()
        is_new_assign = ("bod new assign" in col_o_str or 
                         "new assign" in col_o_str or 
                         parse_date(assign_date_val) == d0)

        pic_val = row[1] if len(row) > 1 else ""
        content_val = row[2] if len(row) > 2 else ""

        if is_new_assign and content_val and not pd.isna(content_val):
            if role not in bod_new_assigns:
                bod_new_assigns[role] = []
            
            bod_new_assigns[role].append({
                "row": idx + 2,
                "pic": str(pic_val).strip() if not pd.isna(pic_val) else "",
                "content": str(content_val).strip(),
                "status": str(col_o_val).strip() if str(col_o_val).strip() else "BOD New assign"
            })

    # ── 1. Gửi Báo cáo Tổng hợp (Daily BOD Assign - Summary) ──
    if stats:
        sorted_stats = sorted(stats.items())
        date_str = today.strftime("%d/%m/%Y")
        now_str = today.strftime("%H:%M")

        lines = [
            "📋 <b>2. Report — Daily BOD Assign — Summary</b>",
            f"📅 {date_str}  |  🕐 {now_str}",
            "📌 Compilation of BOD-assigned tasks completed and confirmation status by department.",
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]

        total_assigned_all = total_d0 = total_d1 = total_d2 = total_d7 = total_month = total_unconfirmed = 0

        for i, (role, s) in enumerate(sorted_stats):
            dot = DEP_SQUARES.get(role.lower().strip(), "🔹")
            lines.append(
                f"{dot} <b>{role}</b>: Task assign : {s['total_assigned']} = 3 day {s['d2']}/{s['d1']}/{s['d0']} "
                f"7 day: {s['d7']} Month: {s['month']} Not Yet Cofirm : {s['unconfirmed']} case"
            )
            
            total_assigned_all += s["total_assigned"]
            total_d0 += s["d0"]
            total_d1 += s["d1"]
            total_d2 += s["d2"]
            total_d7 += s["d7"]
            total_month += s["month"]
            total_unconfirmed += s["unconfirmed"]

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("📊 <b>Total:</b>")
        lines.append(
            f"   Task assign : {total_assigned_all} = 3 day {total_d2}/{total_d1}/{total_d0} "
            f"7 day: {total_d7} Month: {total_month} Not Yet Cofirm : {total_unconfirmed} case"
        )
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")

        report_msg = "\n".join(lines)

        if APPS_SCRIPT_URL:
            delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, "BOD_ASSIGN_CONTROL")

        async with Bot(token=SEND_BOT_TOKEN) as bot:
            ok, msg_ids = await send_msg(bot, CONTROL_CHAT_ID, report_msg, "BOD_ASSIGN_CONTROL")
            if ok and msg_ids and APPS_SCRIPT_URL:
                save_msgids(APPS_SCRIPT_URL, "BOD_ASSIGN_CONTROL", msg_ids)

    # ── 2. Gửi Chi tiết Task Mới (Transmission, M&E, Team 05...) sang CONTROL & Teams ──
    date_str = today.strftime("%d/%m/%Y")
    now_str = today.strftime("%H:%M")

    for role_name, tasks in bod_new_assigns.items():
        role_lower = role_name.lower().strip()
        dot = DEP_SQUARES.get(role_lower, "💙")
        
        report_lines = [
            f"📋 <b>1.1. Report — BOD Assign to {role_name}</b>",
            f"📅 {date_str}  |  🕐 {now_str}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"{dot} <b>{role_name}</b>: You have new Assign from BOD or Manager:",
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]
        
        buttons = []
        for task in tasks:
            task_line = f"• Row #{task['row']} | PIC: {task['pic']} | Content: {task['content']}"
            report_lines.append(task_line)
            buttons.append([InlineKeyboardButton(f"Yes, I received Row #{task['row']}", callback_data=f"ack_bod_assign_{task['row']}")])
            
        report_lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        report_msg = "\n".join(report_lines)
        
        state_key = f"BOD_ASSIGN_{role_name.upper().replace(' ', '_')}_CONTROL"
        if APPS_SCRIPT_URL:
            delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, state_key)
            
        async with Bot(token=SEND_BOT_TOKEN) as bot:
            keyboard = InlineKeyboardMarkup(buttons)
            ok, msg_ids = await send_msg(bot, CONTROL_CHAT_ID, report_msg, state_key, reply_markup=keyboard)
            if ok and msg_ids and APPS_SCRIPT_URL:
                save_msgids(APPS_SCRIPT_URL, state_key, msg_ids)

if __name__ == "__main__":
    asyncio.run(main())
