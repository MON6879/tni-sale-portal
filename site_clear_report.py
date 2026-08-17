"""
site_clear_report.py — Báo cáo 6.1 Site Clear Today.
Lấy dữ liệu từ Google Sheet:
- Spreadsheet ID: 1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow
- Tab: Site down Clear Morning (gid: 582589665)
- Cột B: 2 ký tự đầu xác định Team (T1 -> Team 1, T2/T5 -> Team 2, T3 -> Team 3, T4 -> Team 4)
- Cột C: Toàn bộ nội dung sự cố đã clear trong ngày.
- Giờ gửi: 07:18, 10:18, 14:18, 17:18 (Myanmar Time).
"""

import asyncio
import io
import logging
import os
import sys
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from telegram import Bot
from dotenv import load_dotenv
from delete_old_helper import delete_old_messages_bot, save_msgids

load_dotenv()
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

SEND_BOT_TOKEN = os.getenv("SEND_BOT_TOKEN", "")
SPREADSHEET_ID = "1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow"
GID = "582589665"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid={GID}"

TZ_MM = timezone(timedelta(hours=6, minutes=30))

from tni_config import TELEGRAM_GROUPS, TEAM_NAMES

TEAM_GROUPS = {
    1: TELEGRAM_GROUPS["T1"],
    2: TELEGRAM_GROUPS["T2"],
    3: TELEGRAM_GROUPS["T3"],
    4: TELEGRAM_GROUPS["T4"],
}
CONTROL_CHAT_ID = -5251698940

MAIN_GAS_FALLBACK = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "").strip()
if not APPS_SCRIPT_URL or "AKfycbzGFdnE" in APPS_SCRIPT_URL or "AKfycbz-" not in APPS_SCRIPT_URL:
    APPS_SCRIPT_URL = MAIN_GAS_FALLBACK


def is_valid_text(val):
    if not val:
        return False
    val_s = str(val).strip()
    return val_s not in ("", "-", "nan", "None", "NaN", "0")


async def send_msg(bot: Bot, cid: int, text: str, label: str = ""):
    """Gửi tin nhắn Telegram an toàn, tự động chia nhỏ nếu vượt 4000 ký tự."""
    MAX = 4000
    msg_ids = []

    def chunk_text(t):
        parts, current = [], ""
        for line in t.split("\n"):
            while len(line) > MAX:
                segment = line[:MAX]
                if current:
                    parts.append(current)
                    current = ""
                parts.append(segment)
                line = line[MAX:]
            if len(current) + len(line) + 1 > MAX:
                parts.append(current)
                current = line
            else:
                current += ("\n" if current else "") + line
        if current:
            parts.append(current)
        return parts

    try:
        if len(text) <= MAX:
            sent = await bot.send_message(chat_id=cid, text=text)
            msg_ids.append(sent.message_id)
        else:
            for p in chunk_text(text):
                if p.strip():
                    sent = await bot.send_message(chat_id=cid, text=p)
                    msg_ids.append(sent.message_id)
                    await asyncio.sleep(0.3)
        logger.info(f"✅ {label} → {cid}")
        return True, msg_ids
    except Exception as e:
        logger.error(f"❌ {label} → {cid}: {e}")
        return False, msg_ids


