"""
botlookup_relay.py
==================
Gửi lệnh /down_tni@auto_nocpro_bot vào nhóm BOT LOOKUP,
đọc phản hồi → gọi GAS webhook ghi Cột A → checkAndSend() gửi tổng hợp.
Chạy qua GitHub Actions (mỗi 30p hoặc manual dispatch).
"""

import asyncio
import os
import random
import re
import requests
import sys
from datetime import datetime, timezone, timedelta

from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest

from dotenv import load_dotenv
load_dotenv()

# ── Cấu hình ──────────────────────────────────────────────────────
_RAW_API_ID    = os.environ.get("TELEGRAM_API_ID", "0").strip()
API_HASH       = os.environ.get("TELEGRAM_API_HASH", "").strip()
SESSION_STRING = os.environ.get("TELEGRAM_SESSION", "").strip()

# ══════════════════════════════════════════════════════════════════
# 🔐 CẢNH BÁO KHÓA TELEGRAM — Kiểm tra secrets ngay khi khởi động
# ══════════════════════════════════════════════════════════════════
def _send_lock_alert(msg: str):
    """Gửi cảnh báo qua Bot API (không cần Telethon) khi session bị lỗi."""
    tz  = timezone(timedelta(hours=6, minutes=30))
    now = datetime.now(tz).strftime("%H:%M %d/%m/%Y")
    alert = (
        f"🔐 *TELEGRAM SESSION LOCKED* \\({now} MMT\\)\n\n"
        f"{msg}\n\n"
        r"👉 *Fix:* GitHub → MON6879/tni\-sitedown\-relay → Settings → Secrets" + "\n"
        r"✏️ Cập nhật lại `TELEGRAM\_API\_ID` và `TELEGRAM\_SESSION`"
    )
    # Thử gửi qua SEND_BOT_TOKEN → personal ID admin
    token   = os.environ.get("SEND_BOT_TOKEN", "").strip()
    chat_id = "6859790680"  # Ha Duc Phong personal Telegram ID
    if token:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": alert, "parse_mode": "MarkdownV2"},
                timeout=15,
            )
            print(f"[{now}] ⚠️ Lock alert sent to admin!")
        except Exception as ex:
            print(f"[{now}] ⚠️ Cannot send lock alert: {ex}")
    print(f"[{now}] ❌ SESSION LOCK: {msg}")

# Kiểm tra API_ID — phải là số nguyên hợp lệ, không phải session string
try:
    API_ID = int(_RAW_API_ID)
    if API_ID == 0:
        raise ValueError("API_ID = 0")
except ValueError:
    _send_lock_alert(
        f"❌ `TELEGRAM\\_API\\_ID` không hợp lệ\\!\n"
        f"Giá trị hiện tại: `{_RAW_API_ID[:30]}\\.\\.\\.`\n"
        f"⚠️ Có thể đã paste nhầm SESSION string vào ô API\\_ID\\."
    )
    sys.exit(1)

# Kiểm tra SESSION_STRING — phải đủ dài (Telethon session ≥ 100 ký tự)
if len(SESSION_STRING) < 100:
    _send_lock_alert(
        f"❌ `TELEGRAM\\_SESSION` bị trống hoặc quá ngắn\\!\n"
        f"Độ dài hiện tại: `{len(SESSION_STRING)}` ký tự \\(cần ≥ 100\\)\\.\n"
        f"⚠️ Session string Telethon hợp lệ phải có ~350 ký tự\\."
    )
    sys.exit(1)
# ══════════════════════════════════════════════════════════════════

SOURCE_GROUP   = "Botlookup"
COMMAND        = "/down_tni@auto_nocpro_bot"

REFUEL_GROUP_ID = -5469544739   # 9 TNI REQUEST REFUEL — scan Letter Submit/Approved
REFUEL_GAS_URL  = os.environ.get("REFUEL_APPS_SCRIPT_URL", "")

