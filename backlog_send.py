"""
backlog_send.py — Gửi báo cáo tồn đọng (backlog) hàng ngày vào lúc 17:10 Myanmar.
Không gửi lên nhóm CONTROL.
Không xóa tin cũ (đóng băng tin nhắn).
"""
import asyncio
import io
import logging
import os
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
if not APPS_SCRIPT_URL or "AKfycbzGFdnE" in APPS_SCRIPT_URL:
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
    Trả về emoji chấm tròn màu chuẩn cho từng phòng ban.
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
    """Xác định sub-team (ví dụ: T3 S1 hoặc T3) từ các cột team."""
    for col_idx in [18, 33, 48, 63, 76]:  # S, AH, AW, BL, BY
        val = str(row.iloc[col_idx]).strip() if col_idx < len(row) else ""
        if val and val.lower() not in ("nan", "none", "-"):
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
    # KVA columns definition
    kva_cols = {
        "oil_filter": [("8KVA", "AA"), ("12KVA", "AB"), ("30KVA", "AC"), ("12DKVA", "AD"), ("8.TIP", "AE")],
        "fuel_filter": [("8KVA", "AP"), ("12KVA", "AQ"), ("30KVA", "AR"), ("12DKVA", "AS"), ("8.TIP", "AT")],
        "air_filter": [("8KVA", "BE"), ("12KVA", "BF"), ("30KVA", "BG"), ("12DKVA", "BH"), ("8.TIP", "BI")],
        "oil_plan": [("8KVA", "BS"), ("12KVA", "BT"), ("30KVA", "BU"), ("12DKVA", "BV"), ("8.TIP", "BW")],
        "coolant_plan": [("8KVA", "CF"), ("12KVA", "CG"), ("30KVA", "CH"), ("12DKVA", "CI"), ("8.TIP", "CJ")]
    }

    # Filter kva_cols to only keep columns that have a valid header in row 4 (index 3) of df
    filtered_kva_cols = {}
    for key, cols in kva_cols.items():
        filtered_cols = []
        for kva_name, col_let in cols:
            c_idx = col_letter_to_index(col_let)
            if c_idx < len(df.columns):
                # Row 4 of the sheet corresponds to index 3 in df (since index 0 is row 1)
                header_val = df.iloc[3, c_idx] if len(df) > 3 else None
                if is_valid(header_val):
                    filtered_cols.append((kva_name, col_let))
        filtered_kva_cols[key] = filtered_cols

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
            # T1 (D)
            val1_t1 = row.iloc[3] if len(row) > 3 else ""
            if is_valid(val1_t1): team_msg1[1].append(f"• {label1}: {val1_t1}")
            # T2 (E)
            val1_t2 = row.iloc[4] if len(row) > 4 else ""
            if is_valid(val1_t2): team_msg1[2].append(f"• {label1}: {val1_t2}")
            # T3 (F)
            val1_t3 = row.iloc[5] if len(row) > 5 else ""
            if is_valid(val1_t3): team_msg1[3].append(f"• {label1}: {val1_t3}")
            # T4 (G)
            val1_t4 = row.iloc[6] if len(row) > 6 else ""
            if is_valid(val1_t4): team_msg1[4].append(f"• {label1}: {val1_t4}")
            # T5 (H)
            val1_t5 = row.iloc[7] if len(row) > 7 else ""
            if is_valid(val1_t5): team_msg1[5].append(f"• {label1}: {val1_t5}")

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

        # --- Xử lý Báo cáo 3 (DG Material) ---
        subteam = get_subteam_for_row(row)
        if subteam:
            if subteam not in subteams_dg:
                subteams_dg[subteam] = {
                    "oil_filter": {}, "fuel_filter": {}, "air_filter": {}, "oil_plan": {}, "coolant_plan": {},
                    "oil_sum_need": 0.0, "oil_have": 0.0, "oil_diff": 0.0,
                    "coolant_sum_need": 0.0, "coolant_have": 0.0, "coolant_diff": 0.0
                }
            sd = subteams_dg[subteam]
            
            # KVA sums
            for key, cols in filtered_kva_cols.items():
                for kva_name, col_let in cols:
                    c_idx = col_letter_to_index(col_let)
                    val = to_float(row.iloc[c_idx]) if c_idx < len(row) else 0.0
                    sd[key][kva_name] = sd[key].get(kva_name, 0.0) + val
                    
            # Volumes
            sd["oil_sum_need"] += to_float(row.iloc[67]) if len(row) > 67 else 0.0
            sd["oil_have"] += to_float(row.iloc[68]) if len(row) > 68 else 0.0
            sd["oil_diff"] += to_float(row.iloc[69]) if len(row) > 69 else 0.0
            
            sd["coolant_sum_need"] += to_float(row.iloc[80]) if len(row) > 80 else 0.0
            sd["coolant_have"] += to_float(row.iloc[81]) if len(row) > 81 else 0.0
            sd["coolant_diff"] += to_float(row.iloc[82]) if len(row) > 82 else 0.0

    # ── 4. Xóa sạch tin cũ Report 1, 2, 3 và Gửi báo cáo mới qua Bot API + GAS Cache ──
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
                def fmt_f(val):
                    if val > 0:
                        val_str = str(int(val)) if val.is_integer() else f"{val:.1f}"
                        return f"🔵 {val_str}"
                    val_str = str(int(val)) if val.is_integer() else f"{val:.1f}"
                    return val_str

                def fmt_kva(cat_key, kva_dict):
                    parts = []
                    cols = filtered_kva_cols.get(cat_key, [])
                    for kva, _ in cols:
                        val = int(kva_dict.get(kva, 0.0))
                        if val > 0:
                            parts.append(f"🔵 {kva}: {val}")
                        else:
                            parts.append(f"{kva}: {val}")
                    return " <+> ".join(parts)

                lines3 = [
                    f"📋 3. Report — Main DG Material Need — {t_name}",
                    f"📅 {now_str}",
                    f"📌 Shows generator materials, oil, and coolant needs for each sub-team.",
                    "━━━━━━━━━━━━━━━━━━━━"
                ]

                for subteam in matched_subteams:
                    sd = subteams_dg[subteam]
                    lines3.append(f"\n📍 SUB-TEAM: {subteam}")
                    lines3.append(f"⚙️ Sum DG KVA Need change Oil Filter:\n   • {fmt_kva('oil_filter', sd['oil_filter'])}")
                    lines3.append(f"⚙️ Sum DG KVA Need change Fuel Filter:\n   • {fmt_kva('fuel_filter', sd['fuel_filter'])}")
                    lines3.append(f"⚙️ Sum DG KVA Need change Air Filter:\n   • {fmt_kva('air_filter', sd['air_filter'])}")
                    lines3.append(f"🛢️ Sum DG KVA Need change Oil:\n   • {fmt_kva('oil_plan', sd['oil_plan'])}")
                    lines3.append(f"   👉 Sum Need: {fmt_f(sd['oil_sum_need'])} L | Have at Team: {fmt_f(sd['oil_have'])} L | Diff: {fmt_f(sd['oil_diff'])} L")
                    lines3.append(f"❄️ Sum DG KVA Need change water Coolant:\n   • {fmt_kva('coolant_plan', sd['coolant_plan'])}")
                    lines3.append(f"   👉 Sum Need: {fmt_f(sd['coolant_sum_need'])} L | Have at Team: {fmt_f(sd['coolant_have'])} L | Diff: {fmt_f(sd['coolant_diff'])} L")

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
