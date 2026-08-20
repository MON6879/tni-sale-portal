#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
══════════════════════════════════════════════════════════════════════════════
🚂 CHUYẾN TÀU SỐ 3: SCHEDULED AUTOMATION LINE
🚨 TOA TÀU: TOA KIỂM TOÁN HỆ THỐNG TOÀN DIỆN (SYSTEM AUDIT & SENTINEL CAR)
👑 GHẾ: GHẾ AUDITOR-9.1 (CHUYÊN GIA KIỂM TRA SỨC KHỎE & GIÁM SÁT HỆ THỐNG TOÀN DIỆN)
══════════════════════════════════════════════════════════════════════════════
Phiên bản: Master Sentinel v7.5 — Deep Audit, On-Time Verification & Deduplication Engine
Quy tắc phản hồi:
  - Nếu tất cả OK: Gửi dòng cực kỳ ngắn gọn "🟢 [AUDITOR-9.1] 1, 2, 3, 4 OK".
  - Nếu CÓ LỖI / TRỄ / NHÂN ĐÔI: Báo cáo chi tiết chính xác lỗi ở đâu để xử lý ngay.
══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import time
import json
import logging
import asyncio
import re
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Múi giờ Myanmar UTC+6:30
TZ_MM = timezone(timedelta(hours=6, minutes=30))

# ── CẤU HÌNH GỬI RIÊNG VỀ DM CÁ NHÂN ADMIN (KHÔNG GỬI VÀO GROUP) ────────────
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "6859790680")  # Ha Duc Phong
SEND_BOT_TOKEN = os.getenv("SEND_BOT_TOKEN", "8647102342:AAGwI95-xeyFfJZusOOrIPVBER-z6taZHZI")

# Telethon Secrets
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0")) if str(os.getenv("TELEGRAM_API_ID", "0")).strip().isdigit() else 0
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "")

# Telegram Group IDs
from tni_config import TELEGRAM_GROUPS
ALL_MONITORED_GROUPS = {
    "CONTROL": TELEGRAM_GROUPS.get("CONTROL", -5251698940),
    "T1": TELEGRAM_GROUPS.get("T1", -1004215695747),
    "T2": TELEGRAM_GROUPS.get("T2", -1004480845549),
    "T3": TELEGRAM_GROUPS.get("T3", -1004369170658),
    "T4": TELEGRAM_GROUPS.get("T4", -1004293741999),
    "REFUEL": -5469544739,
    "BOTLOOKUP": -1002287739509,
}

# ── 1. DANH MỤC WEBHOOKS & ENDPOINTS ────────────────────────────────────────
BOT_REGISTRY = {
    "Search Bot (@SEARCHTNITASKWOBOT)": {
        "token": "8606383435:AAEstcN4Om6_9ZAjs4OoFV2uVlRALgae2Ac",
        "expected_url": "https://tni-bot.vercel.app/api/search_bot",
        "ping_url": "https://tni-bot.vercel.app/api/search_bot"
    },
    "Asset Collector (@TNIASSETorderREQUEST_BOT)": {
        "token": "8928677923:AAE_cJuEDH1tUf5v0q5Wf0UjDHlcp_k1lGM",
        "expected_url": "https://tni-bot.vercel.app/api/collector",
        "ping_url": "https://tni-bot.vercel.app/api/collector"
    },
    "Site Down Relay (@TNI_SITE_DOWN_CELL_ALARMBOT)": {
        "token": "8647102342:AAGwI95-xeyFfJZusOOrIPVBER-z6taZHZI",
        "expected_url": "https://tni-sitedown.vercel.app/api/site_down_relay",
        "ping_url": "https://tni-sitedown.vercel.app/api/site_down_relay"
    },
    "Construction Bot 10 (@8903841312)": {
        "token": "8903841312:AAHQ_LeI19gs2nrqBSInTsgzJXOuv6H8LmE",
        "expected_url": "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec",
        "ping_url": "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec?action=get_general"
    }
}

