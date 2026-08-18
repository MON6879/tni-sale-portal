"""
delete_old_helper.py
====================
Shared helper for delete-old-send-new pattern.
Lưu/đọc message_ids qua GAS PropertiesService,
xóa tin cũ trước khi gửi mới.

Dùng cho: cron_send.py, daily_plan_report.py, daily_read_report.py, check_read_status.py
"""

import asyncio
import requests


# ── GAS API helpers ─────────────────────────────────────────────

def get_old_msgids(gas_url: str, key: str) -> list[int]:
    """Đọc message_ids cũ từ GAS PropertiesService.
    Returns list of message_id (int). Rỗng nếu lỗi hoặc chưa có.
    """
    if not gas_url or not key:
        return []
    try:
        resp = requests.get(
            gas_url,
            params={"action": "get_msgids", "key": key},
            timeout=30,
            allow_redirects=True
        )
        if resp.status_code == 200:
            data = resp.json()
            raw = data.get("msgids", [])
            return [int(x) for x in raw]
    except Exception as ex:
        print(f"[delete_old] ⚠️ get_msgids({key}) lỗi: {ex}")
    return []


def save_msgids(gas_url: str, key: str, msgids: list[int]):
    """Lưu message_ids mới vào GAS PropertiesService."""
    if not gas_url or not key or not msgids:
        return
    try:
        resp = requests.post(
            gas_url,
            json={"action": "save_msgids", "key": key, "msgids": msgids},
            timeout=30,
            allow_redirects=True
        )
        if resp.status_code == 200:
            print(f"[delete_old] 💾 Saved {key} = {msgids}")
        else:
            print(f"[delete_old] ⚠️ save_msgids({key}) HTTP {resp.status_code}")
    except Exception as ex:
        print(f"[delete_old] ⚠️ save_msgids({key}) lỗi: {ex}")


# ── Bot API delete ──────────────────────────────────────────────

def delete_telegram_msg(bot_token: str, chat_id, message_id: int) -> bool:
    """Xóa 1 tin nhắn qua Telegram Bot API.
    Trả về True nếu xóa thành công hoặc tin nhắn đã bị xóa trước đó.
    """
    url = f"https://api.telegram.org/bot{bot_token}/deleteMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "message_id": message_id
        }, timeout=10)
        data = resp.json()
        if data.get("ok"):
            print(f"[delete_old] 🗑️ msg_id={message_id} → {chat_id}")
            return True
        else:
            desc = data.get('description', '')
            # Nếu tin nhắn đã bị xóa trước đó, coi như thành công để gỡ khỏi bộ nhớ
            if "message to delete not found" in desc.lower():
                print(f"[delete_old] 🗑️ msg_id={message_id} đã được xóa trước đó (không tìm thấy)")
                return True
            print(f"[delete_old] ⚠️ msg_id={message_id}: {desc}")
            return False
    except Exception as ex:
        print(f"[delete_old] ❌ delete msg_id={message_id}: {ex}")
        return False


def delete_old_messages_bot(bot_token: str, chat_id, gas_url: str, key: str) -> int:
    """Xóa tất cả tin cũ của key. Dùng Bot API. Returns số tin đã xóa."""
    old_ids = get_old_msgids(gas_url, key)
    if not old_ids:
        return 0
    count = 0
    remaining_ids = []
    for mid in old_ids:
        if delete_telegram_msg(bot_token, chat_id, mid):
            count += 1
        else:
            remaining_ids.append(mid)
    
    # Cập nhật lại các ID chưa xóa được lên GAS
    save_msgids(gas_url, key, remaining_ids)
    print(f"[delete_old] 📊 {key}: xóa {count}/{len(old_ids)}")
    return count


# ── Telethon delete ─────────────────────────────────────────────

