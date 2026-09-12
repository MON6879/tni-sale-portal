# -*- coding: utf-8 -*-
import os, asyncio, re, requests, json
from dotenv import load_dotenv
load_dotenv('Task and WO/.env')
from telethon import TelegramClient
from telethon.sessions import StringSession

api_id = int(os.getenv('TELEGRAM_API_ID', '0'))
api_hash = os.getenv('TELEGRAM_API_HASH', '')
session_str = os.getenv('TELEGRAM_SESSION', '')
GAS_URL = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"

GROUPS = {
    'T1': -1004215695747,
    'T2': -1004480845549,
    'T3': -1004369170658,
    'T4': -1004293741999
}

BOT_2D_NAME = "2. TNI Auto Report Daily"

async def execute_clean():
    newest_states_to_save = {}
    total_deleted = 0

    async with TelegramClient(StringSession(session_str), api_id, api_hash) as client:
        for t_name, chat_id in GROUPS.items():
            print(f"\n==================== {t_name} ({chat_id}) ====================")
            eta_by_subteam = {}

            async for msg in client.iter_messages(chat_id, limit=60):
                if not msg.text:
                    continue
                sender = await msg.get_sender()
                sender_name = getattr(sender, 'first_name', '') or getattr(sender, 'title', '')
                
                # We ONLY touch messages sent by Bot 2D
                if BOT_2D_NAME not in sender_name:
                    continue

                first_line = msg.text.strip().split('\n')[0]
                
                # Strictly check for ETA Update in first line
                if "ETA Update" in first_line:
                    m = re.search(r"📋\s*(T\d+(?:\s*S\d+)?)\s*—\s*ETA Update", first_line)
                    subteam = m.group(1) if m else t_name
                    if subteam not in eta_by_subteam:
                        eta_by_subteam[subteam] = []
                    eta_by_subteam[subteam].append(msg.id)

            for subteam, msg_ids in eta_by_subteam.items():
                # msg_ids is in descending order (newest first)
                newest_id = msg_ids[0]
                orphan_ids = msg_ids[1:]
                
                state_key = f"eta_reminder_{subteam.replace(' ', '_')}"
                newest_states_to_save[state_key] = str(newest_id)
                
                print(f"[{subteam}] Keeping newest: ID {newest_id}")
                if orphan_ids:
                    print(f"[{subteam}] Deleting {len(orphan_ids)} orphan ETA messages: {orphan_ids}")
                    try:
                        await client.delete_messages(chat_id, orphan_ids, revoke=True)
                        total_deleted += len(orphan_ids)
                        print(f"[{subteam}] ✅ Deleted {len(orphan_ids)} messages successfully")
                    except Exception as e:
                        print(f"[{subteam}] ❌ Delete error: {e}")

    # Now update GAS with all the newest IDs
    print(f"\n==================== SAVING TO GAS ====================")
    print("Newest states to save in GAS:", newest_states_to_save)
    if newest_states_to_save:
        import urllib.request, time
        payload = json.dumps({"action": "set_msg_ids_batch", "states": newest_states_to_save}).encode("utf-8")
        for attempt in range(3):
            try:
                req = urllib.request.Request(GAS_URL, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    print(f"GAS response (attempt {attempt+1}):", resp.read().decode("utf-8")[:200])
                    break
            except Exception as ge:
                print(f"GAS save attempt {attempt+1} warning: {ge}")
                time.sleep(1)

    print(f"\n🎉 DONE! Cleaned total {total_deleted} orphan ETA messages. Kept only the single latest ETA message per subteam!")

asyncio.run(execute_clean())