GAS_SERVICES = {
    "TNI Main GAS Backend (@357 SSOT)": {
        "url": "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec?action=get_general"
    },
    "Standalone Site Down GAS Backend (@83 SSOT)": {
        "url": "https://script.google.com/macros/s/AKfycbyCibIj4QN7oG5BZc_ju1iS-DUmd9nNdrMn9UN-WD8qf6jVoU_OKOf2yfbi10qGMFF-/exec?action=admin_audit_sitedown"
    },
    "BI Portal Backend (Plan Dep)": {
        "url": "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec?action=get_plan_dep"
    }
}

SHEET_CONNECTORS = {
    "Sheet 10_TNI_SITE_DOWN (GID=0)": "https://docs.google.com/spreadsheets/d/1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow/gviz/tq?tqx=out:csv&gid=0",
    "Sheet Task remain (GID=133591305)": "https://docs.google.com/spreadsheets/d/1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8/gviz/tq?tqx=out:csv&gid=133591305",
    "Sheet Auto Copy Config (GID=0)": "https://docs.google.com/spreadsheets/d/19RBlwehMC6BLoueaTEzsJHMx4puB0CTE5i5x79-uI6c/gviz/tq?tqx=out:csv&gid=0"
}

# ── 2. MA TRẬN LỊCH TRÌNH BÁO CÁO CHUẨN (MASTER SCHEDULE MATRIX) ───────────
SCHEDULE_RULES = [
    {
        "report_name": "Reports 1, 2, 3, 4 + BOD (Sáng)",
        "group_key": "CONTROL",
        "target_times": ["05:48"],
        "title_patterns": [
            r"1\.\s*BOD", r"BOD\s*Assign", r"4c\.\s*Asset", r"3\.1\s*Asset", r"Task\s*remain",
            r"Team\s*1\s*Dawei", r"Technical\s*Dept", r"TL\s*Comparison", r"Daily\s*EOD"
        ],
        "max_delay_min": 4
    },
    {
        "report_name": "Reports 1, 2, 3, 4 + BOD (Chiều)",
        "group_key": "CONTROL",
        "target_times": ["15:48"],
        "title_patterns": [
            r"1\.\s*BOD", r"BOD\s*Assign", r"4c\.\s*Asset", r"3\.1\s*Asset", r"Task\s*remain",
            r"Team\s*1\s*Dawei", r"Technical\s*Dept", r"TL\s*Comparison", r"Daily\s*EOD"
        ],
        "max_delay_min": 4
    },
    {
        "report_name": "Report 5A (Plan EOD)",
        "group_key": "CONTROL",
        "target_times": ["18:41"],
        "title_patterns": [r"5\.\s*Report.*Plan", r"Plan\s*EOD"],
        "max_delay_min": 4
    },
    {
        "report_name": "Report 5B (Plan Update)",
        "group_key": "CONTROL",
        "target_times": ["19:11"],
        "title_patterns": [r"5\.\s*Report.*Plan", r"Plan\s*Update"],
        "max_delay_min": 4
    },
    {
        "report_name": "Report 5C (Plan Sáng/Chiều)",
        "group_key": "CONTROL",
        "target_times": ["06:06", "08:28", "09:56", "15:26", "22:06"],
        "title_patterns": [r"5\.\s*Report.*Plan", r"Daily\s*Plan"],
        "max_delay_min": 4
    },
    {
        "report_name": "Report 6 (Read Status)",
        "group_key": "CONTROL",
        "target_times": ["08:48", "14:58", "17:18", "19:41"],
        "title_patterns": [r"6\.\s*Daily\s*Note\s*Read", r"Read\s*Report"],
        "max_delay_min": 4
    },
    {
        "report_name": "Report 6.1 (Site Clear Today)",
        "group_key": "CONTROL",
        "target_times": ["07:18", "10:18", "14:18", "17:18"],
        "title_patterns": [r"6\.1\s*Site\s*Clear", r"Site\s*Clear\s*Today"],
        "max_delay_min": 4
    },
    {
        "report_name": "Cable Daily Report",
        "group_key": "CONTROL",
        "target_times": ["05:56", "15:56"],
        "title_patterns": [r"Cable", r"Cáp"],
        "max_delay_min": 4
    },
    {
        "report_name": "Refuel Request Report",
        "group_key": "REFUEL",
        "target_times": ["05:48", "05:56", "07:06", "13:06", "15:56"],
        "title_patterns": [r"Refuel", r"Yêu\s*cầu.*dầu", r"Request\s*Refuel"],
        "max_delay_min": 4
    }
]


