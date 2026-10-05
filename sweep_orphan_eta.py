# -*- coding: utf-8 -*-
# sweep_orphan_eta.py — Sweep tin ETA mồ côi + Site Down Alarm cũ (PM-59 & PM-71 fix)
import os, asyncio, re, json, time
from dotenv import load_dotenv
load_dotenv('Task and WO/.env')
from telethon import TelegramClient
from telethon.sessions import StringSession

api_id    = int(os.getenv('TELEGRAM_API_ID', '0'))
api_hash  = os.getenv('TELEGRAM_API_HASH', '')
session_str = os.getenv('TELEGRAM_SESSION', '')
GAS_URL   = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"

GROUPS = {
    'T1': -1004215695747,
    'T2': -1004480845549,
    'T3': -1004369170658,
    'T4': -1004293741999,
}

BOT_2D_NAME   = "2. TNI Auto Report Daily"
# Bot 5T gửi Site Down Alarm — nhận diện qua user_id, username hoặc keywords
BOT_5T_ID     = 8647102342
BOT_5T_NAMES  = ["5 tni_site_down", "5t", "tni_site_down_cell_alarm", "5 tni_site", "5. tni"]
SD_CONTENT_KEYS = [
    "Total Site down",
    "HUB site TNI",
    "Dont Forget",
    "SUMMARY — Team",
    "TNI_SITE_DOWN",
    "TNI_SITE_DOWN_CELL_ALARM",
]


async def execute_clean():
    newest_states_to_save = {}
    total_deleted = 0

    async with TelegramClient(StringSession(session_str), api_id, api_hash) as client:
        for t_name, chat_id in GROUPS.items():
            print(f"\n==================== {t_name} ({chat_id}) ====================")
            eta_by_subteam = {}
            site_down_msgs = []  # Gom message objects Site Down để xử lý theo batch

            async for msg in client.iter_messages(chat_id, limit=150):
                if not msg.text:
                    continue
                sender      = await msg.get_sender()
                sender_name = (getattr(sender, 'first_name', '') or
                               getattr(sender, 'title', '') or '').lower()
                username    = (getattr(sender, 'username', '') or '').lower()
                sender_id   = getattr(sender, 'id', 0)

                # Bỏ qua tin nhắn cá nhân của Admin
                if sender_id == 6859790680:
                    continue

                # ── Bot 2D: ETA Update ─────────────────────────────────
                if BOT_2D_NAME.lower() in sender_name:
                    first_line = msg.text.strip().split('\n')[0]
                    if "ETA Update" in first_line:
                        m = re.search(r"📋\s*(T\d+(?:\s*S\d+)?)\s*—\s*ETA Update", first_line)
                        subteam = m.group(1) if m else t_name
                        eta_by_subteam.setdefault(subteam, []).append(msg.id)
                    continue  # Không kiểm tra tiếp là 5T

                # ── Bot 5T: Site Down Alarm (Bọc thép nhận diện ID, username, title, content) ──
                is_5t = (
                    sender_id == BOT_5T_ID or
                    "tni_site_down" in username or
                    any(kw in sender_name for kw in BOT_5T_NAMES) or
                    any(kw in (msg.text or '') for kw in SD_CONTENT_KEYS)
                )

                if is_5t:
                    site_down_msgs.append(msg)

            # ── Xử lý ETA orphans (giữ 1 mới nhất / subteam) ──────────
            for subteam, msg_ids in eta_by_subteam.items():
                newest_id  = msg_ids[0]
                orphan_ids = msg_ids[1:]
                state_key  = f"eta_reminder_{subteam.replace(' ', '_')}"
                newest_states_to_save[state_key] = str(newest_id)
                print(f"[{subteam}] ETA: giữ ID={newest_id}, xóa {len(orphan_ids)} orphan")
                if orphan_ids:
                    try:
                        await client.delete_messages(chat_id, orphan_ids, revoke=True)
                        total_deleted += len(orphan_ids)
                        print(f"[{subteam}] ✅ Đã xóa {len(orphan_ids)} tin ETA cũ")
                    except Exception as e:
                        print(f"[{subteam}] ❌ ETA delete error: {e}")

            # ── Xử lý Site Down: Gom cụm theo batch mới nhất (cửa sổ 120s) ───
            if site_down_msgs:
                newest_date   = site_down_msgs[0].date
                current_batch = []
                orphan_sd_ids = []
                seen_texts    = set()

                for m in site_down_msgs:
                    age_from_newest = (newest_date - m.date).total_seconds()
                    if age_from_newest <= 120:
                        # Nằm trong đợt gửi mới nhất (Batch Window 120 giây)
                        sig = m.text.strip()[:80]
                        if sig in seen_texts:
                            # Trùng lặp chunk trong cùng batch -> đưa vào danh sách xóa
                            print(f"[{t_name}] ⚠️ Site Down duplicate cùng batch ID={m.id} -> orphan")
                            orphan_sd_ids.append(m.id)
                        else:
                            seen_texts.add(sig)
                            current_batch.append(m.id)
                    else:
                        # Thuộc các đợt phát trước đó (> 120s) -> chắc chắn là tin mồ côi cũ
                        orphan_sd_ids.append(m.id)

                print(f"[{t_name}] Site Down: giữ batch mới nhất ({len(current_batch)} tin: {current_batch}), xóa {len(orphan_sd_ids)} tin cũ")
                if orphan_sd_ids:
                    for i in range(0, len(orphan_sd_ids), 50):
                        chunk = orphan_sd_ids[i:i+50]
                        try:
                            await client.delete_messages(chat_id, chunk, revoke=True)
                            total_deleted += len(chunk)
                            print(f"[{t_name}] ✅ Đã xóa {len(chunk)} Site Down cũ (revoke=True)")
                        except Exception as e:
                            print(f"[{t_name}] ❌ Site Down delete error: {e}")

    # ── Lưu newest ETA IDs lên GAS ────────────────────────────────────
    print(f"\n==================== SAVING TO GAS ====================")
    print("Newest states:", newest_states_to_save)
    if newest_states_to_save:
        payload = json.dumps({"action": "set_msg_ids_batch", "states": newest_states_to_save}).encode("utf-8")
        import urllib.request
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    GAS_URL, data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    print(f"GAS response (attempt {attempt+1}):", resp.read().decode("utf-8")[:200])
                    break
            except Exception as ge:
                print(f"GAS save attempt {attempt+1} warning: {ge}")
                time.sleep(1)

    print(f"\n🎉 DONE! Xóa tổng {total_deleted} tin cũ (ETA + Site Down Alarm). Giữ 1 tin mới nhất mỗi loại mỗi nhóm!")

asyncio.run(execute_clean())
