"""
daily_read_report.py
====================
Run at 20:30 Myanmar — check who has read the EOD Report message
("📋 4. Report — Daily EOD Task & Stats")
in T1 / T2 / T3 / T4 / CONTROL.

For Team groups: only count team members from sheet (col E, rows 4-59).
For CONTROL: count all group participants.

Tracks read status over 3Day / 7Day / Month like Search Stats.
Sends report to each group.
"""

import asyncio
import io
import os
import re
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
load_dotenv()
from delete_old_helper import delete_old_messages_telethon, save_msgids
from telethon.tl.functions.messages import (
    GetHistoryRequest,
    GetMessageReadParticipantsRequest,
)

# ── Config ──────────────────────────────────────────────────────
API_ID         = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH       = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_STRING = os.environ.get("TELEGRAM_SESSION", "")
MAIN_GAS_FALLBACK = "https://script.google.com/macros/s/AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA/exec"
GAS_URL = os.environ.get("APPS_SCRIPT_URL", "").strip()
if not GAS_URL or "AKfycbzGFdnE" in GAS_URL:
    GAS_URL = MAIN_GAS_FALLBACK

MYANMAR_TZ = timezone(timedelta(hours=6, minutes=30))

from tni_config import TELEGRAM_GROUPS as GROUPS

# Map team string patterns → group key
TEAM_TO_GROUP = {
    "TEAM01": "T1", "TEAM 1": "T1", "TEAM1": "T1",
    "TEAM02": "T2", "TEAM 2": "T2", "TEAM2": "T2",
    "TEAM05": "T2", "TEAM 5": "T2", "TEAM5": "T2",  # Team 5 → Team 2
    "TEAM03": "T3", "TEAM 3": "T3", "TEAM3": "T3",
    "TEAM04": "T4", "TEAM 4": "T4", "TEAM4": "T4",
}

# Dùng gviz/tq — export?format=csv trả 307 redirect từ GitHub Actions
SPREADSHEET_ID = "1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8"
SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
    "/gviz/tq?tqx=out:csv&gid=133591305"
)
HEADER_ROWS = 3
COL_A, COL_B, COL_C, COL_E = 0, 1, 2, 4

# Dùng gviz/tq — export?format=csv trả 307 redirect từ GitHub Actions
STAFF_SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
    "/gviz/tq?tqx=out:csv&gid=1684930643"
)
# Col indices trong Staff sheet (0-based)
S_COL_ID   = 0   # A: Employee ID / Telegram ID (số không đổi)
S_COL_NAME = 5   # F: Tên nhân viên (hiển thị chính thức)
S_COL_TEAM = 12  # M: Team (Team 1/2/3/4)
S_COL_EXIT = 13  # N: Ngày nghỉ / status — RỔNG = còn làm việc (active)

# Keywords to identify EOD Report message (sent around 16:00-17:30 Myanmar)
NOTE_KEYWORDS = [
    "note: above are the end-of-day work results, checks, and feedback.",
    "above are the end-of-day work results, checks, and feedback.",
    "note: above are the end-of-day work results",
    "above are the end-of-day work results",
    "above are the end of day work results",
    "above are the end-of-day",
    "daily eod task", "task & stats", "eod task",
    "4. report", "daily backlog", "daily task",   # broader match for Report 4
    "eod report", "end of day",
]

# Exclude self-generated reports from being mistaken as the Note/EOD message
EXCLUDE_KEYWORDS = [
    "6. report", "daily note read report", "read report",
    "summary report", "5. report", "daily plan report",
]
# ──────────────────────────────────────────────────────────────────

def myanmar_now() -> str:
    return datetime.now(MYANMAR_TZ).strftime("%H:%M %d/%m/%Y")

def days_ago_utc(n: int) -> datetime:
    """Midnight N days ago in Myanmar time → UTC."""
    now_mm = datetime.now(MYANMAR_TZ)
    target = (now_mm - timedelta(days=n)).replace(hour=0, minute=0, second=0, microsecond=0)
    return target.astimezone(timezone.utc)

