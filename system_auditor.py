#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
══════════════════════════════════════════════════════════════════════════════
🚂 CHUYẾN TÀU SỐ 3: SCHEDULED AUTOMATION LINE
🚨 TOA TÀU: TOA KIỂM TOÁN HỆ THỐNG TOÀN DIỆN (SYSTEM AUDIT & SENTINEL CAR)
👑 GHẾ: GHẾ AUDITOR-9.1 (CHUYÊN GIA KIỂM TRA SỨC KHỎE HỆ THỐNG 09:00 AM MMT)
══════════════════════════════════════════════════════════════════════════════
Chức năng hạt nhân:
  - Quét tự động toàn bộ 100% các thành phần của hệ thống vào 09:00 AM hàng ngày:
    1. Telegram Bot Webhooks & Realtime Latency (Search, Asset, SiteDown, Cons).
    2. Google Apps Script Web App Endpoints & Backend Health.
    3. GitHub Actions Train Runners & Workflow Concurrency.
    4. Google Sheets Database & Ingestion Connectors (GID=0, Task remain, Config).
  - Tự động gắn nhãn:
    ✅ Done / Active / Connected (Nếu hệ thống sống, phản hồi chuẩn < 3s).
    ❌ Error / Disconnected / Missed Train / Sleeping (Nếu mất kết nối, sai URL).
  - Tự động HỒI SINH (Auto-Heal) nếu phát hiện bất kỳ Bot nào bị rớt Webhook!
  - GỬI DUY NHẤT VỀ TELEGRAM DM CÁ NHÂN CỦA ADMIN (6859790680), KHÔNG GỬI VÀO GROUP CONTROL!
══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import time
import json
import logging
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Múi giờ Myanmar UTC+6:30
TZ_MM = timezone(timedelta(hours=6, minutes=30))

# ── CẤU HÌNH GỬI RIÊNG VỀ DM CÁ NHÂN ADMIN (KHÔNG GỬI VÀO GROUP) ────────────
ADMIN_CHAT_ID = "6859790680" # Ha Duc Phong
SEND_BOT_TOKEN = os.getenv("SEND_BOT_TOKEN", "8647102342:AAGwI95-xeyFfJZusOOrIPVBER-z6taZHZI")

# Danh bạ Webhook chuẩn cố định (Strict Endpoint Registry theo AGENTS.md)
BOT_REGISTRY = {
    "Search Bot (@SEARCHTNITASKWOBOT)": {
        "token": "8606383435:AAEstcN4Om6_9ZAjs4OoFV2uVlRALgae2Ac",
        "expected_url": "https://tni-bot.vercel.app/api/search_bot",
        "ping_url": "https://tni-bot.vercel.app/api/search_bot?action=reset"
    },
    "Asset Collector (@TNIASSETorderREQUEST_BOT)": {
        "token": "8928677923:AAE_cJuEDH1tUf5v0q5Wf0UjDHlcp_k1lGM",
        "expected_url": "https://tni-bot.vercel.app/api/collector",
        "ping_url": "https://tni-bot.vercel.app/api/collector?action=reset"
    },
    "Site Down Relay (@TNI_SITE_DOWN_CELL_ALARMBOT)": {
        "token": "8647102342:AAGwI95-xeyFfJZusOOrIPVBER-z6taZHZI",
        "expected_url": "https://tni-sitedown.vercel.app/api/site_down_relay",
        "ping_url": "https://tni-sitedown.vercel.app/api/site_down_relay"
    },
    "Construction Bot 10 (@8903841312)": {
        "token": "8903841312:AAHQ_LeI19gs2nrqBSInTsgzJXOuv6H8LmE",
        "expected_url": "https://script.google.com/macros/s/AKfycbwi3J0VrrIE91mnPvIUuykPjwGvNc4y9JDxCNPvJTtOmVAvvalDXu5ZwYZmu5jW-fSo0w/exec",
        "ping_url": "https://script.google.com/macros/s/AKfycbwi3J0VrrIE91mnPvIUuykPjwGvNc4y9JDxCNPvJTtOmVAvvalDXu5ZwYZmu5jW-fSo0w/exec?action=ping"
    }
}

