import os
import io
import logging
import asyncio
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta
from telegram import Bot
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template_string
from apscheduler.schedulers.background import BackgroundScheduler

# Load environment variables
load_dotenv()

# Get tokens and URLs
SEND_BOT_TOKEN = os.getenv("SEND_BOT_TOKEN", "")
REPORT_TASK_BOT_TOKEN = os.getenv("REPORT_TASK_BOT_TOKEN", "")
TECHNICAL_DEP_BOT_TOKEN = os.getenv("TECHNICAL_DEP_BOT_TOKEN", "")
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "")

# Spreadsheet constants (same as cron_send.py)
SPREADSHEET_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Xx3u-UXhFgpI8"
SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}" 
    "/gviz/tq?tqx=out:csv&gid=133591305&range=A1:E90"
)
TZ_MM = timezone(timedelta(hours=6, minutes=30))
HEADER_ROWS = 2
COL_A, COL_B, COL_C, COL_D, COL_E = 0, 1, 2, 3, 4

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper functions (copied from cron_send.py)
# ---------------------------------------------------------------------------

def safe(row, idx):
    try:
        v = row.iloc[idx]
        s = "" if pd.isna(v) else str(v).strip()
        return "" if s.lower() in ("nan", "none", "") else s
    except Exception:
        return ""