def is_note_msg(text: str) -> bool:
    """Check if message matches EOD Report keywords and is NOT a self-report."""
    t = (text or "").lower()
    if any(ex in t for ex in EXCLUDE_KEYWORDS):
        return False
    return any(kw in t for kw in NOTE_KEYWORDS)


def get_team_members_from_sheet() -> dict:
    """
    Read sheet rows 4-59 (col A=team, B=name, C=username, E=chat_id).
    Returns: { group_key: [ {"name": str, "telegram_id": int|None, "emp_id": str}, ... ] }
    """
    result = {}
    try:
        resp = requests.get(SHEET_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str, on_bad_lines="skip")

        for idx in range(HEADER_ROWS, len(df)):
            sheet_row = idx + 1
            if sheet_row < 4 or (37 < sheet_row < 52) or sheet_row > 55:
                continue

            row = df.iloc[idx]
            col_a = str(row.iloc[COL_A]).strip() if not pd.isna(row.iloc[COL_A]) else ""
            col_b = str(row.iloc[COL_B]).strip() if not pd.isna(row.iloc[COL_B]) else ""
            col_c = str(row.iloc[COL_C]).strip() if not pd.isna(row.iloc[COL_C]) else ""
            col_e = str(row.iloc[COL_E]).strip() if not pd.isna(row.iloc[COL_E]) else ""

            if col_a.lower() in ("nan", "none", ""): col_a = ""
            if col_b.lower() in ("nan", "none", "", "0"): continue
            if col_c.lower() in ("nan", "none", ""): col_c = ""
            if col_e.lower() in ("nan", "none", "", "0"): col_e = ""

            is_tl = 52 <= sheet_row <= 55
            team_str = col_a.upper()
            if is_tl and col_c and "team leader" in col_c.lower():
                m = re.search(r'team\s*leader\s*(\d+)', col_c, re.IGNORECASE)
                if m:
                    tl_num = m.group(1)
                    team_str = f"TEAM{tl_num.zfill(2)}"

            group_key = None
            for pattern, gk in TEAM_TO_GROUP.items():
                if pattern in team_str:
                    group_key = gk
                    break

            if not group_key:
                continue

            full_name = col_b if (col_b and col_b != "0") else ""
            if not full_name and col_c:
                clean_c = col_c.replace("myt_", "").replace("myt.", "")
                clean_c = re.sub(r'\d+$', '', clean_c)
                clean_c = clean_c.replace(".", " ").replace("_", " ").title().strip()
                full_name = clean_c

            if not full_name:
                continue

            if is_tl:
                full_name = f"{full_name} (TL)"

            cid = col_e.replace(".0", "") if col_e.endswith(".0") else col_e
            telegram_id = int(cid) if (cid.lstrip("-").isdigit() and int(cid) > 0) else None

            result.setdefault(group_key, [])
            if not any(m["name"] == full_name for m in result[group_key]):
                result[group_key].append({
                    "name": full_name,
                    "telegram_id": telegram_id,
                    "emp_id": col_c or full_name,
                })

        print(f"  📋 Sheet: {sum(len(v) for v in result.values())} members across {len(result)} teams")
        for gk, members in result.items():
            print(f"     {gk}: {len(members)} members")

    except Exception as e:
        print(f"  ❌ Sheet read error: {e}")

    return result