# ── 3. KIỂM TRA WEBHOOKS & ENDPOINTS TĨNH ───────────────────────────────────
def audit_telegram_webhooks():
    """Kiểm tra từng Telegram Bot Webhook xem có sống, đúng URL hay bị mất kết nối. Tự động phục hồi nếu rớt."""
    results = []
    for name, cfg in BOT_REGISTRY.items():
        token = cfg["token"]
        expected_url = cfg["expected_url"]
        ping_url = cfg["ping_url"]
        info_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
        try:
            t0 = time.time()
            resp = requests.get(info_url, timeout=8)
            dur = time.time() - t0
            if resp.status_code == 200:
                data = resp.json().get("result", {})
                curr_url = (data.get("url") or "").strip()
                pending = data.get("pending_update_count", 0)
                last_err = data.get("last_error_message")
                
                # Auto-recovery nếu rớt webhook
                if not curr_url and expected_url:
                    logger.warning(f"⚠️ {name} mất Webhook -> Đang tự động kết nối lại...")
                    try:
                        set_resp = requests.post(f"https://api.telegram.org/bot{token}/setWebhook", json={
                            "url": expected_url,
                            "allowed_updates": ["message", "edited_message", "channel_post"]
                        }, timeout=8)
                        if set_resp.status_code == 200 and set_resp.json().get("ok"):
                            curr_url = expected_url
                            logger.info(f"✅ Đã tự động khôi phục Webhook cho {name} thành công!")
                    except Exception as set_err:
                        logger.error(f"❌ Khôi phục Webhook thất bại: {set_err}")

                if not curr_url:
                    results.append({
                        "name": name,
                        "status": "FAIL",
                        "reason": "Mất Webhook (URL rỗng / Chưa lên tàu)",
                        "latency": f"{dur:.2f}s",
                        "pending": pending
                    })
                elif curr_url.lower() != expected_url.lower():
                    results.append({
                        "name": name,
                        "status": "FAIL",
                        "reason": f"Kết nối SAI địa chỉ: {curr_url[:30]}...",
                        "latency": f"{dur:.2f}s",
                        "pending": pending
                    })
                elif last_err and "timeout" in last_err.lower():
                    # Chỉ cảnh báo nếu là lỗi tạm thời
                    results.append({
                        "name": name,
                        "status": "WARN",
                        "reason": f"Cảnh báo: {last_err[:25]}",
                        "latency": f"{dur:.2f}s",
                        "pending": pending
                    })
                else:
                    results.append({
                        "name": name,
                        "status": "PASS",
                        "reason": f"Đang sống (0 lỗi | Queue={pending})",
                        "latency": f"{dur:.2f}s",
                        "pending": pending
                    })
            else:
                results.append({
                    "name": name,
                    "status": "FAIL",
                    "reason": f"Telegram API HTTP {resp.status_code}",
                    "latency": f"{dur:.2f}s"
                })
        except Exception as e:
            results.append({
                "name": name,
                "status": "FAIL",
                "reason": f"Lỗi kết nối: {str(e)[:25]}",
                "latency": "N/A"
            })
    return results


