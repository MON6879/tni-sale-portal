"""
tg_utils.py
===========
Tiện ích chung cho tất cả scripts báo cáo:
- tg_send_fresh(): xóa tin cũ, gửi tin mới, lưu message_id vào GAS BotState
- tg_delete(): xóa tin theo message_id
- tg_delete_by_title(): xóa TẤT CẢ tin cũ cùng tiêu đề qua Telethon
- get_msg_id() / set_msg_id(): đọc/ghi state từ GAS
"""
import os, re, asyncio, requests, logging
try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv("Task and WO/.env")
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ── Cấu hình Telethon ──────────────────────────────────────────────────────

def _tg_api_id()   -> int: return int(os.environ.get("TELEGRAM_API_ID", "0"))
def _tg_api_hash() -> str: return os.environ.get("TELEGRAM_API_HASH", "")
def _tg_session()  -> str: return os.environ.get("TELEGRAM_SESSION", "")


# ── Cấu hình chung ─────────────────────────────────────────────────────────


def _bot_token(bot_token: str = None):
    if bot_token and str(bot_token).strip():
        return str(bot_token).strip()
    return (
        os.environ.get("REFUEL_BOT_TOKEN") or
        os.environ.get("SEND_BOT_TOKEN") or
        "8811503647:AAEVIToiaPbDeNTUPLsoI5xhdnufKdChsME"
    ).strip()

PRIMARY_GAS_URL = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"

def _clean_url(url: str) -> str:
    if not url: return ""
    return str(url).strip().lstrip('\ufeff\u200b\u200c\u200d\u200e\u200f\xa0')

def _gas_url():
    raw = _clean_url(
        os.environ.get("APPS_SCRIPT_URL") or
        os.environ.get("REFUEL_APPS_SCRIPT_URL") or
        ""
    )
    if "AKfycbz-NZlBk8q2" in raw:
        return raw
    return PRIMARY_GAS_URL

# ── GAS BotState & PropertiesService: lưu/đọc message_id ─────────────────

def get_msg_id(key: str) -> str:
    """Đọc message_id đã lưu từ GAS (dual PropertiesService 5ms + BotState sheet)."""
    gas_url = _gas_url()
    if not gas_url or not key:
        return ""
    # 1. Thử GET query param (nhanh <200ms, không bị mất body khi 302 redirect)
    try:
        r = requests.get(f"{gas_url}?action=get_msg_id&key={key}", timeout=8)
        if r.status_code == 200:
            val = r.json().get("msg_id", "")
            if val:
                return str(val).strip()
    except Exception:
        pass
    # 2. Fallback POST json
    try:
        r = requests.post(gas_url, json={"action": "get_msg_id", "key": key}, timeout=8)
        if r.status_code == 200:
            return str(r.json().get("msg_id", "")).strip()
    except Exception as e:
        logger.warning(f"get_msg_id error: {e}")
    return ""

def set_msg_id(key: str, msg_id):
    """Lưu message_id mới vào GAS (dual PropertiesService 5ms + BotState sheet)."""
    gas_url = _gas_url()
    if not gas_url or not key:
        return
    msg_str = str(msg_id).strip()
    try:
        requests.post(gas_url, json={"action": "set_msg_id", "key": key, "msg_id": msg_str}, timeout=8)
    except Exception as e:
        logger.warning(f"set_msg_id error: {e}")