def get_staff_from_staff_sheet() -> dict:
    """
    Đọc Staff sheet (GID 1684930643) — nguồn chính xác danh sách nhân viên.
    Filter: col N trống = còn làm việc (active). Col N có giá trị = đã nghỉ.
    Col C = Telegram User ID (số ngày vĩnh viễn, không đổi dù đổi username).

    Returns: { group_key: [ {"name": str, "telegram_id": int|None, "emp_id": str}, ... ] }
    """
    result = {}
    try:
        resp = requests.get(STAFF_SHEET_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str, on_bad_lines="skip")

        for idx in range(1, len(df)):  # bỏ dòng header (row 0)
            row = df.iloc[idx]

            def safe_col(col_idx, _row=row):
                if col_idx >= len(_row):
                    return ""
                v = str(_row.iloc[col_idx]).strip() if not pd.isna(_row.iloc[col_idx]) else ""
                return "" if v.lower() in ("nan", "none", "") else v

            # Col N: có giá trị = đã nghỉ → bỏ qua
            if safe_col(S_COL_EXIT):
                continue

            emp_id  = safe_col(S_COL_ID)
            tid_raw = safe_col(S_COL_ID)   # Col A = Telegram ID strictly
            name    = safe_col(S_COL_NAME) # Col F = Full Name strictly
            team    = safe_col(S_COL_TEAM) # Col M = Team

            if not name or not team:
                continue

            # Map team string → group key
            team_up = team.upper().replace(" ", "")
            group_key = None
            for pattern, gk in TEAM_TO_GROUP.items():
                if pattern.replace(" ", "") in team_up:
                    group_key = gk
                    break
            if not group_key:
                m_num = re.search(r'(\d+)', team)
                if m_num:
                    mapping = {"1": "T1", "2": "T2", "3": "T3", "4": "T4", "5": "T2"}
                    group_key = mapping.get(m_num.group(1))

            if not group_key:
                continue

            # Parse Telegram User ID (col A)
            tid_clean = tid_raw.replace(".0", "") if tid_raw.endswith(".0") else tid_raw
            telegram_id = int(tid_clean) if tid_clean.lstrip("-").isdigit() else None

            result.setdefault(group_key, [])
            # Dedup theo tên cột F
            if not any(s["name"] == name for s in result[group_key]):
                result[group_key].append({
                    "name":        name,       # Tên Cột F hiển thị chính thức
                    "telegram_id": telegram_id, # ID Cột A
                    "emp_id":      emp_id,
                })

        total = sum(len(v) for v in result.values())
        print(f"  📋 Staff sheet: {total} active staff across {len(result)} teams")
        for gk, members in result.items():
            in_grp = sum(1 for s in members if s["telegram_id"])
            print(f"     {gk}: {len(members)} staff | {in_grp} have Telegram ID")

    except Exception as e:
        print(f"  ❌ Staff sheet read error: {e}")

    return result

async def get_all_members(client, chat_id: int, me_id: int) -> list[dict]:
    """Get all members in group (excluding bots and self)."""
    try:
        participants = await client.get_participants(chat_id)
        members = []
        for p in participants:
            if getattr(p, "bot", False) or p.id == me_id:
                continue
            name = (getattr(p, "first_name", "") or "").strip()
            last = (getattr(p, "last_name",  "") or "").strip()
            if last:
                name = f"{name} {last}".strip()
            members.append({"id": p.id, "name": name or str(p.id)})
        return members
    except Exception as e:
        print(f"    ⚠️  get_members error: {e}")
        return []


async def get_note_msgs_period(client, chat_id: int,
                              since_utc: datetime) -> list:
    """
    Get Note messages from ANY sender from since_utc until now.
    Checks pinned message of group first, then scans history.
    Returns list of (msg, date_mm) tuples.
    """
    notes = []
    seen_ids = set()
    try:
        peer = await client.get_input_entity(chat_id)

        # 1. Check pinned message of group first
        try:
            full_chat = await client.get_entity(chat_id)
            pinned_id = getattr(full_chat, 'pinned_msg_id', None)
            if pinned_id:
                p_msgs = await client.get_messages(peer, ids=[pinned_id])
                if p_msgs and p_msgs[0] and p_msgs[0].message:
                    p_msg = p_msgs[0]
                    dt_mm = p_msg.date.astimezone(MYANMAR_TZ) if p_msg.date.tzinfo else p_msg.date.replace(tzinfo=timezone.utc).astimezone(MYANMAR_TZ)
                    notes.append((p_msg, dt_mm))
                    seen_ids.add(p_msg.id)
        except Exception:
            pass

        # 2. Scan history messages
        history = await client(GetHistoryRequest(
            peer=peer, limit=200,
            offset_date=None, offset_id=0,
            max_id=0, min_id=0, add_offset=0, hash=0,
        ))
        for msg in history.messages:
            if msg.date < since_utc:
                break
            if msg.id in seen_ids:
                continue
            if msg.message and is_note_msg(msg.message):
                dt_mm = msg.date.astimezone(MYANMAR_TZ) if msg.date.tzinfo else msg.date.replace(tzinfo=timezone.utc).astimezone(MYANMAR_TZ)
                notes.append((msg, dt_mm))
                seen_ids.add(msg.id)
    except Exception as e:
        print(f"    ⚠️  get_note_msgs error: {e}")
    return notes