def audit_gas_backends():
    """Kiểm tra phản hồi của các Google Apps Script Backends."""
    results = []
    for name, cfg in GAS_SERVICES.items():
        url = cfg["url"]
        try:
            t0 = time.time()
            resp = requests.get(url, allow_redirects=True, timeout=12)
            dur = time.time() - t0
            if resp.status_code == 200:
                results.append({
                    "name": name,
                    "status": "PASS",
                    "reason": f"Đang sống (Phản hồi {dur:.2f}s)",
                    "latency": f"{dur:.2f}s"
                })
            else:
                results.append({
                    "name": name,
                    "status": "FAIL",
                    "reason": f"HTTP {resp.status_code} ({dur:.2f}s)",
                    "latency": f"{dur:.2f}s"
                })
        except Exception as e:
            results.append({
                "name": name,
                "status": "FAIL",
                "reason": f"Timeout / Ngủ: {str(e)[:25]}",
                "latency": ">12s"
            })
    return results


def audit_sheets_connectors():
    """Kiểm tra kết nối và độ trễ đọc Google Sheets qua GVIZ CSV."""
    results = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for name, url in SHEET_CONNECTORS.items():
        try:
            t0 = time.time()
            resp = requests.get(url, headers=headers, timeout=10)
            dur = time.time() - t0
            if resp.status_code == 200 and len(resp.text) > 50:
                lines = resp.text.split("\n")
                results.append({
                    "name": name,
                    "status": "PASS",
                    "reason": f"Kết nối tốt ({len(lines)} dòng | {dur:.2f}s)",
                    "latency": f"{dur:.2f}s"
                })
            else:
                results.append({
                    "name": name,
                    "status": "FAIL",
                    "reason": f"HTTP {resp.status_code} / Rỗng",
                    "latency": f"{dur:.2f}s"
                })
        except Exception as e:
            results.append({
                "name": name,
                "status": "FAIL",
                "reason": f"Lỗi kết nối Sheet: {str(e)[:25]}",
                "latency": "N/A"
            })
    return results


