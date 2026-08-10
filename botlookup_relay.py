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
from datetime import datetime, timezone, timedelta

from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest

# ── Cấu hình ──────────────────────────────────────────────────────
API_ID         = int(os.environ["TELEGRAM_API_ID"])
API_HASH       = os.environ["TELEGRAM_API_HASH"]
SESSION_STRING = os.environ["TELEGRAM_SESSION"]

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
# ──────────────────────────────────────────────────────────────────

def myanmar_now() -> str:
    tz = timezone(timedelta(hours=6, minutes=30))
    return datetime.now(tz).strftime("%H:%M %d/%m/%Y")


def in_active_window() -> bool:
    tz  = timezone(timedelta(hours=6, minutes=30))
    now = datetime.now(tz)
    return ACTIVE_START <= (now.hour, now.minute) <= ACTIVE_END


def split_message(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        cut = text.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return parts


async def main():
    # ── 0. Kiểm tra khung giờ ────────────────────────────────────
    if not in_active_window():
        print(f"[{myanmar_now()}] 🌙 Ngoài khung giờ 04:30–21:30. Kết thúc.")
        return

    # ── 2. Kết nối Telegram ───────────────────────────────────────
    from telethon.sessions import StringSession
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

    async with client:
        me = await client.get_me()
        print(f"[{myanmar_now()}] Dang nhap: @{me.username} ({me.first_name})")

        # Build entity map tu tat ca dialogs
        print(f"[{myanmar_now()}] Building entity map from dialogs...")
        entity_map = {}  # gname -> entity
        dialogs = await client.get_dialogs(limit=200)
        for dialog in dialogs:
            did = str(getattr(dialog.entity, 'id', 0))
            for gname, gid in ALL_GROUPS.items():
                if did == str(abs(int(gid))):
                    entity_map[gname] = dialog.entity
                    print(f"[{myanmar_now()}] Found {gname}: {dialog.title}")
        print(f"[{myanmar_now()}] Entity map: {list(entity_map.keys())}")

        # ── 3. Lấy entity nhóm Botlookup ─────────────────────────
        try:
            source = await client.get_entity(SOURCE_GROUP)
            print(f"[{myanmar_now()}] 📌 Nhóm: {source.title}")
        except Exception as e:
            err = f"❌ [{myanmar_now()}] Relay lỗi: không tìm được '{SOURCE_GROUP}': {e}"
            print(err)
            await client.send_message(TARGET_CHAT_ID, err)
            return

        # ── 3.5. PRE-CHECK BẢO VỆ NHÓM (Circuit Breaker 100% Exact) ───────
        # Kể từ 3 tin nhắn gửi lệnh /down_ gần nhất của bất kỳ ai trong nhóm:
        # Nếu cả 3 lệnh gần nhất đều KHÔNG CÓ BẤT KỲ tin trả lời nào chứa "Auto Report NocPro",
        # và từ thời điểm đó đến nay chưa có tin "Auto Report NocPro" xuất hiện -> TẠM DỪNG GỬI MỚI!
        # Chỉ khi quét thấy có tin "Auto Report NocPro" xuất hiện trở lại -> Mới gửi lệnh cào dữ liệu!
        try:
            pre_history = await client(GetHistoryRequest(
                peer=source, limit=60,
                offset_date=None, offset_id=0, max_id=0, min_id=0, add_offset=0, hash=0
            ))
            
            # Lấy tất cả tin nhắn dạng lệnh /down_ và tất cả tin nhắn chứa Auto Report NocPro (xếp từ cũ -> mới)
            messages = list(reversed(pre_history.messages))
            
            down_cmds = []
            auto_reports = []

            for msg in messages:
                txt = (msg.message or "").lower()
                if "/down_" in txt or "auto_nocpro_bot" in txt:
                    down_cmds.append(msg)
                if "auto report nocpro" in txt or "site down" in txt or "auto-generated report" in txt or "nocpro" in txt:
                    auto_reports.append(msg)

            # Lấy 3 lệnh /down_ gần đây nhất trong nhóm
            if len(down_cmds) >= 3:
                last_3_cmds = down_cmds[-3:]
                third_last_cmd_date = last_3_cmds[0].date
                
                # Có bất kỳ tin "Auto Report NocPro" nào xuất hiện từ sau lệnh thứ 3 gần nhất không?
                has_nocpro_reply_after = any(r.date >= third_last_cmd_date for r in auto_reports)

                print(f"[{myanmar_now()}] 🔍 Pre-check: Lấy 3 lệnh /down_ gần nhất ({len(down_cmds)} tổng cộng) | Phản hồi 'Auto Report NocPro' sau lệnh thứ 3: {'Có' if has_nocpro_reply_after else 'Không'}")

                if not has_nocpro_reply_after:
                    print(f"[{myanmar_now()}] ⚠️ Bot công ty đang LỖI (kể từ 3 lệnh /down_ gần nhất chưa có tin 'Auto Report NocPro' xuất hiện). BỎ QUA GỬI MỚI để không làm loãng nhóm!")
                    return
                else:
                    print(f"[{myanmar_now()}] 🟢 Đã có tin 'Auto Report NocPro'! Bot công ty đã sửa xong. Tiếp tục gửi lệnh cào dữ liệu...")
        except Exception as pre_ex:
            print(f"[{myanmar_now()}] ⚠️ Pre-check error (vẫn tiếp tục): {pre_ex}")

        # ── 4+5. Gui lenh va ghi nho thoi diem SAU khi gui ─────
        print(f"[{myanmar_now()}] 📤 Gửi: {COMMAND}")
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
            else:
                if msg.sender_id != me.id:
                    print(f"[{myanmar_now()}] STOP: nguoi khac gui (sender_id={msg.sender_id})")
                    break

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

        gas_url = os.environ.get("SD_APPS_SCRIPT_URL") or os.environ.get("APPS_SCRIPT_URL") or ""

        if not bot_messages:
            err = f"[{myanmar_now()}] @{BOT_USERNAME} khong phan hoi trong {WAIT_REPLY_SEC}s"
            print(err)
            await client.send_message(TARGET_CHAT_ID, err)

        raw_text = "\n".join(bot_messages) if bot_messages else ""

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
                    if ("letter" in txt_lower and "submit" in txt_lower) or \
                       ("government approved" in txt_lower) or \
                       ("approved the letter" in txt_lower):
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