async def get_reader_ids_with_time(client, chat_id: int, msg_id: int) -> dict:
    """Get {user_id: read_datetime_utc} for msg_id."""
    try:
        peer = await client.get_input_entity(chat_id)
        readers = await client(GetMessageReadParticipantsRequest(
            peer=peer, msg_id=msg_id,
        ))
        result = {}
        for r in readers:
            uid = getattr(r, "user_id", 0)
            rdate = getattr(r, "date", None)
            if uid:
                result[uid] = rdate
        return result
    except Exception as e:
        print(f"    ⚠️  get_reader_ids error: {e}")
        return {}


async def process_group(client, group_key: str, chat_id: int,
                        me_id: int, staff_by_team: dict, cycle_start: datetime, cycle_end: datetime) -> dict | None:
    """Process 1 group: check Note reads. Returns data dict."""
    print(f"\n[{group_key}] chat_id={chat_id}")

    # Lấy danh sách staff từ Staff sheet cho team này
    staff_list = staff_by_team.get(group_key, [])

    # Lấy participants thực tế của nhóm Telegram
    group_participants = await get_all_members(client, chat_id, me_id)
    participant_ids = {p["id"] for p in group_participants}
    print(f"  👥 Group participants: {len(participant_ids)}")

    # Build per_person tracking for ALL staff members in the team
    per_person = {}
    member_ids = set()
    not_in_group_names = []

    if group_key == "CONTROL":
        for p in group_participants:
            uid = p["id"]
            member_ids.add(uid)
            per_person[uid] = {"name": p["name"], "id": uid, "d0": 0, "d1": 0, "d2": 0, "d7": 0, "month": 0}
    else:
        for s in staff_list:
            name = s["name"]
            tid  = s.get("telegram_id")
            matched_id = None
            if tid and tid in participant_ids:
                matched_id = tid
            else:
                norm_n = name.lower().replace(" ", "")
                for p in group_participants:
                    p_name = p["name"].lower().replace(" ", "")
                    if norm_n and (norm_n in p_name or p_name in norm_n):
                        matched_id = p["id"]
                        break

            key = matched_id if matched_id else f"unmapped_{name}"
            if matched_id:
                member_ids.add(matched_id)
            else:
                not_in_group_names.append(name)

            per_person[key] = {
                "name": name,
                "id": matched_id,
                "d0": 0, "d1": 0, "d2": 0, "d7": 0, "month": 0
            }

    member_count = len(per_person)

    # Get Note messages from last 35 days (to cover the full cycle and rolling 7-day stats)
    since_date = days_ago_utc(35)
    note_msgs = await get_note_msgs_period(client, chat_id, since_date)

    if not note_msgs:
        print(f"  ℹ️  No Note messages found in last 35 days — skip")
        return None

    print(f"  📨 Found {len(note_msgs)} Note messages in last 35 days")

    # Categorize by period
    now_mm = datetime.now(MYANMAR_TZ)
    today_start = now_mm.replace(hour=0, minute=0, second=0, microsecond=0)
    d1_start = today_start - timedelta(days=1)
    d2_start = today_start - timedelta(days=2)
    d7_start = today_start - timedelta(days=7)

    def in_read_window(read_dt, day_start):
        """Check if read_dt is after the message was sent and within active reporting window."""
        if read_dt is None:
            return True  # no timestamp → count anyway
        if read_dt.tzinfo is None:
            read_dt = read_dt.replace(tzinfo=timezone.utc)
        read_mm = read_dt.astimezone(MYANMAR_TZ)
        start_time = day_start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = (day_start + timedelta(days=2)).replace(hour=23, minute=59, second=59, microsecond=0)
        return start_time <= read_mm <= end_time

    today_note_msg = None

    for msg, dt_mm in note_msgs:
        rid_map = await get_reader_ids_with_time(client, chat_id, msg.id)
        rid_map = {uid: t for uid, t in rid_map.items() if uid in member_ids}

        for uid, read_dt in rid_map.items():
            if uid not in per_person:
                continue
            pp = per_person[uid]

            # Only count if read during 17:30 - 20:30 of that message's day
            msg_day_start = dt_mm.replace(hour=0, minute=0, second=0, microsecond=0)
            if not in_read_window(read_dt, msg_day_start):
                continue

            if cycle_start <= dt_mm <= cycle_end:
                pp["month"] += 1

            if dt_mm >= d7_start:
                pp["d7"] += 1

            if dt_mm >= d2_start and dt_mm < d1_start:
                pp["d2"] = 1
            elif dt_mm >= d1_start and dt_mm < today_start:
                pp["d1"] = 1
            elif dt_mm >= today_start:
                pp["d0"] = 1

        if dt_mm >= today_start and today_note_msg is None:
            today_note_msg = msg

        await asyncio.sleep(0.3)

    # Sort: unread today first, then by name
    per_member = sorted(per_person.values(), key=lambda p: (p["d0"], p["name"]))

    today_read = [p["name"] for p in per_person.values() if p["d0"] == 1]
    today_unread = [p["name"] for p in per_person.values() if p["d0"] == 0]

    # Totals
    cnt_d0 = sum(1 for p in per_person.values() if p["d0"])
    cnt_d1 = sum(1 for p in per_person.values() if p["d1"])
    cnt_d2 = sum(1 for p in per_person.values() if p["d2"])

    print(f"  ✅ Today: {cnt_d0} read / {len(today_unread)} unread")

    return {
        "group_key": group_key,
        "member_count": member_count,
        "cnt_d0": cnt_d0, "cnt_d1": cnt_d1, "cnt_d2": cnt_d2,
        "per_member": per_member,
        "today_read": today_read,
        "today_unread": today_unread,
        "not_in_group": not_in_group_names,   # danh sách tên chưa join nhóm
        "note_preview": (today_note_msg.message or "")[:60].replace("\n", " ") if today_note_msg else "",
    }