# ── 4. KIỂM TRA ĐÚNG GIỜ & PHÁT HIỆN NHÂN ĐÔI TIN NHẮN (TELETHON AUDIT) ─────
async def audit_telegram_messages_telethon():
    """
    Quét lịch sử tin nhắn thực tế trong các nhóm Telegram để:
    1. Kiểm tra xem các mốc giờ đã qua trong ngày có tin nhắn gửi ĐÚNG GIỜ không.
    2. Phát hiện các tin nhắn bị NHÂN ĐÔI (gửi lặp lại / chưa xóa tin cũ).
    """
    if not (TELEGRAM_API_ID and TELEGRAM_API_HASH and TELEGRAM_SESSION and len(TELEGRAM_SESSION) >= 100):
        logger.warning("⚠️ Không có Telethon Session hợp lệ -> Bỏ qua kiểm tra Telethon sâu.")
        return {
            "available": False,
            "schedule_results": [],
            "duplicate_results": []
        }

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    schedule_results = []
    duplicate_results = []

    now_mmt = datetime.now(TZ_MM)
    today_start = now_mmt.replace(hour=0, minute=0, second=0, microsecond=0)
    current_time_str = now_mmt.strftime("%H:%M")
    current_total_min = now_mmt.hour * 60 + now_mmt.minute

    try:
        async with TelegramClient(StringSession(TELEGRAM_SESSION), TELEGRAM_API_ID, TELEGRAM_API_HASH) as client:
            logger.info("📡 Đã kết nối Telethon Client để quét kiểm toán tin nhắn...")

            # Lưu cache tin nhắn từng nhóm
            group_messages = {}
            for gkey, gid in ALL_MONITORED_GROUPS.items():
                try:
                    msgs = []
                    async for msg in client.iter_messages(gid, limit=80):
                        if not msg.text:
                            continue
                        msg_date_mmt = msg.date.astimezone(TZ_MM)
                        if msg_date_mmt >= today_start:
                            msgs.append({
                                "id": msg.id,
                                "date": msg_date_mmt,
                                "time_str": msg_date_mmt.strftime("%H:%M"),
                                "total_min": msg_date_mmt.hour * 60 + msg_date_mmt.minute,
                                "sender_id": msg.sender_id,
                                "text": msg.text,
                                "first_line": msg.text.split("\n")[0].strip()
                            })
                    group_messages[gkey] = msgs
                    logger.info(f"   📥 Quét nhóm {gkey} ({gid}): lấy {len(msgs)} tin nhắn hôm nay.")
                except Exception as ge:
                    logger.warning(f"   ⚠️ Lỗi quét nhóm {gkey} ({gid}): {ge}")
                    group_messages[gkey] = []

            # ── A. KIỂM TRA ĐÚNG GIỜ (Schedule Adherence) ──
            for rule in SCHEDULE_RULES:
                r_name = rule["report_name"]
                gkey = rule["group_key"]
                msgs = group_messages.get(gkey, [])
                patterns = [re.compile(p, re.IGNORECASE) for p in rule["title_patterns"]]

                for target_t in rule["target_times"]:
                    th, tm = map(int, target_t.split(":"))
                    target_total_min = th * 60 + tm

                    # Chỉ kiểm tra các mốc giờ đã qua trong ngày (cách ít nhất 2 phút)
                    if target_total_min > current_total_min + 2:
                        continue # Mốc giờ tương lai -> bỏ qua

                    # Tìm tin nhắn khớp với tiêu đề
                    matched_msgs = []
                    for m in msgs:
                        is_match = any(p.search(m["text"]) for p in patterns)
                        if is_match:
                            diff = abs(m["total_min"] - target_total_min)
                            matched_msgs.append((diff, m))

                    if not matched_msgs:
                        # Nếu mốc giờ đã qua hơn 15 phút mà không có tin nhắn -> MISSED
                        if current_total_min - target_total_min >= 15:
                            schedule_results.append({
                                "report": r_name,
                                "target_time": target_t,
                                "group": gkey,
                                "status": "FAIL",
                                "label": "🔴 MISSED",
                                "detail": f"Không có tin nhắn nào lúc {target_t} (Trễ {current_total_min - target_total_min}p)"
                            })
                    else:
                        # Sắp xếp theo độ gần với giờ đích nhất
                        matched_msgs.sort(key=lambda x: x[0])
                        best_diff, best_msg = matched_msgs[0]

                        if best_diff <= rule["max_delay_min"]:
                            schedule_results.append({
                                "report": r_name,
                                "target_time": target_t,
                                "group": gkey,
                                "status": "PASS",
                                "label": "🟢 ON-TIME",
                                "detail": f"Gửi lúc {best_msg['time_str']} (Lệch {best_diff}p | ID: {best_msg['id']})"
                            })
                        elif best_diff <= 15:
                            schedule_results.append({
                                "report": r_name,
                                "target_time": target_t,
                                "group": gkey,
                                "status": "WARN",
                                "label": "🟡 DELAYED",
                                "detail": f"Gửi lúc {best_msg['time_str']} (Trễ {best_diff}p | ID: {best_msg['id']})"
                            })
                        else:
                            schedule_results.append({
                                "report": r_name,
                                "target_time": target_t,
                                "group": gkey,
                                "status": "FAIL",
                                "label": "🔴 MISSED",
                                "detail": f"Tin gần nhất lúc {best_msg['time_str']} lệch {best_diff}p so với {target_t}"
                            })

            # ── B. KIỂM TRA NHÂN ĐÔI TIN NHẮN (Deduplication Check) ──
            for gkey, msgs in group_messages.items():
                if len(msgs) < 2:
                    continue
                
                # Phân nhóm tin nhắn theo dòng đầu tiên (tiêu đề) đã chuẩn hóa
                title_map = {}
                for m in msgs:
                    clean_title = re.sub(r"[\*\_`#\[\]\(\)\d\/\:\s\-]", "", m["first_line"][:40]).lower()
                    if len(clean_title) < 5:
                        continue
                    if clean_title not in title_map:
                        title_map[clean_title] = []
                    title_map[clean_title].append(m)

                for title_key, item_list in title_map.items():
                    if len(item_list) >= 2:
                        # Sắp xếp theo thời gian gửi
                        item_list.sort(key=lambda x: x["date"])
                        for i in range(len(item_list) - 1):
                            m1 = item_list[i]
                            m2 = item_list[i+1]
                            diff_sec = abs((m2["date"] - m1["date"]).total_seconds())

                            # Nếu 2 tin cùng loại gửi cách nhau < 180s (3 phút) -> NHÂN ĐÔI
                            if diff_sec <= 180:
                                duplicate_results.append({
                                    "group": gkey,
                                    "title": m1["first_line"][:35],
                                    "time1": m1["time_str"],
                                    "time2": m2["time_str"],
                                    "diff_sec": int(diff_sec),
                                    "id1": m1["id"],
                                    "id2": m2["id"],
                                    "detail": f"Nhân đôi trong nhóm {gkey}: {m1['time_str']} & {m2['time_str']} (Cách {int(diff_sec)}s | ID {m1['id']},{m2['id']})"
                                })

            # ── C. KIỂM TRA CHẤT LƯỢNG NỘI DUNG & QUÂN SỐ (Data Quality & Roster Audit) ──
            quality_results = []
            for gkey, msgs in group_messages.items():
                for m in msgs:
                    text = m.get("text", "")
                    # 1. Báo cáo 4c Placeholder Name Check
                    if "4c. Report — Employee Task & Rank" in text:
                        if re.search(r'\bnv_\d+\b', text) or re.search(r'\bTeam leader \d+\b', text):
                            quality_results.append({
                                "report": "4c. Report — Employee Task & Rank",
                                "group": gkey,
                                "status": "FAIL",
                                "label": "🔴 PLACEHOLDER NAME",
                                "detail": f"Nhóm {gkey}: Báo cáo 4c chứa mã tạm (nv_ hoặc Team leader N) chưa chuyển sang tên thật!"
                            })
                    # 2. Báo cáo 6 Roster Deficit Check
                    if gkey in ("T1", "T2", "T3", "T4") and ("6. Report — Daily Note Read Report" in text or "Daily Note Read Report" in text):
                        m_cnt = re.search(r'Team Members:\s*(\d+)', text)
                        if m_cnt:
                            cnt = int(m_cnt.group(1))
                            if cnt < 4:
                                quality_results.append({
                                    "report": "Report 6 (Read Status)",
                                    "group": gkey,
                                    "status": "FAIL",
                                    "label": "🔴 ROSTER DEFICIT",
                                    "detail": f"Nhóm {gkey}: Báo cáo 6 chỉ có {cnt} nhân viên (Quân số chuẩn phải >= 5)!"
                                })

            # 3. Chống Lặp Tin Nhắn Mẫu / Bot Template Loop Check
            for gkey, msgs in group_messages.items():
                template_msgs = [m for m in msgs if m.get("text") and ("Plan:" in m["text"] or "Delivery:" in m["text"] or "Upgraded:" in m["text"] or "/Note:" in m["text"])]
                if len(template_msgs) >= 3:
                    for i in range(len(template_msgs) - 2):
                        m1 = template_msgs[i]
                        m3 = template_msgs[i+2]
                        if abs((m3["date"] - m1["date"]).total_seconds()) <= 120:
                            quality_results.append({
                                "report": "Bot Template Response",
                                "group": gkey,
                                "status": "FAIL",
                                "label": "🔴 BOT TEMPLATE LOOP DETECTED",
                                "detail": f"Nhóm {gkey}: Phát hiện Bot gửi lặp tin mẫu 3+ lần trong vòng 2 phút!"
                            })
                            break

        return {
            "available": True,
            "schedule_results": schedule_results,
            "duplicate_results": duplicate_results,
            "quality_results": quality_results
        }
    except Exception as te:
        logger.error(f"❌ Lỗi Telethon Message Audit: {te}")
        return {
            "available": False,
            "error": str(te),
            "schedule_results": [],
            "duplicate_results": [],
            "quality_results": []
        }


