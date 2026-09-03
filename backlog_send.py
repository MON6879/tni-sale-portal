"""
backlog_send.py — Gửi báo cáo tồn đọng (backlog) hàng ngày vào lúc 17:10 Myanmar.
Không gửi lên nhóm CONTROL.
Không xóa tin cũ (đóng băng tin nhắn).
"""
import asyncio
import io
import logging
import os
import re
import sys
import time
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
SPREADSHEET_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&gid=159298579"

TZ_MM = timezone(timedelta(hours=6, minutes=30))

from tni_config import TELEGRAM_GROUPS, TEAM_NAMES

TEAM_GROUPS = {
    1: TELEGRAM_GROUPS["T1"],
    2: TELEGRAM_GROUPS["T2"],
    3: TELEGRAM_GROUPS["T3"],
    4: TELEGRAM_GROUPS["T4"],
}

MAIN_GAS_FALLBACK = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "").strip()
if not APPS_SCRIPT_URL or "AKfycbz-NZlBk8q2" not in APPS_SCRIPT_URL:
    APPS_SCRIPT_URL = MAIN_GAS_FALLBACK

CHATID_TO_KEY = {
    TELEGRAM_GROUPS["T1"]: "BACKLOG_TEAM_T1",
    TELEGRAM_GROUPS["T2"]: "BACKLOG_TEAM_T2",
    TELEGRAM_GROUPS["T3"]: "BACKLOG_TEAM_T3",
    TELEGRAM_GROUPS["T4"]: "BACKLOG_TEAM_T4",
}


def col_letter_to_index(col_str):
    exp = 0
    idx = 0
    for char in reversed(col_str.upper()):
        idx += (ord(char) - 64) * (26 ** exp)
        exp += 1
    return idx - 1


def is_valid(val):
    if not val:
        return False
    val_s = str(val).strip()
    if val_s in ("", "-", "nan", "None", "NaN"):
        return False
    return True


def is_non_zero(val):
    if not is_valid(val):
        return False
    val_s = str(val).strip()
    try:
        if float(val_s) == 0.0:
            return False
    except ValueError:
        pass
    return True


def to_float(val):
    if not is_valid(val):
        return 0.0
    try:
        return float(str(val).strip())
    except ValueError:
        return 0.0


# ── Department Color Dot Rule (Quy luật chấm tròn màu phòng ban) ──
DEPT_COLOR_MAP = {
    # 1. Asset / Kho / Vật tư -> 🟣 Tím (Purple)
    "ASSET": "🟣",
    "KHO": "🟣",
    "MATERIAL": "🟣",
    "INVENTORY": "🟣",

    # 2. CM (Corrective Maintenance) / Bảo dưỡng / Sự cố -> 🟢 Xanh lá (Green)
    "CM": "🟢",
    "MAINTENANCE": "🟢",
    "REPAIR": "🟢",

    # 3. Admin / Hành chính / Văn phòng -> 🔵 Xanh dương (Blue)
    "ADMIN": "🔵",
    "ADMINISTRATION": "🔵",
    "OFFICE": "🔵",

    # 4. Transmission / Cáp / Truyền dẫn / FBB -> 🟠 Cam (Orange)
    "TRANSMISSION": "🟠",
    "CABLE": "🟠",
    "FIBER": "🟠",
    "FBB": "🟠",

    # 5. Technical / M&E / Power / Máy nổ / Nhiên liệu -> 🟡 Vàng (Yellow)
    "TECHNICAL": "🟡",
    "M&E": "🟡",
    "POWER": "🟡",
    "GENSET": "🟡",
    "FUEL": "🟡",
    "REFUEL": "🟡",

    # 6. BOD / Ban Giám Đốc / PM / Manager / NOC / Control -> 🔴 Đỏ (Red)
    "BOD": "🔴",
    "DIRECTOR": "🔴",
    "PM": "🔴",
    "MANAGER": "🔴",
    "MANAGEMENT": "🔴",
    "NOC": "🔴",
    "CONTROL": "🔴",

    # 7. Finance / Kế toán / Thu chi -> 🟤 Nâu (Brown)
    "FINANCE": "🟤",
    "ACCOUNTING": "🟤",

    # 8. HR / Nhân sự / Tuyển dụng / Điểm danh -> ⚪ Trắng (White)
    "HR": "⚪",
    "ATTENDANCE": "⚪",
    "PERSONNEL": "⚪",

    # 9. Construction / Dự án -> 🟣 Tím
    "CONSTRUCTION": "🟣",
    "PROJECT": "🟣",
}