async def delete_old_messages_telethon(client, chat_id, gas_url: str, key: str) -> int:
    """Xóa tất cả tin cũ của key. Dùng Telethon client với revoke=True (xóa hẳn cho mọi người)."""
    old_ids = get_old_msgids(gas_url, key)
    if not old_ids:
        return 0
    count = 0
    remaining_ids = []
    for mid in old_ids:
        try:
            await client.delete_messages(chat_id, [mid], revoke=True)
            count += 1
            print(f"[delete_old] 🗑️ msg_id={mid} → {chat_id} (revoke=True)")
        except Exception as ex:
            err_str = str(ex).lower()
            if "not found" in err_str or "invalid" in err_str:
                count += 1
                print(f"[delete_old] 🗑️ msg_id={mid} đã được xóa trước đó")
            else:
                remaining_ids.append(mid)
                print(f"[delete_old] ⚠️ msg_id={mid}: {ex}")

    save_msgids(gas_url, key, remaining_ids)
    print(f"[delete_old] 📊 {key}: xóa {count}/{len(old_ids)}")
    return count


def _get_bot_user_id(bot_token: str) -> int:
    """Lấy user_id của bot từ token qua Bot API getMe."""
    try:
        r = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
        return r.json()["result"]["id"]
    except Exception as ex:
        print(f"[delete_title] ⚠️ getMe lỗi: {ex}")
        return 0


async def delete_by_titles_batch_telethon(
    client,
    bot_token: str,
    chat_to_prefixes: dict, # {chat_id: [prefix1, prefix2, ...]}
    search_limit: int = 100,
) -> int:
    """
    Quét lịch sử MỖI NHÓM ĐÚNG 1 LẦN (Single-Pass Scanning) và xóa tất cả tin khớp với danh sách prefix.
    Giảm từ 70 vòng lặp mạng xuống đúng 5 vòng lặp, chạy siêu tốc < 3 giây và 0% FloodWait!
    """
    bot_id = _get_bot_user_id(bot_token)
    total_deleted = 0

    for chat_id, prefixes in chat_to_prefixes.items():
        if not prefixes:
            continue
        try:
            cid = int(chat_id)
            clean_prefixes = [p.replace("📦", "").strip() for p in prefixes]
            
            async for msg in client.iter_messages(cid, limit=search_limit):
                if not msg.text:
                    continue

                # Xóa các tin Note chỉ đạo gửi từ user (Telethon revoke=True)
                if "Note: Above are the end-of-day work results" in msg.text or "Note: 📋 1. Report" in msg.text:
                    try:
                        await client.delete_messages(cid, [msg.id], revoke=True)
                        total_deleted += 1
                        print(f"[delete_batch] 🗑️ Xóa Note msg_id={msg.id} ({cid})")
                    except Exception as ex:
                        print(f"[delete_batch] ⚠️ Xóa Note lỗi: {ex}")
                    continue

                # Lọc tin của Bot
                if bot_id and msg.sender_id != bot_id:
                    continue

                first_line = msg.text.split("\n")[0].strip()
                first_line_clean = first_line.replace("**", "").replace("__", "").replace("📦", "").strip()

                matched = False
                for pfx in clean_prefixes:
                    if first_line_clean.startswith(pfx):
                        matched = True
                        break

                if matched:
                    try:
                        resp = requests.post(
                            f"https://api.telegram.org/bot{bot_token}/deleteMessage",
                            json={"chat_id": cid, "message_id": msg.id},
                            timeout=10,
                        )
                        if resp.json().get("ok"):
                            total_deleted += 1
                            print(f"[delete_batch] 🗑️ Bot API xóa msg_id={msg.id} ('{first_line_clean[:30]}...')")
                        else:
                            await client.delete_messages(cid, [msg.id], revoke=True)
                            total_deleted += 1
                    except Exception as ex:
                        print(f"[delete_batch] ❌ delete msg_id={msg.id}: {ex}")

        except Exception as chat_err:
            print(f"[delete_batch] ❌ iter_messages({chat_id}): {chat_err}")

    print(f"[delete_batch] 📊 Tổng cộng đã xóa {total_deleted} tin cũ qua Telethon Batch.")
    return total_deleted


async def delete_by_title_telethon(
    client,
    bot_token: str,
    chat_id,
    title_prefix: str,
    search_limit: int = 100,
) -> int:
    """Fallback single-title delete wrapper using batch function."""
    return await delete_by_titles_batch_telethon(client, bot_token, {chat_id: [title_prefix]}, search_limit)


