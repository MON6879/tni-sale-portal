"""
Cable Daily Report — sends statistics to TNI CABLE ROUTE group.
Schedule via GitHub Actions cron.

Stats: Today / 3-Day / 7-Day / Monthly — per Type (Rescue/RC/Maintenance/Deploy)
"""
import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

CABLE_BOT_TOKEN      = os.getenv("CABLE_BOT_TOKEN") or "8758104446:AAH3o7lMCxBXn70ThAXweH1DddmRkJrgwWo"
CABLE_CHAT_ID        = os.getenv("CABLE_CHAT_ID", "-5531350787")
CABLE_APPS_SCRIPT_URL = os.getenv("CABLE_APPS_SCRIPT_URL", "")
TZ_MM = timezone(timedelta(hours=6, minutes=30))               # Myanmar UTC+6:30

TYPE_EMOJIS = {
    "rescue":         "🚨",
    "request change": "🔄",
    "maintenance":    "🔧",
    "deploy":         "🚀",
}


def get_stats() -> dict | None:
    """Fetch stats from Cable Apps Script."""
    if not CABLE_APPS_SCRIPT_URL:
        print("❌ CABLE_APPS_SCRIPT_URL not set", file=sys.stderr)
        return None
    try:
        resp = requests.get(
            CABLE_APPS_SCRIPT_URL,
            params={"action": "cable_get_stats"},
            timeout=30,
        )
        data = resp.json()
        if data.get("status") == "ok":
            return data["stats"]
        print(f"⚠️ Stats error: {data.get('message')}", file=sys.stderr)
    except Exception as e:
        print(f"❌ Stats fetch error: {e}", file=sys.stderr)
    return None


def format_report(stats: dict) -> str:
    now      = datetime.now(TZ_MM)
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M")

    lines = [
        "🔌 <b>TNI CABLE ROUTE — Daily Report</b>",
        f"📅 {date_str}  ⏰ {time_str} (Myanmar)",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📊 <b>Overall Summary</b>",
        f"  • Today    : <b>{stats.get('today', 0)}</b>",
        f"  • 3 Days   : <b>{stats.get('day3', 0)}</b>",
        f"  • 7 Days   : <b>{stats.get('day7', 0)}</b>",
        f"  • This Month: <b>{stats.get('month', 0)}</b>",
        f"  • All Time : <b>{stats.get('total', 0)}</b>",
        "",
        f"✅ Confirmed: <b>{stats.get('confirmed', 0)}</b>  "
        f"⏳ Pending: <b>{stats.get('pending', 0)}</b>",
    ]

    by_type: dict = stats.get("by_type", {})
    if by_type:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        lines.append("📋 <b>By Type</b>")
        for type_key, ts in by_type.items():
            if not type_key:
                continue
            emoji     = TYPE_EMOJIS.get(type_key.lower(), "📌")
            type_name = type_key.title()
            lines.append(
                f"{emoji} <b>{type_name}</b>\n"
                f"   Today:{ts.get('today',0)} | "
                f"3d:{ts.get('day3',0)} | "
                f"7d:{ts.get('day7',0)} | "
                f"Mo:{ts.get('month',0)} | "
                f"All:{ts.get('total',0)}"
            )

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🤖 <i>Auto report by 15 TNI CABLE</i>")
    return "\n".join(lines)


def send_telegram(chat_id: str, text: str) -> tuple[bool, int | None]:
    """Send message to Telegram group."""
    url  = f"https://api.telegram.org/bot{CABLE_BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=60,
    )
    res_json = resp.json()
    ok = res_json.get("ok", False)
    msg_id = None
    if ok:
        print(f"✅ Report sent to {chat_id}")
        msg_id = res_json.get("result", {}).get("message_id")
    else:
        print(f"❌ Send failed: {resp.text[:200]}", file=sys.stderr)
    return ok, msg_id


def main():
    print(f"🛑 Cable Daily Report — permanently disabled per user request ({datetime.now(TZ_MM).strftime('%d/%m/%Y %H:%M')} Myanmar)")
    print("✅ Cable report execution halted: no report will be sent.")
    return


if __name__ == "__main__":
    main()