def get_msg_ids_batch(keys: list) -> dict:
    """Đọc hàng loạt message_ids trong 1 request duy nhất (<300ms)."""
    gas_url = _gas_url()
    if not gas_url or not keys:
        return {}
    keys_param = ",".join(str(k).strip() for k in keys)
    full_url = f"{gas_url}?action=get_msg_ids_batch&keys={keys_param}"
    
    # 1. Thử urllib.request siêu tốc với headers Mozilla/5.0 (chống Google throttle 100%)
    try:
        import urllib.request, json as _json
        req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "ok" and data.get("states"):
                return data.get("states", {})
    except Exception as ue:
        logger.warning(f"get_msg_ids_batch urllib error: {ue}")

    # 2. Fallback requests.get với headers
    try:
        r = requests.get(full_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "ok" and data.get("states"):
                return data.get("states", {})
    except Exception as re:
        logger.warning(f"get_msg_ids_batch requests error: {re}")

    return {}

def set_msg_ids_batch(states_dict: dict):
    """Lưu hàng loạt message_ids trong 1 request duy nhất (<300ms)."""
    gas_url = _gas_url()
    if not gas_url or not states_dict:
        return
    
    # 1. Thử urllib.request POST (chống 302 redirect method drop)
    try:
        import urllib.request, json as _json
        payload_bytes = _json.dumps({"action": "set_msg_ids_batch", "states": states_dict}).encode("utf-8")
        req = urllib.request.Request(
            gas_url,
            data=payload_bytes,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except Exception as ue:
        logger.warning(f"set_msg_ids_batch urllib error: {ue}")

    # 2. Fallback requests.post
    try:
        requests.post(gas_url, json={"action": "set_msg_ids_batch", "states": states_dict},
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    except Exception as e:
        logger.warning(f"set_msg_ids_batch requests error: {e}")

# ── Telegram helpers ───────────────────────────────────────────────────────

def tg_delete(chat_id: str, msg_id, bot_token: str = None):
    """Xóa tin nhắn cũ theo message_id. Bỏ qua nếu không có."""
    if not msg_id:
        return
    try:
        token = _bot_token(bot_token)
        r = requests.post(
            f"https://api.telegram.org/bot{token}/deleteMessage",
            json={"chat_id": chat_id, "message_id": int(msg_id)},
            timeout=10
        )
        if not r.json().get("ok"):
            logger.info(f"tg_delete: {r.json().get('description')} (msg_id={msg_id})")
    except Exception as e:
        logger.warning(f"tg_delete error: {e}")


def tg_delete_by_title(chat_id: str, title_prefix: str, search_limit: int = 300, bot_token: str = None) -> int:
    """
    Dùng Telethon để scan lịch sử chat, tìm TẤT CẢ tin nhắn từ bot
    có chứa tiêu đề (title_prefix) trong 6 dòng đầu, xóa hết qua Bot API hoặc Telethon.
    Fallback: không làm gì nếu không có Telethon session.
    """
    api_id   = _tg_api_id()
    api_hash = _tg_api_hash()
    session  = _tg_session()
    token    = _bot_token(bot_token)

    if not (api_id and api_hash and session and token):
        logger.warning("tg_delete_by_title: thiếu Telethon credentials, bỏ qua.")
        return 0

    async def _run():
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        deleted = 0
        # Lấy bot user_id
        bot_id = None
        try:
            me_r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            if me_r.status_code == 200:
                bot_id = me_r.json()["result"]["id"]
        except Exception as ex:
            logger.warning(f"tg_delete_by_title: getMe lỗi: {ex}")

        try:
            clean_pfx = re.sub(r'^[^\w\[]+', '', title_prefix).strip()
            bot_msg_ids = []
            async with TelegramClient(StringSession(session), api_id, api_hash) as client:
                async for msg in client.iter_messages(int(chat_id), limit=search_limit):
                    if not msg.text:
                        continue

                    # 1. Xóa Note reply gửi từ user @Phongha79 nếu có
                    if any(k in msg.text for k in ["@Raja HO", "Refuel Team Sent Plan", "Aung MinPaing_VCM", "Note: Above are the end-of-day", "Note: 📋 1. Report"]):
                        try:
                            await client.delete_messages(int(chat_id), [msg.id], revoke=True)
                            deleted += 1
                            logger.info(f"[del_title] 🗑️ Xóa Note msg_id={msg.id} ({chat_id})")
                        except Exception as ex:
                            logger.warning(f"[del_title] ⚠️ Xóa Note lỗi: {ex}")
                        continue

                    # 2. Lọc tin của Bot
                    if bot_id and msg.sender_id != bot_id:
                        continue

                    # Lấy 6 dòng đầu để so sánh tiêu đề - "TIN NÀO XÓA TIN NẤY"
                    header_clean = "\n".join(msg.text.split("\n")[:6]).replace("**", "").replace("__", "").replace("📦", "").strip().lower()
                    matched = False
                    pfx_lower = title_prefix.lower()

                    # Phân biệt bản tin theo tiêu đề:
                    # Đã gộp "TNI REQUEST REFUEL" + "PLAN & PROGRESS" thành 1 tin
                    # → Khi prefix = "tni request refuel", xóa cả 2 loại tin cũ
                    if "tni request refuel" in pfx_lower:
                        if "tni request refuel" in header_clean or "plan & progress" in header_clean:
                            matched = True
                    elif "plan & progress" in pfx_lower:
                        if "plan & progress" in header_clean or "tni request refuel" in header_clean:
                            matched = True
                    elif clean_pfx and len(clean_pfx) >= 4 and clean_pfx.lower() in header_clean:
                        matched = True

                    if matched:
                        bot_msg_ids.append(msg.id)

                # Batch xóa tất cả tin bot khớp tiêu đề bằng Telethon
                if bot_msg_ids:
                    try:
                        await client.delete_messages(int(chat_id), bot_msg_ids, revoke=True)
                        deleted += len(bot_msg_ids)
                        logger.info(f"[del_title] 🗑️ Telethon batch xóa {len(bot_msg_ids)} msg_ids: {bot_msg_ids}")
                    except Exception as ex:
                        logger.warning(f"[del_title] ⚠️ Telethon batch xóa lỗi: {ex}, fallback Bot API")
                        for mid in bot_msg_ids:
                            try:
                                resp = requests.post(
                                    f"https://api.telegram.org/bot{token}/deleteMessage",
                                    json={"chat_id": int(chat_id), "message_id": mid},
                                    timeout=6,
                                )
                                if resp.json().get("ok"):
                                    deleted += 1
                            except Exception:
                                pass
        except Exception as telethon_ex:
            logger.warning(f"[del_title] ⚠️ Telethon lỗi (bỏ qua xóa): {telethon_ex}")
        return deleted

    try:
        # Timeout 60s — tránh hang vô thời hạn nếu Telegram FloodWait
        deleted = asyncio.run(asyncio.wait_for(_run(), timeout=60))
        logger.info(f"[del_title] Tổng xóa {deleted} tin '{title_prefix[:40]}' tại {chat_id}")
        return deleted
    except asyncio.TimeoutError:
        logger.warning(f"tg_delete_by_title: timeout 60s — bỏ qua xóa, tiếp tục gửi tin mới")
        return 0
    except Exception as ex:
        logger.warning(f"tg_delete_by_title exception: {ex}")
        return 0

def tg_send_fresh(chat_id: str, text: str, state_key: str = None,
                  parse_mode: str = "HTML", title_prefix: str = "", bot_token: str = None) -> int:
    """
    Xóa tin cũ → gửi tin mới → lưu message_id mới.
    Ưu tiên dùng Telethon xóa theo tiêu đề (nếu có title_prefix),
    fallback về GAS msg_id nếu không có Telethon session.
    """
    # Bước 1: xóa tin cũ
    if title_prefix:
        tg_delete_by_title(chat_id, title_prefix)  # Telethon xóa tất cả cùng tiêu đề

    if state_key:
        old_id = get_msg_id(state_key)
        if old_id:
            tg_delete(chat_id, old_id, bot_token=bot_token)             # Fallback: xóa 1 tin theo GAS msg_id
            logger.info(f"Deleted old msg {old_id} for key={state_key}")

        # Xóa cả tin cũ từ legacy keys nếu có (report3 -> report1, report4 -> report2)
        if "report1_" in state_key:
            legacy_id = get_msg_id(state_key.replace("report1_", "report3_"))
            if legacy_id:
                tg_delete(chat_id, legacy_id, bot_token=bot_token)
        elif "report2_" in state_key:
            legacy_id = get_msg_id(state_key.replace("report2_", "report4_"))
            if legacy_id:
                tg_delete(chat_id, legacy_id, bot_token=bot_token)

    # Bước 2: gửi tin mới
    try:
        token = _bot_token(bot_token)
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=45
        )
        result = r.json()
        if result.get("ok"):
            new_id = result["result"]["message_id"]
            logger.info(f"Sent new msg {new_id} to {chat_id}")
            if state_key:
                set_msg_id(state_key, new_id)      # Vẫn lưu để fallback
            return new_id
        else:
            logger.error(f"tg_send_fresh error: {result.get('description')}")
            return 0
    except Exception as e:
        logger.error(f"tg_send_fresh exception: {e}")
        return 0