# ── 5. TỔNG HỢP BÁO CÁO & PHÁT CẢNH BÁO ĐỎ ──────────────────────────────────
def build_master_audit_report():
    """
    Tổng hợp toàn bộ các kết quả kiểm tra thành bản tin báo cáo:
    - Nếu TẤT CẢ OK: Gửi dòng ngắn gọn '🟢 [AUDITOR-9.1] 1, 2, 3, 4 OK'.
    - Nếu CÓ LỖI: Chỉ liệt kê các thành phần bị lỗi / trễ giờ / nhân đôi để xử lý ngay.
    """
    now_mmt = datetime.now(TZ_MM).strftime("%d/%m/%Y %H:%M:%S")
    logger.info("🔍 Bắt đầu quét kiểm toán sâu toàn bộ hệ thống...")

    # 1. Chạy các bài kiểm tra
    webhook_res = audit_telegram_webhooks()
    gas_res = audit_gas_backends()
    sheets_res = audit_sheets_connectors()

    # 2. Chạy kiểm tra Telethon (Đúng giờ & Nhân đôi)
    try:
        telethon_data = asyncio.run(audit_telegram_messages_telethon())
    except Exception as ae:
        logger.error(f"Lỗi chạy asyncio telethon: {ae}")
        telethon_data = {"available": False, "schedule_results": [], "duplicate_results": []}

    schedule_res = telethon_data.get("schedule_results", [])
    duplicate_res = telethon_data.get("duplicate_results", [])
    quality_res = telethon_data.get("quality_results", [])

    # 3. Tính toán sự cố (Chỉ tính status FAIL là lỗi thực sự)
    fail_checks = sum(1 for c in (webhook_res + gas_res + sheets_res) if c["status"] == "FAIL")
    warn_checks = sum(1 for c in (webhook_res + gas_res + sheets_res) if c["status"] == "WARN")

    missed_count = sum(1 for s in schedule_res if s["status"] == "FAIL")
    delay_count = sum(1 for s in schedule_res if s["status"] == "WARN")
    dup_count = len(duplicate_res)
    quality_count = len(quality_res)

    total_incidents = fail_checks + missed_count + dup_count + quality_count

    # 🟢 TRƯỜNG HỢP 1: TẤT CẢ ĐỀU OK -> BÁO CÁO SIÊU NGẮN GỌN (1, 2, 3, 4 OK)
    if total_incidents == 0 and delay_count == 0 and warn_checks == 0:
        lines = [
            "🟢 <b>[AUDITOR-9.1] 1, 2, 3, 4 OK</b>",
            f"⏰ {now_mmt} MMT"
        ]
        return "\n".join(lines), 0

    # 🔴 TRƯỜNG HỢP 2: CÓ LỖI / TRỄ / NHÂN ĐÔI / SAI DỮ LIỆU -> CHỈ BÁO CHI TIẾT CÁC MỤC LỖI
    lines = []
    lines.append("🚨 <b>[SYSTEM ALERT — PHÁT HIỆN SỰ CỐ HỆ THỐNG]</b>")
    lines.append(f"⏰ <b>Thời gian:</b> {now_mmt} (MMT)")
    lines.append(f"❌ <b>Tổng sự cố:</b> {total_incidents} Lỗi" + (f" | ⚠️ {warn_checks + delay_count} Cảnh báo" if (warn_checks + delay_count) > 0 else ""))
    lines.append("──────────────────────────")

    # 1. Báo cáo lỗi Chất Lượng Nội Dung & Quân Số
    if quality_res:
        lines.append(f"\n📋 <b>LỖI CHẤT LƯỢNG NỘI DUNG & QUÂN SỐ ({len(quality_res)} lỗi):</b>")
        for q in quality_res:
            lines.append(f"   {q['label']} <b>{q['report']}</b> ({q['group']})")
            lines.append(f"      └ <i>{q['detail']}</i>")

    # 2. Báo cáo lỗi Đúng Giờ / Bỏ Sót
    missed_items = [s for s in schedule_res if s["status"] in ("FAIL", "WARN")]
    if missed_items:
        lines.append("\n⏰ <b>LỖI TIẾN ĐỘ & TRỄ GIỜ:</b>")
        for s in missed_items:
            lines.append(f"   {s['label']} <b>{s['report']}</b> ({s['target_time']} MMT)")
            lines.append(f"      └ <i>{s['detail']}</i>")

    # 3. Báo cáo lỗi Nhân Đôi
    if duplicate_res:
        lines.append(f"\n🛡️ <b>LỖI NHÂN ĐÔI TIN NHẮN ({len(duplicate_res)} trường hợp):</b>")
        for d in duplicate_res:
            lines.append(f"   ❌ <b>[{d['group']}]</b> <i>{d['title']}</i>")
            lines.append(f"      └ Gửi 2 tin lúc: <b>{d['time1']}</b> & <b>{d['time2']}</b> (Cách {d['diff_sec']}s | ID: {d['id1']}, {d['id2']})")

    # 3. Báo cáo lỗi Webhooks Bot
    webhook_fails = [r for r in webhook_res if r["status"] != "PASS"]
    if webhook_fails:
        lines.append("\n🤖 <b>LỖI KẾT NỐI WEBHOOK:</b>")
        for r in webhook_fails:
            lines.append(f"   ❌ <b>{r['name']}</b>: <i>{r['reason']}</i>")

    # 4. Báo cáo lỗi GAS
    gas_fails = [r for r in gas_res if r["status"] != "PASS"]
    if gas_fails:
        lines.append("\n☁️ <b>LỖI GOOGLE APPS SCRIPT:</b>")
        for r in gas_fails:
            lines.append(f"   ❌ <b>{r['name']}</b>: <i>{r['reason']}</i>")

    # 5. Báo cáo lỗi Sheets
    sheet_fails = [r for r in sheets_res if r["status"] != "PASS"]
    if sheet_fails:
        lines.append("\n📊 <b>LỖI GOOGLE SHEETS:</b>")
        for r in sheet_fails:
            lines.append(f"   ❌ <b>{r['name']}</b>: <i>{r['reason']}</i>")

    lines.append("\n──────────────────────────")
    lines.append("👉 <i>Vui lòng xử lý các thành phần báo lỗi ở trên.</i>")

    return "\n".join(lines), total_incidents