# Nhóm nhận Note từ @Phongha79 (để theo dõi ai đọc)
ALL_GROUPS = {
    "CONTROL": -5251698940,  # Chat (chưa migrate)
    "T1":       4215695747,  # Channel
    "T2":       4480845549,  # Channel
    "T3":       4369170658,  # Channel
    "T4":       4293741999,  # Channel
}
TARGET_CHAT_ID = ALL_GROUPS["CONTROL"]   # fallback error messages

BOT_USERNAME   = "auto_nocpro_bot"
WAIT_REPLY_SEC = 35

ACTIVE_START   = (3, 30)
ACTIVE_END     = (22, 15)

MIN_DELAY_SEC  = 0
MAX_DELAY_SEC  = 0
SKIP_DELAY     = os.environ.get("SKIP_DELAY", "1") == "1"
def myanmar_now() -> str:
    tz = timezone(timedelta(hours=6, minutes=30))
    return datetime.now(tz).strftime("%H:%M %d/%m/%Y")


def in_active_window() -> bool:
    tz = timezone(timedelta(hours=6, minutes=30))
    now = datetime.now(tz)
    return ACTIVE_START <= (now.hour, now.minute) <= ACTIVE_END


def wait_until_target_minute(force: bool = False) -> bool:
    """
    Chờ đến đúng phút :06:00 hoặc :36:00 MMT (Asia/Yangon UTC+6:30).
    - Nếu runner khởi động sớm (:00-:05 hoặc :25-:35 MMT): sleep chính xác số giây còn lại để phát đúng :06:00 hoặc :36:00 MMT.
    - Nếu runner khởi động trễ do GitHub Actions delay (:06-:20 hoặc :36-:50 MMT): CHẠY NGAY LẬP TỨC (0s delay), KHÔNG HỦY BỎ.
    - Chế độ FORCE/MANUAL: Chạy ngay lập tức.
    """
    tz = timezone(timedelta(hours=6, minutes=30))
    now = datetime.now(tz)
    m = now.minute
    s = now.second

    if force:
        print(f"[{myanmar_now()}] ⚡ Chế độ FORCE/MANUAL — Bắt đầu ngay không cần chờ.")
        return True

    print(f"[{myanmar_now()}] ⏱️ Runner khởi động lúc: {now.strftime('%H:%M:%S')} MMT (phút {m}:{s:02d})")

    # 1. Khung nhịp :06 MMT (Cửa sổ chặt: chỉ chấp nhận :00-:10)
    if 0 <= m < 6:
        target_sec = (6 - m) * 60 - s
        print(f"[{myanmar_now()}] ⏳ Khởi động sớm trước mốc :06 MMT — Sleep {target_sec}s...")
        import time
        time.sleep(target_sec)
        print(f"[{myanmar_now()}] 🔔 Đã chạm mốc :06:00 MMT. Bắt đầu gửi lệnh!")
        return True
    elif 6 <= m <= 10:
        print(f"[{myanmar_now()}] 🎯 Trong cửa sổ nhịp :06 MMT (phút {m}). Chạy ngay lập tức!")
        return True

    # 2. Phút :11-:20 → Trễ quá nhịp :06, sleep đến :36
    elif 11 <= m < 21:
        target_sec = (36 - m) * 60 - s
        print(f"[{myanmar_now()}] ⏳ Trễ nhịp :06 — Chuyển hướng sleep {target_sec}s đến :36 MMT...")
        import time
        time.sleep(target_sec)
        print(f"[{myanmar_now()}] 🔔 Đã chạm mốc :36:00 MMT. Bắt đầu gửi lệnh!")
        return True

    # 3. Khung nhịp :36 MMT (Cửa sổ chặt: chỉ chấp nhận :21-:40)
    elif 21 <= m < 36:
        target_sec = (36 - m) * 60 - s
        print(f"[{myanmar_now()}] ⏳ Khởi động sớm trước mốc :36 MMT — Sleep {target_sec}s...")
        import time
        time.sleep(target_sec)
        print(f"[{myanmar_now()}] 🔔 Đã chạm mốc :36:00 MMT. Bắt đầu gửi lệnh!")
        return True
    elif 36 <= m <= 40:
        print(f"[{myanmar_now()}] 🎯 Trong cửa sổ nhịp :36 MMT (phút {m}). Chạy ngay lập tức!")
        return True

    # 4. Phút :41-:59 → Trễ quá nhịp :36, sleep đến :06 giờ kế tiếp
    else:
        target_sec = (60 - m + 6) * 60 - s
        print(f"[{myanmar_now()}] ⏳ Trễ nhịp :36 — Sleep {target_sec}s đến :06 MMT giờ kế tiếp...")
        import time
        time.sleep(target_sec)
        print(f"[{myanmar_now()}] 🔔 Đã chạm mốc :06:00 MMT. Bắt đầu gửi lệnh!")
        return True


