"""
health_check.py
===============
System-Wide Health Check & Endpoints Auditor for TNI Bot Infrastructure.
Audits all Google Apps Script WebApp URLs and Vercel endpoints registered in system_map.md.
"""

import requests
import json
import sys
from datetime import datetime, timezone, timedelta

TZ_MM = timezone(timedelta(hours=6, minutes=30))

ENDPOINTS_TO_CHECK = [
    {
        "name": "Main Apps Script (Collector @302)",
        "url": "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec",
        "method": "GET",
        "allow_redirects": True
    },
    {
        "name": "Refuel Apps Script (@71)",
        "url": "https://script.google.com/macros/s/AKfycbyCibIj4QN7oG5BZc_ju1iS-DUmd9nNdrMn9UN-WD8qf6jVoU_OKOf2yfbi10qGMFF-/exec",
        "method": "GET",
        "allow_redirects": True
    },
    {
        "name": "Site Down Standalone Apps Script",
        "url": "https://script.google.com/macros/s/AKfycbxVi0BGDW7B_KBxcSEdw3yuHB9Rs2BemQEYeKDwsybJQdmQv-_0HqyGHjpZI6jupxll/exec",
        "method": "GET",
        "allow_redirects": True
    },
    {
        "name": "Construction Keepalive Apps Script",
        "url": "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec",
        "method": "GET",
        "allow_redirects": True
    },
    {
        "name": "Vercel Search Bot Webhook",
        "url": "https://tni-bot.vercel.app/api/search_bot",
        "method": "GET",
        "allow_redirects": True
    },
    {
        "name": "Vercel Asset Collector Webhook",
        "url": "https://tni-bot.vercel.app/api/collector",
        "method": "GET",
        "allow_redirects": True
    },
    {
        "name": "Vercel Refuel Collector Webhook",
        "url": "https://tni-bot.vercel.app/api/refuel_collector",
        "method": "GET",
        "allow_redirects": True
    }
]

def run_health_check():
    now_str = datetime.now(TZ_MM).strftime("%d/%m/%Y %H:%M:%S MMT")
    print(f"==================================================")
    print(f"🏥 TNI BOT SYSTEM HEALTH CHECK AUDIT")
    print(f"📅 Timestamp: {now_str}")
    print(f"==================================================\n")

    all_healthy = True
    results = []

    for item in ENDPOINTS_TO_CHECK:
        name = item["name"]
        url = item["url"]
        try:
            res = requests.request(item["method"], url, timeout=12, allow_redirects=item["allow_redirects"])
            status_code = res.status_code
            is_ok = (status_code in [200, 302, 405]) # 405 is fine for POST-only GET requests on Vercel handler
            status_icon = "✅ OK" if is_ok else f"❌ FAIL ({status_code})"
            if not is_ok:
                all_healthy = False
            print(f"{status_icon} | Code: {status_code} | {name}")
            results.append({"name": name, "status": status_code, "ok": is_ok})
        except Exception as e:
            all_healthy = False
            print(f"❌ ERROR | {name} -> {e}")
            results.append({"name": name, "status": "ERROR", "ok": False, "error": str(e)})

    print("\n" + "=" * 50)
    if all_healthy:
        print("🎉 ALL ENDPOINTS HEALTHY & RESPONSIVE! [100%]")
    else:
        print("⚠️ HEALTH CHECK DETECTED UNHEALTHY ENDPOINTS!")
    print("=" * 50)
    return all_healthy

if __name__ == "__main__":
    success = run_health_check()
    sys.exit(0 if success else 1)