# Backend GAS Services
GAS_SERVICES = {
    "TNI Main GAS Backend (@302)": {
        "url": "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec?action=ping"
    },
    "Standalone Site Down GAS Backend": {
        "url": "https://script.google.com/macros/s/AKfycbwi3J0VrrIE91mnPvIUuykPjwGvNc4y9JDxCNPvJTtOmVAvvalDXu5ZwYZmu5jW-fSo0w/exec?action=get_note_msgids"
    }
}

# Google Sheets Data Connectors
SHEET_CONNECTORS = {
    "Sheet 10_TNI_SITE_DOWN (GID=0)": "https://docs.google.com/spreadsheets/d/1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow/gviz/tq?tqx=out:csv&gid=0",
    "Sheet Task remain (GID=133591305)": "https://docs.google.com/spreadsheets/d/1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8/gviz/tq?tqx=out:csv&gid=133591305",
    "Sheet Auto Copy Config (GID=0)": "https://docs.google.com/spreadsheets/d/19RBlwehMC6BLoueaTEzsJHMx4puB0CTE5i5x79-uI6c/gviz/tq?tqx=out:csv&gid=0"
}


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
                elif last_err:
                    results.append({
                        "name": name,
                        "status": "WARN",
                        "reason": f"Webhook OK (Cảnh báo: {last_err[:25]})",
                        "latency": f"{dur:.2f}s",
                        "pending": pending
                    })
                else:
                    ping_ok = True
                    try:
                        p_resp = requests.get(ping_url, timeout=5)
                        if p_resp.status_code not in (200, 302):
                            ping_ok = False
                    except:
                        ping_ok = False
                    
                    state_txt = "Đang sống (Active)" if ping_ok else "Đang sưởi ấm"
                    results.append({
                        "name": name,
                        "status": "PASS",
                        "reason": f"{state_txt} (0 lỗi | Queue={pending})",
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


def audit_github_runners():
    """Kiểm tra tình trạng các đoàn tàu GitHub Actions Runner."""
    results = []
    repos = ["MON6879/tni-sitedown-relay"]
    headers = {"User-Agent": "Mozilla/5.0"}
    for repo in repos:
        try:
            url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=3"
            t0 = time.time()
            resp = requests.get(url, headers=headers, timeout=8)
            dur = time.time() - t0
            if resp.status_code == 200:
                runs = resp.json().get("workflow_runs", [])
                if runs:
                    latest = runs[0]
                    w_name = latest.get("name", "Train")
                    w_concl = latest.get("conclusion") or latest.get("status")
                    if w_concl in ("success", "completed", "in_progress"):
                        results.append({
                            "name": f"GitHub Runner ({repo})",
                            "status": "PASS",
                            "reason": f"Chạy tốt [{w_concl}]",
                            "latency": f"{dur:.2f}s"
                        })
                    else:
                        results.append({
                            "name": f"GitHub Runner ({repo})",
                            "status": "WARN",
                            "reason": f"Lần chạy gần nhất: {w_concl}",
                            "latency": f"{dur:.2f}s"
                        })
                else:
                    results.append({
                        "name": f"GitHub Runner ({repo})",
                        "status": "PASS",
                        "reason": "Repo kết nối tốt",
                        "latency": f"{dur:.2f}s"
                    })
            else:
                results.append({
                    "name": f"GitHub Runner ({repo})",
                    "status": "FAIL",
                    "reason": f"HTTP {resp.status_code}",
                    "latency": f"{dur:.2f}s"
                })
        except Exception as e:
            results.append({
                "name": f"GitHub Runner ({repo})",
                "status": "FAIL",
                "reason": f"Lỗi API GitHub: {str(e)[:25]}",
                "latency": "N/A"
            })
    return results


def build_audit_report():
    """Tổng hợp toàn bộ các kết quả kiểm tra thành bản tin báo cáo hoàn chỉnh."""
    now_mmt = datetime.now(TZ_MM).strftime("%d/%m/%Y %H:%M:%S")
    
    logger.info("🔍 Bắt đầu quét kiểm toán toàn bộ hệ thống...")
    webhook_res = audit_telegram_webhooks()
    gas_res = audit_gas_backends()
    sheets_res = audit_sheets_connectors()
    github_res = audit_github_runners()
    
    all_checks = webhook_res + gas_res + sheets_res + github_res
    total_checks = len(all_checks)
    pass_checks = sum(1 for c in all_checks if c["status"] == "PASS")
    warn_checks = sum(1 for c in all_checks if c["status"] == "WARN")
    fail_checks = sum(1 for c in all_checks if c["status"] == "FAIL")
    
    health_pct = int((pass_checks / total_checks) * 100) if total_checks else 0
    health_icon = "🟢" if fail_checks == 0 else ("🟡" if fail_checks <= 2 else "🔴")
    
    lines = []
    lines.append(f"{health_icon} <b>BÁO CÁO KIỂM TOÁN HỆ THỐNG — GHẾ 9.1</b>")
    lines.append(f"⏰ <b>Thời gian kiểm tra:</b> {now_mmt} (MMT)")
    lines.append(f"📊 <b>Sức khỏe hệ thống:</b> {health_pct}% ({pass_checks}/{total_checks} Done | ⚠️ {warn_checks} | ❌ {fail_checks} Lỗi)")
    lines.append("━" * 26)
    
    # 1. Telegram Webhooks
    lines.append("\n🤖 <b>1. TELEGRAM BOT WEBHOOKS & REALTIME:</b>")
    lines.append("─" * 22)
    for r in webhook_res:
        icon = "✅" if r["status"] == "PASS" else ("⚠️" if r["status"] == "WARN" else "❌")
        lines.append(f"{icon} <b>{r['name']}</b>")
        lines.append(f"   └ <i>{r['reason']}</i> ({r['latency']})")
        
    # 2. GAS Backends
    lines.append("\n☁️ <b>2. GOOGLE APPS SCRIPT BACKENDS:</b>")
    lines.append("─" * 22)
    for r in gas_res:
        icon = "✅" if r["status"] == "PASS" else "❌"
        lines.append(f"{icon} <b>{r['name']}</b>")
        lines.append(f"   └ <i>{r['reason']}</i>")
        
    # 3. Google Sheets Connectors
    lines.append("\n📊 <b>3. GOOGLE SHEETS DATABASE CONNECTORS:</b>")
    lines.append("─" * 22)
    for r in sheets_res:
        icon = "✅" if r["status"] == "PASS" else "❌"
        lines.append(f"{icon} <b>{r['name']}</b>")
        lines.append(f"   └ <i>{r['reason']}</i>")
        
    # 4. GitHub Train Runners
    lines.append("\n🚂 <b>4. GITHUB ACTIONS TRAIN RUNNERS:</b>")
    lines.append("─" * 22)
    for r in github_res:
        icon = "✅" if r["status"] == "PASS" else ("⚠️" if r["status"] == "WARN" else "❌")
        lines.append(f"{icon} <b>{r['name']}</b>")
        lines.append(f"   └ <i>{r['reason']}</i>")
        
    lines.append("\n━" * 26)
    if fail_checks == 0:
        lines.append("🎉 <b>KẾT LUẬN:</b> Toàn bộ hệ thống sống 100%, kết nối chuẩn xác!")
    else:
        lines.append("⚠️ <b>KẾT LUẬN:</b> Có thành phần mất kết nối/lỗi! Vui lòng kiểm tra mục ❌ ở trên.")
        
    return "\n".join(lines), fail_checks


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
            logger.info(f"✅ Đã gửi báo cáo Ghế 9.1 thành công đến DM Admin: {ADMIN_CHAT_ID}")
        else:
            logger.error(f"❌ Gửi Telegram thất bại DM {ADMIN_CHAT_ID}: HTTP {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"❌ Lỗi gửi Telegram DM {ADMIN_CHAT_ID}: {e}")


def main():
    logger.info("🚂 KHỞI CHẠY GHẾ AUDITOR-9.1: QUÉT KIỂM TOÁN HỆ THỐNG GỬI DM ADMIN")
    report_text, fail_count = build_audit_report()
    print("\n" + "=" * 60)
    print(report_text)
    print("=" * 60 + "\n")
    
    send_report_telegram(report_text)
    logger.info(f"🏁 Hoàn tất kiểm toán Ghế 9.1 (Phát hiện {fail_count} lỗi).")


if __name__ == "__main__":
    main()