def get_cycle_range(now_mm: datetime) -> tuple[datetime, datetime]:
    """
    Calculate the cycle from the 21st of the previous month to the 20th of the current month
    (or current 21st to next 20th, depending on the current date).
    """
    if now_mm.day <= 20:
        if now_mm.month == 1:
            start_year = now_mm.year - 1
            start_month = 12
        else:
            start_year = now_mm.year
            start_month = now_mm.month - 1
        
        end_year = now_mm.year
        end_month = now_mm.month
    else:
        start_year = now_mm.year
        start_month = now_mm.month
        
        if now_mm.month == 12:
            end_year = now_mm.year + 1
            end_month = 1
        else:
            end_year = now_mm.year
            end_month = now_mm.month + 1
            
    start_dt = datetime(start_year, start_month, 21, 0, 0, 0, tzinfo=MYANMAR_TZ)
    end_dt = datetime(end_year, end_month, 20, 23, 59, 59, tzinfo=MYANMAR_TZ)
    return start_dt, end_dt


async def main():
    print(f"[{myanmar_now()}] 🚀 Daily Note Read Report starting...")

    # Read staff from Task remain sheet (nguồn chính xác danh sách nhân viên 4 Team)
    print(f"[{myanmar_now()}] 📋 Reading staff list from Task remain sheet...")
    staff_by_team = get_team_members_from_sheet()

    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

    async with client:
        me = await client.get_me()
        print(f"[{myanmar_now()}] 🔑 Logged in: @{me.username} ({me.first_name})")

        now_mm = datetime.now(MYANMAR_TZ)
        cycle_start, cycle_end = get_cycle_range(now_mm)
        cycle_str = f"{cycle_start.strftime('%d/%m/%y')}-{cycle_end.strftime('%d/%m/%y')}"
        cycle_short_str = f"{cycle_start.strftime('%d/%m')}-{cycle_end.strftime('%d/%m')}"

        # Collect data from all groups
        all_results = {}  # group_key -> data
        for group_key, chat_id in GROUPS.items():
            data = await process_group(client, group_key, chat_id, me.id, staff_by_team, cycle_start, cycle_end)
            if data:
                all_results[group_key] = data

        if not all_results:
            print("⚠️  No data to report")
            return

        date_str = now_mm.strftime("%d/%m/%Y")
        now_str  = myanmar_now()
        divider  = "━" * 30

        # Helper: build per-member lines with ❓ for members not joined/mapped yet
        def member_lines(per_member):
            lines = []
            for p in per_member:
                if p["d0"]:
                    icon = "✅"
                elif not p.get("id"):
                    icon = "❓"  # Chưa tham gia / Chưa khớp ID Telegram
                else:
                    icon = "❌"  # Đã vào nhóm nhưng chưa đọc bài
                lines.append(
                    f"  {icon} {p['name']}: "
                    f"3Day:{p['d0']}/{p['d1']}/{p['d2']}  "
                    f"7Day:{p['d7']}  Month:{p['month']}"
                )
            return lines

        # ── 1. Send per-team report to each Team group ──
        for gk in ("T1", "T2", "T3", "T4"):
            r = all_results.get(gk)
            if not r:
                continue

            cnt_unread = sum(1 for p in r["per_member"] if not p["d0"] and p.get("id"))
            cnt_not_joined = sum(1 for p in r["per_member"] if not p.get("id"))

            note_line = f"📝 Note: {r['note_preview']}...\n" if r["note_preview"] else ""
            tl = [
                f"📋 6. Report — Daily Note Read Report — {gk}",
                f"📅 {date_str}  |  🕐 {now_str}",
                f"⏰ Read Window: 04:00 - 23:59 Myanmar",
                f"📅 Cycle: {cycle_str}",
                f"📌 Shows who read the Note message during the active window (04:00 - 23:59) today.",
            ]
            if note_line:
                tl.append(f"📝 Note: {r['note_preview']}...")
            tl.append(divider)
            tl.append(f"👥 Team Members: {r['member_count']}  |  "
                       f"✅ Read: {r['cnt_d0']}  |  ❌ Unread: {cnt_unread}  |  ❓ Not Joined: {cnt_not_joined}")
            tl.append(divider)
            tl.extend(member_lines(r["per_member"]))
            tl.append(divider)

            chat_id = GROUPS[gk]
            try:
                await delete_old_messages_telethon(client, chat_id, GAS_URL, f"READREPORT_{gk}")
            except Exception as del_e:
                print(f"⚠️ Delete old report error {gk}: {del_e}")
            try:
                async for old_m in client.iter_messages(chat_id, limit=30):
                    if old_m.text and ("6. Report — Daily Note Read Report" in old_m.text or "Daily Note Read Report" in old_m.text):
                        try:
                            await client.delete_messages(chat_id, [old_m.id], revoke=True)
                        except Exception: pass
            except Exception: pass
            sent = await client.send_message(chat_id, "\n".join(tl))
            save_msgids(GAS_URL, f"READREPORT_{gk}", [sent.id])
            print(f"📤 Report sent to {gk}")
            await asyncio.sleep(1)

        # ── 2. Send consolidated report to CONTROL ──
        lines = [
            f"📋 6. Report — Daily Note Read Report — Summary",
            f"📅 {date_str}  |  🕐 {now_str}",
            f"⏰ Read Window: 04:00 - 23:59 Myanmar",
            f"📅 Cycle: {cycle_str}",
            f"📌 Shows who read the Note message during the active window (04:00 - 23:59) today.",
            divider,
        ]

        # Note preview
        for r in all_results.values():
            if r["note_preview"]:
                lines.append(f"📝 Note: {r['note_preview']}...")
                lines.append("")
                break

        # Per-group with per-person details
        for gk, r in all_results.items():
            cnt_unread = sum(1 for p in r["per_member"] if not p["d0"] and p.get("id"))
            cnt_not_joined = sum(1 for p in r["per_member"] if not p.get("id"))
            lines.append(
                f"🏷️ {gk}  |  👥 {r['member_count']}  |  "
                f"✅ {r['cnt_d0']}  ❌ {cnt_unread}  ❓ {cnt_not_joined}"
            )
            lines.extend(member_lines(r["per_member"]))

            # Phần "Chưa có trong nhóm" cho CONTROL
            if r.get("not_in_group"):
                lines.append(f"⚠️ Not in Group yet ({len(r['not_in_group'])} members):")
                for name in r["not_in_group"]:
                    lines.append(f"  • {name}")

            lines.append("")

        lines.append(divider)

        # Grand totals
        total_members = sum(r["member_count"] for r in all_results.values())
        total_read = sum(r["cnt_d0"] for r in all_results.values())
        total_unread = sum(len(r["today_unread"]) for r in all_results.values())
        lines.append(
            f"📊 Total: {total_members} members  |  "
            f"✅ Read: {total_read}  |  ❌ Unread: {total_unread}"
        )
        lines.append(divider)

        report = "\n".join(lines)
        control_id = GROUPS["CONTROL"]
        try:
            await delete_old_messages_telethon(client, control_id, GAS_URL, "READREPORT_CONTROL")
        except Exception as del_ctrl_e:
            print(f"⚠️ Delete old report CONTROL error: {del_ctrl_e}")
        try:
            async for old_m in client.iter_messages(control_id, limit=30):
                if old_m.text and ("6. Report — Daily Note Read Report" in old_m.text or "Daily Note Read Report" in old_m.text):
                    try:
                        await client.delete_messages(control_id, [old_m.id], revoke=True)
                    except Exception: pass
        except Exception: pass
        sent = await client.send_message(control_id, report)
        save_msgids(GAS_URL, "READREPORT_CONTROL", [sent.id])
        print(f"📤 Consolidated report sent to CONTROL SITE")

        # ── 3. Ghi dữ liệu lượt đọc vào Google Sheet tab 'Read Group' ──
        log_read_group_to_gas(all_results, date_str, now_str)

    print(f"\n[{myanmar_now()}] 🎉 Complete!")


def log_read_group_to_gas(all_results: dict, date_str: str, now_str: str):
    """POST collected read statistics to GAS to record into 'Read Group' sheet tab."""
    if not GAS_URL:
        return
    records = []
    for gk, r in all_results.items():
        note_msg = r.get("note_preview", "")
        for p in r.get("per_member", []):
            records.append({
                "date": date_str,
                "time": now_str,
                "team": gk,
                "name": p["name"],
                "telegram_id": str(p.get("id", "")),
                "status": "Read" if p["d0"] == 1 else "Unread",
                "trend_3day": f"{p['d0']}/{p['d1']}/{p['d2']}",
                "count_7day": p["d7"],
                "count_month": p["month"],
                "note_msg": note_msg,
            })
    if not records:
        return
    try:
        resp = requests.post(GAS_URL, json={
            "action": "log_read_group",
            "records": records
        }, timeout=30)
        print(f"  💾 Logged {len(records)} records to 'Read Group' tab on Google Sheets")
    except Exception as e:
        print(f"  ⚠️  Failed to log to Read Group tab: {e}")


if __name__ == "__main__":
    asyncio.run(main())