def call_apps_script(payload, timeout=30):
    if not APPS_SCRIPT_URL:
        return {}
    try:
        resp = requests.post(APPS_SCRIPT_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Apps Script error: {e}")
        return {}


def get_asset_stats():
    data = call_apps_script({"action": "get_asset_stats"}, timeout=120)
    if data.get("status") != "ok":
        logger.warning(f"get_asset_stats failed: {data.get('message', 'unknown')}")
        return {}
    return data


def get_report_data():
    data = call_apps_script({"action": "get_report_data"}, timeout=120)
    if data.get("status") != "ok":
        logger.warning(f"get_report_data failed: {data.get('message', 'unknown')}")
        return {}
    return data


def build_search_summary(now_str, report_data):
    team_summary = report_data.get("teamSummary", [])
    grand = report_data.get("grandTotal", {})
    if not team_summary:
        return ""
    TEAM_SHORT = {
        "MYT_TNI_TEAM01_Dawei": "Team1(Dawei)",
        "MYT_TNI_TEAM02_Myeik": "Team2(Myeik)",
        "MYT_TNI_TEAM03_Bokpyin": "Team3(Bokpyin)",
        "MYT_TNI_TEAM04_Kawthoung": "Team4(Kawthoung)",
    }
    lines = [f"🔍 Search Stats – {now_str}"]
    for ts in team_summary:
        tm = TEAM_SHORT.get(ts.get("team", ""), ts.get("team", ""))
        lines.append(
            f"🏷️ {tm}: "
            f"3Day:{ts.get('d2',0)}/{ts.get('d1',0)}/{ts.get('today',0)} "
            f"7Day:{ts.get('week',0)} Month:{ts.get('month',0)}"
        )
    lines.append(
        f"📊 Total: "
        f"3Day:{grand.get('d2',0)}/{grand.get('d1',0)}/{grand.get('today',0)} "
        f"7Day:{grand.get('week',0)} Month:{grand.get('month',0)}"
    )
    return "\n".join(lines)


def build_asset_msg(now_str, asset_data):
    if not asset_data.get("actionTypes"):
        return ""
    action_types = asset_data.get("actionTypes", [])
    teams = asset_data.get("teams", [])
    stats = asset_data.get("stats", {})
    grand = asset_data.get("grandTotal", {})
    TEAM_SHORT = {
        "MYT_TNI_TEAM01_Dawei": "Team1(Dawei)",
        "MYT_TNI_TEAM02_Myeik": "Team2(Myeik)",
        "MYT_TNI_TEAM03_Bokpyin": "Team3(Bokpyin)",
        "MYT_TNI_TEAM04_Kawthoung": "Team4(Kawthoung)",
    }
    def fmt(s):
        total = s.get("total", 0)
        done = s.get("done", 0)
        return f"{total} Done {done}"
    def fmt_period(s):
        return (
            f"3Day:{s.get('d0',0)}/{s.get('d1',0)}/{s.get('d2',0)} "
            f"7Day:{s.get('d6',0)} Month:{s.get('d15',0)}"
            f" All:{s.get('total',0)}/{s.get('done',0)}"
        )
    lines = [f"📦 Thống kê Asset – {now_str}"]
    for tm in teams:
        tm_short = TEAM_SHORT.get(tm, tm)
        parts = [f"{at}: {fmt(stats.get(at,{}).get(tm,{}))}" for at in action_types]
        lines.append(f"🏷️ {tm_short}: " + " | ".join(parts))
        team_total = {"d0":0,"d1":0,"d2":0,"d6":0,"d15":0,"total":0,"done":0}
        for at in action_types:
            s = stats.get(at, {}).get(tm, {})
            for k in team_total:
                team_total[k] += s.get(k, 0)
        lines.append(f"   📅 {fmt_period(team_total)}")
    parts = [f"{at}: {fmt(grand.get(at,{}))}" for at in action_types]
    lines.append(f"📊 Total: " + " | ".join(parts))
    g_period = {"d0":0,"d1":0,"d2":0,"d6":0,"d15":0,"total":0,"done":0}
    for at in action_types:
        g = grand.get(at, {})
        for k in g_period:
            g_period[k] += g.get(k, 0)
    lines.append(f"📅 Total {fmt_period(g_period)}")
    return "\n".join(lines)

async def send_msg(bot, cid, text, label=""):
    MAX = 4000
    try:
        if len(text) <= MAX:
            await bot.send_message(chat_id=cid, text=text)
        else:
            parts = []
            current = ""
            for line in text.split("\n"):
                if len(current) + len(line) + 1 > MAX:
                    parts.append(current)
                    current = line
                else:
                    current += ("\n" if current else "") + line
            if current:
                parts.append(current)
            for p in parts:
                await bot.send_message(chat_id=cid, text=p)
                await asyncio.sleep(0.3)
        logger.info(f"✅ {label} → {cid}")
        return True
    except Exception as e:
        logger.error(f"❌ {label} → {cid}: {e}")
        return False

async def _run_send_all():
    now = datetime.now(TZ_MM)
    now_str = now.strftime("%d/%m/%Y %H:%M")
    logger.info(f"🚀 Send all start – {now_str}")
    resp = requests.get(SHEET_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str, on_bad_lines="skip")
    logger.info(f"Sheet rows: {len(df)}")
    all_rows = []
    for idx, row in df.iterrows():
        sheet_row = idx + 1
        if sheet_row <= HEADER_ROWS:
            continue
        content = safe(row, COL_D)
        cid_raw = safe(row, COL_E)
        col_c = safe(row, COL_C)
        cid = cid_raw[:-2] if cid_raw.endswith(".0") else cid_raw
        if not cid or cid == "-" or not cid.lstrip("-").isdigit():
            continue
        all_rows.append((sheet_row, content, cid, col_c))
    asset_data = get_asset_stats()
    asset_msg = build_asset_msg(now_str, asset_data)
    report_data = get_report_data()
    search_msg = build_search_summary(now_str, report_data)
    mgmt_parts = [f"📊 Báo cáo tổng hợp – {now_str}", "━━━━━━━━━━━━━━━━━━━━"]
    if asset_msg:
        mgmt_parts.append(asset_msg)
        mgmt_parts.append("━━━━━━━━━━━━━━━━━━━━")
    if search_msg:
        mgmt_parts.append(search_msg)
        mgmt_parts.append("━━━━━━━━━━━━━━━━━━━━")
    team_leader_content = []
    for idx, row in df.iterrows():
        sheet_row = idx + 1
        if sheet_row <= HEADER_ROWS:
            continue
        col_c = safe(row, COL_C)
        if col_c and "team leader" in col_c.lower():
            team_name = safe(row, COL_A) or safe(row, COL_B) or "Unknown"
            team_leader_content.append({"team": team_name, "name": safe(row, COL_B), "content": safe(row, COL_D)})
    if team_leader_content:
        mgmt_parts.append("👑 Team Leader Reports:")
        for tl in team_leader_content:
            txt = tl["content"]
            short = txt[:600] + "..." if len(txt) > 600 else txt
            mgmt_parts.append(f"\n🏷️ {tl['team']}:\n{short}")
    mgmt_report = "\n".join(mgmt_parts)
    groups = {}
    for sheet_row, content, cid, col_c in all_rows:
        if 4 <= sheet_row <= 32 and REPORT_TASK_BOT_TOKEN:
            token = REPORT_TASK_BOT_TOKEN
            bot_label = "@TNIREPORTTASK"
        elif 75 <= sheet_row <= 87 and TECHNICAL_DEP_BOT_TOKEN:
            token = TECHNICAL_DEP_BOT_TOKEN
            bot_label = "@TNITECHNICAL"
        elif SEND_BOT_TOKEN:
            token = SEND_BOT_TOKEN
            bot_label = "SEND_BOT"
        else:
            continue
        if 60 <= sheet_row <= 74:
            msg = mgmt_report
        elif 75 <= sheet_row <= 87:
            parts = []
            if content:
                parts.append(f"📋 ကျန်ရှိသောလုပ်ငန်းများ သတိပေးချက် – {now_str}\n━━━━━━━━━━━━━━━━━━━━\n{content}\n━━━━━━━━━━━━━━━━━━━━")
            if asset_msg:
                parts.append(asset_msg)
            if search_msg:
                parts.append(search_msg)
            msg = "\n".join(parts) if parts else None
        elif content:
            msg = (
                f"📋 ကျန်ရှိသောလုပ်ငန်းများ သတိပေးချက် – {now_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{content}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ ကျေးဇူးပြု၍ အမြန်ဆောင်ရွက်ပေးပါ။"
            )
        else:
            continue
        if msg:
            groups.setdefault(token, []).append((sheet_row, msg, cid, bot_label))
    ok = fail = 0
    for token, items in groups.items():
        bot_name = items[0][3] if items else "BOT"
        logger.info(f"--- {bot_name}: {len(items)} messages ---")
        async with Bot(token=token) as bot:
            for sheet_row, msg, cid, label in items:
                result = await send_msg(bot, cid, msg, f"{label} row{sheet_row}")
                if result:
                    ok += 1
                else:
                    fail += 1
                await asyncio.sleep(0.4)
    logger.info(f"📊 Done: ✅{ok} | ❌{fail}")
    return {"sent": ok, "failed": fail}

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<html lang='vi'>
<head>
  <meta charset='utf-8'>
  <title>Gửi tin Telegram</title>
  <link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap' rel='stylesheet'>
  <style>
    body {font-family: 'Inter', sans-serif; background: linear-gradient(135deg, #1e1e2f, #282a36); color: #f0f0f0; display:flex; flex-direction:column; align-items:center; padding:2rem;}
    .card {background: rgba(255,255,255,0.08); backdrop-filter: blur(8px); border-radius: 12px; padding: 2rem; max-width: 480px; width:100%; box-shadow: 0 8px 32px rgba(0,0,0,0.4);}
    h1 {margin-top:0; font-weight:600; font-size:1.8rem; text-align:center;}
    button {background: #4e9af1; border:none; color:#fff; padding:0.8rem 1.5rem; border-radius:8px; font-size:1rem; cursor:pointer; transition:background 0.2s;}
    button:hover {background:#3b7dd8;}
    #log {margin-top:1rem; font-size:0.9rem; line-height:1.4; white-space:pre-wrap; max-height:200px; overflow-y:auto;}
  </style>
</head>
<body>
  <div class='card'>
    <h1>Gửi tin nhắn Telegram</h1>
    <p>Nhấn nút dưới đây để gửi **tất cả** tin nhắn một lần.</p>
    <button onclick='sendAll()'>🚀 Gửi ngay</button>
    <div id='log'></div>
  </div>
  <script>
    function log(msg){
      const el=document.getElementById('log');
      el.textContent+=msg+'\n';
    }
    async function sendAll(){
      log('⏳ Đang gửi...');
      try{
        const resp = await fetch('/send_all', {method:'POST'});
        const data = await resp.json();
        log('✅ Hoàn thành: '+data.sent+' tin đã gửi, '+data.failed+' lỗi');
      }catch(e){
        log('❌ Lỗi: '+e);
      }
    }
  </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/send_all', methods=['POST'])
def trigger_send():
    result = asyncio.run(_run_send_all())
    return jsonify(result)

# Schedule daily automatic send at 17:30
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: asyncio.run(_run_send_all()), 'cron', hour=17, minute=30, id='daily_send')
scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