# 8 Bảng màu chấm tròn chuẩn lặp lại tuần hoàn khi vượt số lượng
COLOR_PALETTE = ["🟣", "🟢", "🔵", "🟠", "🟡", "🔴", "🟤", "⚪"]

def get_dept_color_dot(cat_str: str) -> str:
    """
    Trả về emoji chấm tròn màu chuẩn cho từng phòng ban (Bản tin 1: Daily Backlog).
    Nếu phòng ban mới/chưa định nghĩa, sẽ tự động lặp lại (cycle) tuần hoàn 8 màu theo mã băm.
    """
    if not cat_str:
        return "•"
    clean_cat = str(cat_str).strip().upper()
    for key, dot in DEPT_COLOR_MAP.items():
        if key == clean_cat or key in clean_cat:
            return dot
    # Fallback tuần hoàn 8 màu nếu nhiều hơn số màu quy định
    h = sum(ord(c) for c in clean_cat)
    return COLOR_PALETTE[h % len(COLOR_PALETTE)]


# ── DailyWO Task Square Color Rule (Quy luật chấm màu vuông cho nhãn DailyWO) ──
LABEL_SQUARE_MAP = {
    # 1. Cable / Fiber / Patrol / FTTH / DWDM -> 🟧 Cam (Orange)
    "CABLE": "🟧",
    "PATROL": "🟧",
    "FTTH": "🟧",
    "DWDM": "🟧",
    "IP": "🟧",

    # 2. Mytel Station -> 🟩 Xanh lá (Green)
    "MYTEL": "🟩",
    "MAINTENANCE_MYTEL": "🟩",

    # 3. Towerco Station -> 🟪 Tím (Purple)
    "TOWERCO": "🟪",
    "MAINTENANCE_TOWERCO": "🟪",

    # 4. Generator / Engine Oil / Battery / Smart CB -> 🟨 Vàng (Yellow)
    "GENERATOR": "🟨",
    "RADIATOR": "🟨",
    "ENGINE OIL": "🟨",
    "BATTERY": "🟨",
    "SMART CB": "🟨",

    # 5. Main Station / Core / Failure -> 🟥 Đỏ (Red)
    "MAIN_STATION": "🟥",
    "MAIN STATION": "🟥",
    "FAILURE": "🟥",

    # 6. Solar Power System -> 🟦 Xanh dương (Blue)
    "SOLAR": "🟦",

    # 7. 5S / Cleaning / Office -> 🟫 Nâu (Brown)
    "5S": "🟫",
}

# Bảng 9 màu vuông chuẩn lặp lại tuần hoàn khi có nhãn mới
SQUARE_PALETTE = ["🟧", "🟩", "🟪", "🟨", "🟥", "🟦", "🟫", "⬛", "⬜"]

def get_label_square_dot(label_str: str) -> str:
    """
    Trả về emoji chấm vuông màu chuẩn cho từng nhãn công việc DailyWO (Bản tin 2: DailyWO).
    Nếu nhãn mới hoặc vượt quá số lượng, sẽ tự động lặp lại (cycle) tuần hoàn 9 màu theo mã băm.
    """
    if not label_str:
        return "•"
    clean_label = str(label_str).strip().upper()
    for key, sq in LABEL_SQUARE_MAP.items():
        if key in clean_label:
            return sq
    # Fallback tuần hoàn bảng màu vuông
    h = sum(ord(c) for c in clean_label)
    return SQUARE_PALETTE[h % len(SQUARE_PALETTE)]


async def send_msg(bot, cid, text, label=""):
    """Gửi tin nhắn, xử lý giới hạn 4096 ký tự của Telegram."""
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


def get_team_for_row(row):
    """Xác định team từ các cột team S, AH, AW, BL, BY."""
    for col_idx in [18, 33, 48, 63, 76]:  # S, AH, AW, BL, BY
        val = str(row.iloc[col_idx]).strip() if col_idx < len(row) else ""
        if val and val.lower() not in ("nan", "none", "-"):
            prefix = val[:2].upper()
            if prefix == "T1":
                return 1
            elif prefix in ("T2", "T5"):
                return 2
            elif prefix == "T3":
                return 3
            elif prefix == "T4":
                return 4
    return None


def get_subteam_for_row(row):
    """Xác định mã sub-team (T1, T1 S1, T2, T2 S1, T3, T3 S1, T4) từ Cột S (Col 18)."""
    if len(row) > 18:
        val = str(row.iloc[18]).strip()
        if val.startswith(("T1", "T2", "T3", "T4", "T5")):
            return val.upper()
    return None