async def main():
    force = ("--force" in sys.argv) or (os.environ.get("FORCE_RUN") == "1") or (os.environ.get("MANUAL_RUN") == "1")

    # ── 0. Kiểm tra khung giờ ─────────────────────────────────────
    if not in_active_window() and not force:
        print(f"[{myanmar_now()}] 🌙 Ngoài khung giờ 03:30–22:15. Kết thúc.")
        return

    # ── 1. Chờ đúng phút :06 hoặc :36 MMT ────────────────────────
    if not wait_until_target_minute(force):
        return

    print(f"[{myanmar_now()}] 🚀 Bắt đầu relay Site Down vào nhóm Botlookup...")

    # ── 2. Kết nối Telegram ───────────────────────────────────────
    from telethon.sessions import StringSession
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

    async with client:
        me = await client.get_me()
        print(f"[{myanmar_now()}] Dang nhap: @{me.username} ({me.first_name})")

        # ── 3. Lấy entity nhóm Botlookup trực tiếp (Siêu tốc < 0.2s) ──
        try:
            source = await client.get_entity(SOURCE_GROUP)
            print(f"[{myanmar_now()}] 📌 Nhóm: {source.title}")
        except Exception as e:
            err = f"❌ [{myanmar_now()}] Relay lỗi: không tìm được '{SOURCE_GROUP}': {e}"
            print(err)
            await client.send_message(TARGET_CHAT_ID, err)
            return

        # ── 4+5. Gửi lệnh /down_tni@auto_nocpro_bot vào nhóm Botlookup ─────
        print(f"[{myanmar_now()}] 📤 Gửi lệnh trực tiếp: {COMMAND}")
        await client.send_message(source, COMMAND)
        send_time = datetime.now(timezone.utc) - timedelta(seconds=5)

        # ── 6. Chờ bot phản hồi ───────────────────────────────────
        print(f"[{myanmar_now()}] ⏳ Chờ {WAIT_REPLY_SEC}s...")
        await asyncio.sleep(WAIT_REPLY_SEC)

        # -- 7. Doc lich su Botlookup (newest-first tu API) --
        history = await client(GetHistoryRequest(
            peer=source, limit=50,
            offset_date=None, offset_id=0,
            max_id=0, min_id=0, add_offset=0, hash=0,
        ))

        # -- 8. Thu thap tin sau send_time, sort oldest-first --
        all_after = [msg for msg in history.messages if msg.date >= send_time]
        all_after.sort(key=lambda m: m.date)  # oldest-first = tu tren xuong

        # -- 9. Gom tin bot: tu lenh /down_tni -> dung khi co nguoi khac --
        found_command = False
        bot_messages  = []

        for msg in all_after:
            if not found_command:
                is_mine = (msg.sender_id == me.id) or getattr(msg, 'out', False)
                if is_mine and "/down_tni" in (msg.message or "").lower():
                    found_command = True
                continue

            sender_uname = ""
            if msg.sender_id:
                try:
                    s = await client.get_entity(msg.sender_id)
                    sender_uname = getattr(s, "username", "") or ""
                except Exception:
                    pass

            if sender_uname.lower() == BOT_USERNAME.lower() and msg.message:
                bot_messages.append(msg.message)
                print(f"[{myanmar_now()}] Bot tin #{len(bot_messages)}: {len(msg.message)} ky tu")
            # Không dừng loop khi có tài khoản thứ 2 hoặc người khác gửi tin nhắn — tiếp tục gom đủ tin từ @auto_nocpro_bot

        if not found_command:
            print(f"[{myanmar_now()}] Khong tim thay lenh /down_tni -> fallback: lay tin bot MOI NHAT sau send_time")
            # Fallback: chi lay 1 tin MOI NHAT cua bot (tranh lay nhieu tin tu cac lan relay truoc)
            for msg in reversed(all_after):  # newest-first
                is_mine = (msg.sender_id == me.id) or getattr(msg, 'out', False)
                if is_mine:
                    continue
                s_name = ""
                if msg.sender_id:
                    try:
                        s = await client.get_entity(msg.sender_id)
                        s_name = getattr(s, "username", "") or ""
                    except Exception:
                        pass
                if s_name.lower() == BOT_USERNAME.lower() and msg.message:
                    bot_messages.append(msg.message)
                    print(f"[{myanmar_now()}] Fallback: lay tin moi nhat ({len(msg.message)} ky tu) - dung lai")
                    break  # Chi lay 1 tin moi nhat, khong lay them

        # Smart Retry Stage 2: Nếu chưa có tin nhắn sau WAIT_REPLY_SEC (25s), chờ thêm 10s và quét lại lần 2
        if not bot_messages:
            print(f"[{myanmar_now()}] ⏳ Chưa nhận phản hồi — Chờ thêm 10s (Smart Retry Stage 2)...")
            await asyncio.sleep(10)
            try:
                history2 = await client(GetHistoryRequest(
                    peer=source, limit=50,
                    offset_date=None, offset_id=0,
                    max_id=0, min_id=0, add_offset=0, hash=0,
                ))
                all_after2 = [msg for msg in history2.messages if msg.date >= send_time]
                for msg in reversed(all_after2):
                    s_name = ""
                    if msg.sender_id:
                        try:
                            s = await client.get_entity(msg.sender_id)
                            s_name = getattr(s, "username", "") or ""
                        except Exception: pass
                    if s_name.lower() == BOT_USERNAME.lower() and msg.message:
                        bot_messages.append(msg.message)
                        print(f"[{myanmar_now()}] ✅ Smart Retry thành công! Tìm thấy tin bot ({len(msg.message)} ký tự)")
                        break
            except Exception as retry_ex:
                print(f"[{myanmar_now()}] ⚠️ Smart Retry error: {retry_ex}")

        gas_url = os.environ.get("SD_APPS_SCRIPT_URL") or os.environ.get("APPS_SCRIPT_URL") or ""

        if not bot_messages:
            err = f"[{myanmar_now()}] @{BOT_USERNAME} khong phan hoi trong 35s (Stage 1 + 2)"
            print(err)
            await client.send_message(TARGET_CHAT_ID, err)

        raw_text = "\n".join(bot_messages) if bot_messages else ""

        # 🛡️ LỌC CHỈ LẤY TANINTHARYI REGION — Không lấy tỉnh khác (Ayeyarwady, Sagaing, v.v.)
        # Bot /down_tni trả về nhiều tin cho nhiều region. Chỉ giữ tin chứa "Tanintharyi Region".
        if bot_messages:
            tni_messages = [m for m in bot_messages if "tanintharyi" in m.lower()]
            if tni_messages:
                raw_text = "\n".join(tni_messages)
                print(f"[{myanmar_now()}] 🎯 Lọc Tanintharyi: {len(tni_messages)}/{len(bot_messages)} tin")
            else:
                print(f"[{myanmar_now()}] ⚠️ Không tìm thấy tin Tanintharyi trong {len(bot_messages)} tin bot — bỏ qua!")
                raw_text = ""
        else:
            raw_text = ""

        # ── 9. Gọi GAS webhook → ghi Cột A → checkAndSend() gửi tổng hợp ──
        sent_tin1 = True
        if raw_text and gas_url:
            try:
                resp = requests.post(
                    gas_url,
                    json={"action": "store_site_down", "text": raw_text},
                    timeout=120
                )
                print(f"[{myanmar_now()}] ✅ GAS webhook: {resp.status_code} — {resp.text[:200]}")
                if resp.status_code == 200:
                    try:
                        res_json = resp.json()
                        sent_tin1 = res_json.get("sent_tin1", False)
                        print(f"[{myanmar_now()}] Webhook response sent_tin1: {sent_tin1}")
                    except Exception as json_ex:
                        print(f"[{myanmar_now()}] ⚠️ Lỗi parse JSON webhook response: {json_ex}")
            except Exception as ex:
                print(f"[{myanmar_now()}] ⚠️ GAS webhook lỗi: {ex}")
        elif not raw_text:
            print(f"[{myanmar_now()}] ℹ️ Không có data bot — bỏ qua ghi Cột A")

        # ── 12. Scan nhóm REFUEL — bắt tin Letter Submit/Approved ───
        if REFUEL_GAS_URL:
            try:
                refuel_entity = await client.get_entity(REFUEL_GROUP_ID)
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=35)

                refuel_history = await client(GetHistoryRequest(
                    peer=refuel_entity, limit=50,
                    offset_date=None, offset_id=0, max_id=0,
                    min_id=0, add_offset=0, hash=0
                ))

                for msg in refuel_history.messages:
                    if not msg.message:
                        continue
                    msg_date = msg.date.replace(tzinfo=timezone.utc) if msg.date.tzinfo is None else msg.date
                    if msg_date < cutoff:
                        break
                    txt = msg.message.strip()
                    txt_lower = txt.lower()
                    import re
                    is_letter_submit = bool(re.search(r'^\s*(letter\s*submit|submit\s*letter)\s*[:\-]', txt_lower, re.M) or re.search(r'^\s*(letter\s*submit|submit\s*letter)\b.*\d{1,2}[/\-\.]\d{1,2}', txt_lower, re.M))
                    is_letter_approved = bool(re.search(r'^\s*(approved\s*letter|letter\s*approved)\s*[:\-]', txt_lower, re.M) or re.search(r'^\s*(approved\s*letter|letter\s*approved)\b.*\d{1,2}[/\-\.]\d{1,2}', txt_lower, re.M) or ("government approved" in txt_lower and ":" in txt_lower))
                    if is_letter_submit or is_letter_approved:
                        sender_id = str(msg.sender_id) if msg.sender_id else ""
                        try:
                            sender_entity = await client.get_entity(msg.sender_id)
                            sender_name = getattr(sender_entity, "first_name", "") or sender_id
                        except Exception:
                            sender_name = sender_id
                        resp = requests.post(
                            REFUEL_GAS_URL,
                            json={
                                "action": "collect_message",
                                "group_id": str(REFUEL_GROUP_ID).lstrip("-"),
                                "text": txt,
                                "sender": sender_name,
                                "sender_id": sender_id,
                            },
                            timeout=20,
                            allow_redirects=True,
                        )
                        print(f"[{myanmar_now()}] 📬 Letter collect → {resp.status_code} | {resp.text[:80]}")
            except Exception as ex:
                print(f"[{myanmar_now()}] ⚠️ Letter scan lỗi: {ex}")

        print(f"[{myanmar_now()}] ✅ Xong tất cả.")

if __name__ == "__main__":
    asyncio.run(main())