async def main():
    logger.info("🚀 Starting Report 6.1 — Site Clear Today...")
    now_str = datetime.now(TZ_MM).strftime("%d/%m/%Y %H:%M")

    # 1. Tải dữ liệu từ Google Sheets
    try:
        resp = requests.get(SHEET_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str)
        logger.info(f"✅ Loaded sheet: {len(df)} rows, {len(df.columns)} cols")
    except Exception as ex:
        logger.error(f"❌ Lỗi tải Google Sheet gid={GID}: {ex}")
        return

    # 2. Phân loại theo Team (Cột B lấy 2 ký tự đầu)
    team_data = {1: [], 2: [], 3: [], 4: []}

    for idx, row in df.iterrows():
        if idx < 1:  # Bỏ qua row 1 metadata
            continue
        col_b = str(row.iloc[1]).strip() if len(row) > 1 and not pd.isna(row.iloc[1]) else ""
        col_c = str(row.iloc[2]).strip() if len(row) > 2 and not pd.isna(row.iloc[2]) else ""

        if not col_b or not is_valid_text(col_c):
            continue

        prefix = col_b[:2].upper()
        t_num = None
        if prefix == "T1":
            t_num = 1
        elif prefix in ("T2", "T5"):
            t_num = 2
        elif prefix == "T3":
            t_num = 3
        elif prefix == "T4":
            t_num = 4

        if t_num:
            team_data[t_num].append(col_c)

    if not SEND_BOT_TOKEN:
        logger.error("Missing SEND_BOT_TOKEN")
        return

    # 3. Gửi tin nhắn cho từng Team và Control
    async with Bot(token=SEND_BOT_TOKEN) as bot:
        total_sent = 0
        control_blocks = []

        for t_num, chat_id in TEAM_GROUPS.items():
            t_name = TEAM_NAMES[t_num]
            records = team_data[t_num]

            if not records:
                logger.info(f"Team {t_num} ({t_name}) không có dữ liệu clear site → Bỏ qua.")
                continue

            # Xóa tin cũ trước khi gửi mới
            if APPS_SCRIPT_URL:
                try:
                    delete_old_messages_bot(SEND_BOT_TOKEN, chat_id, APPS_SCRIPT_URL, f"SITE_CLEAR_REPORT_T{t_num}")
                except Exception as ex:
                    logger.warning(f"Lỗi khi xóa tin nhắn cũ qua GAS của {t_name}: {ex}")

            lines = [
                f"📋 6.1 Report — Site Clear Today — {t_name}",
                f"📅 {now_str}",
                "━━━━━━━━━━━━━━━━━━━━",
            ]
            for rec in records:
                lines.append(f"• {rec}")

            msg_text = "\n".join(lines)
            ok, sent_ids = await send_msg(bot, chat_id, msg_text, f"{t_name} Report 6.1")
            if ok and sent_ids:
                total_sent += 1
                if APPS_SCRIPT_URL:
                    try:
                        save_msgids(APPS_SCRIPT_URL, f"SITE_CLEAR_REPORT_T{t_num}", sent_ids)
                    except Exception as ex:
                        logger.warning(f"Lỗi khi lưu msgids của {t_name}: {ex}")

            control_blocks.append(f"【{t_name}】\n" + "\n".join([f"• {rec}" for rec in records]))
            await asyncio.sleep(0.5)

        # Gửi bản tổng hợp cho CONTROL nếu có dữ liệu
        if control_blocks and CONTROL_CHAT_ID:
            if APPS_SCRIPT_URL:
                try:
                    delete_old_messages_bot(SEND_BOT_TOKEN, CONTROL_CHAT_ID, APPS_SCRIPT_URL, "SITE_CLEAR_REPORT_CONTROL")
                except Exception as ex:
                    logger.warning(f"Lỗi xóa tin cũ Control: {ex}")

            ctrl_lines = [
                "📋 6.1 Report — Site Clear Today — ALL TEAMS",
                f"📅 {now_str}",
                "━━━━━━━━━━━━━━━━━━━━",
                "\n\n".join(control_blocks),
            ]
            ctrl_text = "\n".join(ctrl_lines)
            ok, ctrl_ids = await send_msg(bot, CONTROL_CHAT_ID, ctrl_text, "Control Report 6.1")
            if ok and ctrl_ids and APPS_SCRIPT_URL:
                try:
                    save_msgids(APPS_SCRIPT_URL, "SITE_CLEAR_REPORT_CONTROL", ctrl_ids)
                except Exception as ex:
                    logger.warning(f"Lỗi lưu msgids Control: {ex}")

        logger.info(f"🎉 Hoàn tất Report 6.1 (Đã gửi {total_sent} teams).")


if __name__ == "__main__":
    asyncio.run(main())