async def main():
    # ── 1. Đợi đến đúng 17:10 Myanmar ──
    now = datetime.now(TZ_MM)
    target = now.replace(hour=17, minute=10, second=0, microsecond=0)
    
    # Nếu chạy trước 17:10, ngủ cho tới lúc đó
    if "--now" not in sys.argv and now < target:
        delay = (target - now).total_seconds()
        logger.info(f"Giờ Myanmar hiện tại: {now.strftime('%H:%M:%S')}. Đang chờ {delay:.1f} giây để gửi báo cáo lúc 17:10...")
        await asyncio.sleep(delay)
        
    now = datetime.now(TZ_MM)
    now_str = now.strftime("%d/%m/%Y %H:%M")
    logger.info(f"🚀 Bắt đầu gửi báo cáo backlog – {now_str}")

    if not SEND_BOT_TOKEN:
        logger.error("SEND_BOT_TOKEN không được thiết lập!")
        return

    # ── 2. Tải dữ liệu bảng tính với retry ──
    df = None
    for attempt in range(5):
        try:
            resp = requests.get(SHEET_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str)
            logger.info(f"Đọc thành công bảng tính: {len(df)} dòng.")
            break
        except Exception as e:
            logger.warning(f"Lần tải {attempt+1} thất bại: {e}")
            if attempt < 4:
                await asyncio.sleep(5)
                
    if df is None:
        logger.error("Không thể tải dữ liệu bảng tính sau 5 lần thử.")
        return

    # ── 3. Thu thập dữ liệu báo cáo ──
    # Báo cáo 1
    # T1: D(3), T2: E(4), T3: F(5), T4: G(6), T5: H(7)
    # Báo cáo 2
    # T1: M(12), T2: N(13), T3: O(14), T4: P(15)
    # Báo cáo 3
    team_msg1 = {1: [], 2: [], 3: [], 4: [], 5: []}
    team_msg2 = {1: [], 2: [], 3: [], 4: []}
    subteams_dg = {}

    # Bắt đầu duyệt từ dòng 4 (index 3)
    for idx, row in df.iterrows():
        if idx < 3:
            continue
            
        # --- Xử lý Báo cáo 1 & 2 ---
        label1 = row.iloc[2] if len(row) > 2 else ""
        if is_valid(label1):
            label1 = str(label1).strip()
            sq = get_label_square_dot(label1)
            # T1 (D)
            val1_t1 = row.iloc[3] if len(row) > 3 else ""
            if is_valid(val1_t1): team_msg1[1].append(f"{sq} {label1}: {val1_t1}")
            # T2 (E)
            val1_t2 = row.iloc[4] if len(row) > 4 else ""
            if is_valid(val1_t2): team_msg1[2].append(f"{sq} {label1}: {val1_t2}")
            # T3 (F)
            val1_t3 = row.iloc[5] if len(row) > 5 else ""
            if is_valid(val1_t3): team_msg1[3].append(f"{sq} {label1}: {val1_t3}")
            # T4 (G)
            val1_t4 = row.iloc[6] if len(row) > 6 else ""
            if is_valid(val1_t4): team_msg1[4].append(f"{sq} {label1}: {val1_t4}")
            # T5 (H)
            val1_t5 = row.iloc[7] if len(row) > 7 else ""
            if is_valid(val1_t5): team_msg1[5].append(f"{sq} {label1}: {val1_t5}")

        # Báo cáo 2 (K:L và M:P)
        cat = row.iloc[10] if len(row) > 10 else ""
        desc = row.iloc[11] if len(row) > 11 else ""
        if is_valid(cat) or is_valid(desc):
            cat_str = str(cat).strip() if is_valid(cat) else ""
            desc_str = str(desc).strip() if is_valid(desc) else ""
            dot = get_dept_color_dot(cat_str)
            if cat_str and desc_str:
                label2 = f"{dot} [{cat_str}] {desc_str}"
            elif cat_str:
                label2 = f"{dot} [{cat_str}]"
            else:
                label2 = f"• {desc_str}"

            # T1 (M)
            val2_t1 = row.iloc[12] if len(row) > 12 else ""
            if is_valid(val2_t1): team_msg2[1].append(f"{label2}:\n  {val2_t1}")
            # T2 (N)
            val2_t2 = row.iloc[13] if len(row) > 13 else ""
            if is_valid(val2_t2): team_msg2[2].append(f"{label2}:\n  {val2_t2}")
            # T3 (O)
            val2_t3 = row.iloc[14] if len(row) > 14 else ""
            if is_valid(val2_t3): team_msg2[3].append(f"{label2}:\n  {val2_t3}")
            # T4 (P)
            val2_t4 = row.iloc[15] if len(row) > 15 else ""
            if is_valid(val2_t4): team_msg2[4].append(f"{label2}:\n  {val2_t4}")

        # --- Xử lý Báo cáo 3 (DG Material Need - Cột AM, AT, BI, BX, CI, CV) ---
        if len(row) > 38:
            team_am = str(row.iloc[38]).strip() if is_valid(row.iloc[38]) else ""
            if team_am.startswith(("T1", "T2", "T3", "T4", "T5")):
                at_oil_filter = str(row.iloc[45]).strip() if len(row) > 45 and is_valid(row.iloc[45]) else ""
                bi_fuel_filter = str(row.iloc[60]).strip() if len(row) > 60 and is_valid(row.iloc[60]) else ""
                bx_air_filter = str(row.iloc[75]).strip() if len(row) > 75 and is_valid(row.iloc[75]) else ""
                ci_oil = str(row.iloc[86]).strip() if len(row) > 86 and is_valid(row.iloc[86]) else ""
                cj_need = str(row.iloc[87]).strip() if len(row) > 87 and is_valid(row.iloc[87]) else "0"
                ck_have = str(row.iloc[88]).strip() if len(row) > 88 and is_valid(row.iloc[88]) else "0"
                cl_diff = str(row.iloc[89]).strip() if len(row) > 89 and is_valid(row.iloc[89]) else "0"
                cv_cool = str(row.iloc[99]).strip() if len(row) > 99 and is_valid(row.iloc[99]) else ""
                cw_need = str(row.iloc[100]).strip() if len(row) > 100 and is_valid(row.iloc[100]) else "0"
                cx_have = str(row.iloc[101]).strip() if len(row) > 101 and is_valid(row.iloc[101]) else "0"
                cy_diff = str(row.iloc[102]).strip() if len(row) > 102 and is_valid(row.iloc[102]) else "0"

                if (team_am not in subteams_dg) and (at_oil_filter or bi_fuel_filter or bx_air_filter or ci_oil or cv_cool):
                    subteams_dg[team_am] = {
                        "oil_filter": at_oil_filter,
                        "fuel_filter": bi_fuel_filter,
                        "air_filter": bx_air_filter,
                        "oil": ci_oil,
                        "oil_need": cj_need,
                        "oil_have": ck_have,
                        "oil_diff": cl_diff,
                        "coolant": cv_cool,
                        "coolant_need": cw_need,
                        "coolant_have": cx_have,
                        "coolant_diff": cy_diff,
                    }

    # ── 4. Xóa sạch tin cũ Report 1, 2, 3 và Gửi báo cáo mới qua Bot API + GAS Cache ──
    def format_blue_dots(val_str, dot_char="🔵"):
        if not val_str:
            return "  •"
        parts = val_str.split("<+>")
        res = []
        for p in parts:
            p = p.strip()
            if ":" in p:
                k, v = p.rsplit(":", 1)
                k, v = k.strip(), v.strip()
                m = re.search(r"[-+]?\d*\.?\d+", v)
                try:
                    num_val = float(m.group(0)) if m else 0.0
                    if num_val > 0:
                        res.append(f"{dot_char} {k}: {v}")
                    else:
                        res.append(f"{k}: {v}")
                except (ValueError, TypeError):
                    res.append(f"{k}: {v}")
            elif p:
                res.append(p)
        return "  " + " <+> ".join(res) if res else "  •"

    async with Bot(token=SEND_BOT_TOKEN) as bot:
        for t_num, chat_id in TEAM_GROUPS.items():
            t_name = TEAM_NAMES[t_num]
            logger.info(f"--- Bắt đầu gửi báo cáo cho {t_name} ({chat_id}) ---")

            if APPS_SCRIPT_URL:
                try:
                    delete_old_messages_bot(SEND_BOT_TOKEN, chat_id, APPS_SCRIPT_URL, CHATID_TO_KEY[chat_id])
                except Exception as ex:
                    logger.warning(f"Lỗi khi xóa tin nhắn cũ qua GAS của {t_name}: {ex}")

            sent_msg_ids = []

            # ── 4a. Gửi Bản tin 2 (Report 1) ──
            lines2 = [
                f"📋 1. Report — Daily Backlog (Category/Description) — {t_name}",
                f"📅 {now_str}",
                f"📌 Shows detailed site assignments and tasks grouped by department (Admin, Asset, etc.) from today/recent plans.",
                "━━━━━━━━━━━━━━━━━━━━"
            ]
            if team_msg2[t_num]: # Có dữ liệu
                # Sắp xếp danh sách chi tiết (theo Category) trước khi gửi
                lines2.extend(sorted(team_msg2[t_num]))
                msg2_text = "\n".join(lines2)
                ok, m_ids = await send_msg(bot, chat_id, msg2_text, f"{t_name} Backlog Msg 2")
                sent_msg_ids.extend(m_ids)
                await asyncio.sleep(0.5)

            # ── 4b. Gửi Bản tin 1 (Report 2) ──
            lines1 = [
                f"📋 2. Report — DailyWO — {t_name}",
                f"📅 {now_str}",
                f"📌 Shows pending tasks and general cable patrol backlogs accumulated from previous days.",
                "━━━━━━━━━━━━━━━━━━━━"
            ]
            if t_num == 2:
                # Team 2 có gộp Team 5
                if team_msg1[2]:
                    lines1.append("【Team 2 Myeik】")
                    lines1.extend(team_msg1[2])
                if team_msg1[5]:
                    lines1.append("────────────────────")
                    lines1.append("【Team 5 Merged】")
                    lines1.extend(team_msg1[5])
            else:
                lines1.extend(team_msg1[t_num])

            if len(lines1) > 4: # Có dữ liệu (bao gồm header và annotation)
                msg1_text = "\n".join(lines1)
                ok, m_ids = await send_msg(bot, chat_id, msg1_text, f"{t_name} Backlog Msg 1")
                sent_msg_ids.extend(m_ids)
                await asyncio.sleep(0.5)

            # ── 4c. Gửi Bản tin 3 (Report 3) ──
            # Lọc các subteam của team hiện tại
            if t_num == 2:
                prefixes = ("T2", "T5")
            else:
                prefixes = (f"T{t_num}",)

            matched_subteams = sorted([s for s in subteams_dg.keys() if s.startswith(prefixes)])

            if matched_subteams:
                lines3 = [
                    f"📋 3. Report — Main DG Material Need — {t_name}",
                    f"📅 {now_str}",
                    f"📌 Shows generator materials, oil, and coolant needs for each sub-team.",
                    "━━━━━━━━━━━━━━━━━━━━"
                ]

                for subteam in matched_subteams:
                    sd = subteams_dg[subteam]
                    lines3.append(f"\n📍 TEAM: {subteam}")
                    lines3.append("⚙️ Sum DG KVA Need change Oil Filter:\n" + format_blue_dots(sd["oil_filter"], "🔵"))
                    lines3.append("⚙️ Sum DG KVA Need change Fuel Filter:\n" + format_blue_dots(sd["fuel_filter"], "🟡"))
                    lines3.append("⚙️ Sum DG KVA Need change Air Filter:\n" + format_blue_dots(sd["air_filter"], "🟢"))
                    lines3.append("🛢️ Sum DG KVA Need change Oil:\n" + format_blue_dots(sd["oil"], "🟠"))
                    lines3.append(f"  👉 Sum Need: {sd['oil_need']} L | Have at Team: {sd['oil_have']} L | Diff: {sd['oil_diff']} L")
                    lines3.append("❄️ Sum DG KVA Need change water Coolant:\n" + format_blue_dots(sd["coolant"], "🟣"))
                    lines3.append(f"  👉 Sum Need: {sd['coolant_need']} L | Have at Team: {sd['coolant_have']} L | Diff: {sd['coolant_diff']} L")

                msg3_text = "\n".join(lines3)
                ok, m_ids = await send_msg(bot, chat_id, msg3_text, f"{t_name} DG Msg 3")
                sent_msg_ids.extend(m_ids)
                await asyncio.sleep(0.5)

            if APPS_SCRIPT_URL and sent_msg_ids:
                try:
                    from delete_old_helper import save_msgids
                    save_msgids(APPS_SCRIPT_URL, CHATID_TO_KEY[chat_id], sent_msg_ids)
                except Exception as ex:
                    logger.warning(f"Lỗi khi lưu tin nhắn mới của {t_name}: {ex}")

    logger.info("🎉 Tất cả báo cáo backlog đã được gửi thành công.")


if __name__ == "__main__":
    asyncio.run(main())