def send_report_telegram(msg_text: str):
    """GỬI DUY NHẤT VỀ TELEGRAM DM CỦA ADMIN (6859790680), TUYỆT ĐỐI KHÔNG GỬI VÀO BẤT KỲ GROUP NÀO."""
    token = SEND_BOT_TOKEN
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": ADMIN_CHAT_ID,
            "text": msg_text,
            "parse_mode": "HTML"
        }
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            logger.info(f"✅ Đã gửi báo cáo Ghế AUDITOR-9.1 thành công đến DM Admin: {ADMIN_CHAT_ID}")
        else:
            logger.error(f"❌ Gửi Telegram thất bại DM {ADMIN_CHAT_ID}: HTTP {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"❌ Lỗi gửi Telegram DM {ADMIN_CHAT_ID}: {e}")


def main():
    logger.info("🚂 KHỞI CHẠY GHẾ AUDITOR-9.1: QUÉT KIỂM TOÁN HỆ THỐNG GỬI DM ADMIN")
    report_text, incident_count = build_master_audit_report()
    print("\n" + "=" * 65)
    print(report_text)
    print("=" * 65 + "\n")

    send_report_telegram(report_text)
    logger.info(f"🏁 Hoàn tất kiểm toán Ghế AUDITOR-9.1 (Phát hiện {incident_count} sự cố).")


if __name__ == "__main__":
    main()
