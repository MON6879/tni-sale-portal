# TNI Bot System Documentation
> **Last Updated:** 30/07/2026 13:42 Myanmar  
> **Maintainer:** Phong Ha Duc  
> **Repo:** github.com/phonghdpxd-cmd/tni-bot

---

## 🤖 System Bot Routing & Webhook Map (100% Online Cloud)

| Bot # | Bot Name & Username | Server / Cloud Environment | Webhook URL / Trigger | Key Functions |
|---|---|---|---|---|
| **Bot 1 & 3** | **TNI Search & Daily Result Bot**<br>`@SEARCHTNITASKWOBOT`<br>(`3. TNI PERSONAL FIND TASK...`) | **Vercel Cloud Serverless** | `https://tni-bot.vercel.app/api/search_bot` | • `/daily` ➔ Mẫu `Daily result: DD/MM/YYYY`<br>• Tra cứu Info trạm (`Info: TNIxxxx`, `info: TNIxxxx`) ➔ Thông tin Site/Cable/Gpon/DIA từ tab `Name Site / Site / Cable / Gpon / DIA`<br>• Tra cứu trạm (`TNIxxxx`, `/tni TNIxxxx`) ➔ Chi tiết Task/WO từ tab `Tên Sum WO`<br>• Tra cứu Clear Site (`CLEAR TNIxxxx`) ➔ Lịch sử Clear trạm từ `Search Site Clear`<br>• Tra cứu Not Close (`T1notclose`..`T4notclose`) & Wait CD (`T1waitcd`..`T4waitcd`)<br>• **Cơ chế Tự chữa lành (Self-Healing)**: Trả về HTTP 200 OK trong 1ms + Tự động khóa lại Webhook ngầm |
| **Bot Asset** | **TNI Asset & Cable Collector Bot** | **Vercel Cloud Serverless** | `https://tni-bot.vercel.app/api/collector` | • Quản lý lệnh Order/Revoke/Move/Export/Done/Inventory tài sản |
| **Bot 2** | **TNI Auto Report Daily Bot**<br>`@TNIREPORTTASK_BOT`<br>(`2. TNI Auto Report Daily`) | **GitHub Actions Cloud 24/7** | Cron Workflows (`daily_plan_report.yml`, `daily_read_report.yml`) | • Báo cáo Kế hoạch (Plan Report 17:30 MMT)<br>• Báo cáo Đọc Note (09:30, 14:00, 16:00, 21:00 MMT)<br>• Báo cáo Công việc ngày (17:00 MMT) |
| **Bot 5** | **TNI Site Down Cell Alarm Bot**<br>`@TNISITEDOWN_BOT`<br>(`5T TNI_SITE_DOWN_CELL_ALARM`) | **Google Apps Script Cloud** | Project: `site_down_v2.gs` (1-min trigger) | • Tin 1 (Chi tiết Site Down từ Cột C)<br>• Tin 2 (SUMMARY từ AW7:AZ15)<br>• **Quy tắc tuyệt đối**: Tin 2 SUMMARY LUÔN ÉP BẮN NỐI ĐUÔI Ở DƯỚI CÙNG ĐÁY CHAT bên dưới Tin 1 |
| **Bot Attendance** | **TNI Attendance Bot**<br>`@TNIATTENDANCE_BOT` | **Google Apps Script Cloud** | Project: `TNI attendance.js` (Web App `/exec`) | • Đọc ảnh điểm danh & Nhận diện khuôn mặt Gemini 2.5 Flash<br>• Tự lưu ảnh vào thư mục `2.11 Attendance photo`<br>• Tự cập nhật tab `General`<br>• Tự động phát báo cáo 4 mốc giờ (08:45, 12:15, 14:15, 17:15 MMT) |
| **Bot 9** | **TNI Request Refuel Bot**<br>`@TNI_FUEL`<br>(`9 TNI REQUEST REFUEL`) | **GitHub Actions Cloud 24/7** | Cron Workflow (`refuel_report.yml`) | • Báo cáo Request Refuel tự động 2 mốc giờ (**06:15 MMT** & **16:20 MMT**)<br>• **Thu thập 100% dữ liệu thô** (lưu đủ các yêu cầu trùng do chưa thực hiện theo kế hoạch cũ)<br>• Khi lập báo cáo tổng hợp: Tự động **lọc BỎ TRÙNG** theo mã trạm/máy phát để so sánh đối chiếu chuẩn xác giữa **Kế hoạch (Plan)** và **Yêu cầu (Request)** |

---

## 🎨 Master Standard Team Color Palette (Quy chuẩn bảng màu Team)

| Team Name | Team Region | Standard Emoji Color | Color Hex Reference |
|---|---|---|---|
| **Team 1** | Dawei | 🟠 **Orange (Chấm Cam)** | `#FB8C00` |
| **Team 2** | Myeik | 🔵 **Blue (Chấm Xanh Dương)** | `#1E88E5` |
| **Team 3** | Bokpyin | 🟢 **Green (Chấm Xanh Lá)** | `#43A047` |
| **Team 4** | Kawthoung | 🟡 **Yellow (Chấm Vàng)** | `#FDD835` |

> 📌 **Quy tắc tuyệt đối**: Toàn bộ hệ thống Bot (`Bot 1/3`, `Bot 2`, `Bot 5 Site Down`, `Bot 9 Refuel`, Apps Script và Python) đều tuân thủ 100% quy chuẩn bảng màu này. Không thay đổi màu đại diện giữa các Team.

---

## 🏗️ Architecture Overview

```
Google Sheets (Data Source)
    ↓ CSV export / Apps Script API
cron_send.py (17:00 Myanmar)          ← GitHub Actions: daily_reports.yml (daily_task)
    ↓ Bot API (SEND_BOT_TOKEN)
Telegram Groups (T1, T2, T3, T4, CONTROL)

daily_read_report.py (20:30 Myanmar)  ← GitHub Actions: daily_read_report.yml
    ↓ Telethon (User Account API)
Telegram Groups (per-team + consolidated to CONTROL)
```

---

## 📁 Core Files

### 1. `cron_send.py` — Daily Task Report (17:00 Myanmar)
- **Trigger:** GitHub Actions `daily_task.yml` (workflow_dispatch from GAS relay)
- **Schedule:** 17:00 Myanmar = 10:30 UTC
- **Bot:** `@TNIREPORTTASK_BOT` (SEND_BOT_TOKEN)
- **What it sends:**

#### Per Team Group (T1, T2, T3, T4):
```
𝗥𝗲𝗽𝗼𝗿𝘁 Team1 Dawei – 24/06/2026 17:30
━━━━━━━━━━━━━━━━━━━━
👤 ▸ Employee Name
  [7-day task results, WO details, alarms...]
━━━━━━━━━━━━━━━━━━━━
📦 Asset: Order: 1 /1 | Revoke: 0 /0 | ...
📅 3Day: 0/0/0 7Day: 1 Month: 1
🔍 Search: 3Day:0/0/0 7Day:0 Month:0
🔍 Search per member (X not searched today):
  ❌ Name1: 3Day:0/0/0 7Day:2 Month:8
  ✅ Name2: 3Day:1/1/1 7Day:7 Month:25
━━━━━━━━━━━━━━━━━━━━
👥 Total: 8 members
```

#### CONTROL Group (5 TNI TECHNICA DEP CONTROL SITE):
- **Asset Stats** — all teams combined with 3Day/7Day/Month
- **Summary Report** — all TL reports + Search Stats (all teams)

### 2. `daily_read_report.py` — Note Read Report (10:00, 14:00 & 20:30 Myanmar)
- **Trigger:** GitHub Actions `daily_reports.yml` (cron + workflow_dispatch)
- **Schedule:** 10:00 sáng, 14:00 chiều & 20:30 tối Myanmar (03:30, 07:30 & 14:00 UTC)
- **API:** Telethon (TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION under `@phongha79`)
- **Tracks:** Who read the **Note message** ("Note: Above are the end-of-day work results, checks, and feedback.")
- **Read Window:** 04:00 - 23:59 Myanmar cutoff active window today
- **Member Source:** Staff Sheet (GID 1684930643) for Teams, group participants for CONTROL

#### Per Team Group (T1, T2, T3, T4):
```
📋 6. Report — Daily Note Read Report — T1
📅 24/06/2026  |  🕐 20:30
⏰ Read Cutoff: 20:25 Myanmar
📝 Note: Team leader and Staff control Site down...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 Team Members: 8  |  ✅ Read: 6  |  ❌ Unread: 2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ❌ Name1: 3Day:0/0/0  7Day:2  Month:8
  ❌ Name2: 3Day:1/1/0  7Day:5  Month:15
  ✅ Name3: 3Day:1/1/1  7Day:7  Month:25
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### CONTROL Group — Consolidated:
```
👁 NOTE READ REPORT — Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏷️ T1  |  👥 8  |  ✅ 6  ❌ 2
  ❌ Name1: 3Day:0/0/0  7Day:2  Month:8
  ✅ Name3: 3Day:1/1/1  7Day:7  Month:25
🏷️ T2  |  👥 12  |  ✅ 10  ❌ 2
  ...
🏷️ CONTROL  |  👥 13  |  ✅ 11  ❌ 2
  ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Total: 44 members  |  ✅ Read: 37  |  ❌ Unread: 7
```

### 3. `apps_script_collector.js` — Google Apps Script Data Collector
- **Deployed as:** Web App (Google Apps Script)
- **URL:** Set in `APPS_SCRIPT_URL` secret in main repo
- **Returns JSON** with: employees, leaders, teamSummary, searchStats, taskSummary, asset data
- **Per-person search fields:** `search_today`, `search_d1`, `search_d2`, `search_week`, `search_month`
- **Per-team summary:** `today`, `d1`, `d2`, `week`, `month`
- ⚠️ **Must deploy manually** via Google Apps Script Editor → Deploy → New version

### 3a. `site_down_v2.gs` — Standalone Site Down Web App
- **Deployed as:** Standalone Web App (Google Apps Script project: "TNI Site Down Bot")
- **URL:** Set in `SD_APPS_SCRIPT_URL` secret in `TNI-SITE-DOWN` repo
- **Functions:** Standard entry points `doPost` (receives raw text from Python, writes to Col A, triggers `checkAndSend(true)`) and `doGet`
- **Trigger:** Runs `checkAndSend` trigger every 1 minute, which gates execution to exactly minutes `:08` and `:38` between `03:38` and `22:08` Myanmar Time.
- **Key decoupling:** Has no dependencies on `apps_script_collector.gs` and runs completely independently.

### 4. `check_read_status.py` — Quick Read Check (manual)

### 5. `daily_plan_report.py` — Daily Plan Collection & Report (3 modes: EOD 17:00, Update 21:00, Morning 07:00)
- **Trigger:** GitHub Actions `daily_plan_report.yml` (cron + workflow_dispatch)
- **Schedule:** 17:30 Myanmar = 11:00 UTC
- **API:** Telethon (read messages) + SEND_BOT (send reports) + Apps Script (sheet I/O)
- **Sheet:** `1C8hU8SXpOdq-v6z7iLGoqwDJmO9DYudZ3rhflb7LC8Y` (cùng spreadsheet Daily Report)
- **Tab:** "Team leader assign Plan" (GID: 853981745)
- **Collects:** Any message containing "Daily Plan" from T1/T2/T3/T4 groups
- **Columns:** A=REF, B=Date, C=Team, D=Daily Plan, E=Daily Report results (B:S), F=Comparison
- **Comparison:** Extract TNI site codes from Plan vs Daily Report → done/remaining count
- **Reports:** 3Day/7Day/Month stats + Plan vs Actual comparison

#### Per Team Group (T1, T2, T3, T4):
```
📋 DAILY PLAN REPORT — Team4 Kawthoung
📅 26/06/2026  |  🕐 17:30
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Plan Stats: 3Day: 1/1/1 | 7Day: 7 | Month: 25

📝 Today's Plan:
──────────
I. Hot task Rescue Cell down: TNI0052, TNI0288

📊 Plan vs Actual:
📋 Plan: 8 stations
✅ Done: 5 stations (62%)
⏳ Remaining: 3 stations
Missing: TNI0052, TNI0185, TNI0058
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### CONTROL Group — Consolidated:
```
📋 DAILY PLAN REPORT — Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏷️ Team1 Dawei:
   Plan: 10 | Done: 8 (80%) | Remain: 2
   3Day: 1/1/1 | 7Day: 7 | Month: 25
🏷️ Team2 Myeik:
   ❌ No plan today
   3Day: 0/0/0 | 7Day: 3 | Month: 15
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Total: Plan: 24 | Done: 19 (79%) | Remain: 5
📊 3Day: 1/1/1 | 7Day: 10 | Month: 40
```

- One-time check: who read last message in each group
- Uses Telethon

### 6. `backlog_send.py` — Daily Backlog Report (17:10 Myanmar)
- **Trigger:** GitHub Actions `daily_task.yml` (runs right after `cron_send.py` or manually)
- **Schedule:** 17:10 Myanmar = 10:40 UTC
- **Bot:** `@TNIREPORTTASK_BOT` (SEND_BOT_TOKEN)
- **What it sends:**
  - **Report 2 (sent first):** Category/Description backlog details by columns K:L and M:P.
  - **Report 1 (sent second):** Task progress backlog details by columns C and D:H (appending Team 5 to Team 2).
  - **Report 3 (sent third):** Generator Materials Summary (KVA filter capacities, oil/coolant plans, stocks and differences) grouped separately by sub-team (e.g., `T3`, `T3 S1` separately), highlighting numbers > 0 with a blue indicator (`🔵`).
- **Key Features:**
  - **Message Deletion Isolation:** Deletes its own previous backlog messages (using keys like `BACKLOG_TEAM_T1`, etc.) via the Apps Script helper API before sending new ones, ensuring they are independent and not touched/deleted by `cron_send.py` (freezing).
  - **No CONTROL Group Send:** Only sends reports to the respective Team groups (T1, T2, T3, T4), never to the CONTROL group.

---

## 📡 Telegram Groups & IDs

| Group | Chat ID | Content |
|---|---|---|
| **TNI TEAM 1 PLAN - ALARM** (Dawei) | `-1004215695747` | Per-team task & plan report |
| **TNI TEAM 2 PLAN - ALARM** (Myeik, includes Team 5) | `-1004480845549` | Per-team task & plan report |
| **TNI TEAM 3 PLAN - ALARM** (Bokpyin) | `-1004369170658` | Per-team task & plan report |
| **TNI TEAM 4 PLAN - ALARM** (Kawthoung) | `-1004293741999` | Per-team task & plan report |
| **5 TNI TECHNICA DEP CONTROL SITE** | `-5251698940` | Consolidated reports |

---

## 🤖 Bots

| Bot | Username | Token Secret | Used In |
|---|---|---|---|
| **SEND_BOT** | `@TNIREPORTTASK_BOT` ("2. TNI Auto Report Daily") | `SEND_BOT_TOKEN` | cron_send.py |
| **Telethon User Account** | Personal account | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` | daily_read_report.py, check_read_status.py |

---

## 📊 Google Sheet Structure

**Sheet ID:** `1Etd2PmbY5LgPaYhkdykT7KYXZHhB-_Qx3u-UXhFgpI8`  
**GID:** `133591305`

| Column | Field | Used For |
|---|---|---|
| **A** (col 0) | Team name (e.g., `MYT_TNI_TEAM01_Dawei`) | Team mapping |
| **B** (col 1) | Employee name | Display name |
| **C** (col 2) | Role (e.g., `team leader 1`) | TL detection |
| **E** (col 4) | Telegram Chat ID | Read tracking, search tracking |

- **Rows 4-32:** Employees (FT)
- **Rows 33-59:** Team Leaders (TL)
- **Header rows:** 1-3 (skipped)

### Team Mapping

| Sheet Team Pattern | Group Key | Group |
|---|---|---|
| `TEAM01`, `TEAM 1`, `TEAM1` | T1 | TNI TEAM 1 (Dawei) |
| `TEAM02`, `TEAM 2`, `TEAM2` | T2 | TNI TEAM 2 (Myeik) |
| `TEAM05`, `TEAM 5`, `TEAM5` | T2 | → Merged into Team 2 |
| `TEAM03`, `TEAM 3`, `TEAM3` | T3 | TNI TEAM 3 (Bokpyin) |
| `TEAM04`, `TEAM 4`, `TEAM4` | T4 | TNI TEAM 4 (Kawthoung) |

---

## ⏰ Daily Schedule (Myanmar Time)

| Time | Script | Workflow / Input | What |
|---|---|---|---|
| **07:00 & 16:00** | `cron_send.py` + `backlog_send.py` | `daily_reports.yml` (`daily_task`) | Reports 1-4: Daily EOD Task + Auto-Note H2 + Search reports (Deletes old before send) |
| **16:00** | `daily_bod_assign.py` | `daily_reports.yml` (`bod_assign`) | Report 2: BOD-assigned task statistics (Consolidated) to CONTROL |
| **16:00** | `daily_plan_report.py --mode eod` | `daily_reports.yml` (`plan_eod`) | Report 5A: EOD Plan vs Actual + Plan Tomorrow status |
| **21:00** | `daily_plan_report.py --mode update` | `daily_reports.yml` (`plan_update`) | Report 5B: Updated Plan Tomorrow status |
| **07:00** | `daily_plan_report.py --mode morning` | `daily_reports.yml` (`plan_morning`) | Report 5C: Morning Plan forward + 3D/7D/1M stats + completion rate |
| **09:00** | `refuel_plan_report.py --report 2` | `daily_reports.yml` (`Report 2 - Progress Sent Plan`) | Refuel Plan Report 2: Progress Sent Plan (9:00 Myanmar) |
| **13:00** | `refuel_plan_report.py --report 2` | `daily_reports.yml` (`Report 2 - Progress Sent Plan`) | Refuel Plan Report 2: Progress Sent Plan (13:00 Myanmar) |
| **20:00** | `refuel_plan_report.py --report 2` | `daily_reports.yml` (`Report 2 - Progress Sent Plan`) | Refuel Plan Report 2: Progress Sent Plan (20:00 Myanmar) |
| **10:00, 14:00 & 20:30** | `daily_read_report.py` | `daily_reports.yml` (`read_report`) | Report 6: Note read status per-person (Read window 04:00-23:59) to teams + CONTROL |

---

## 🔑 GitHub Secrets Required

| Secret | Repository | Used By | Description |
|---|---|---|---|
| `SEND_BOT_TOKEN` | `tni-bot` (main) | `cron_send.py` | Bot token for daily reports |
| `REPORT_TASK_BOT_TOKEN` | `tni-bot` (main) | `cron_send.py` | Bot token for task remain |
| `TECHNICAL_DEP_BOT_TOKEN` | `tni-bot` (main) | `cron_send.py` | Bot token for technical updates |
| `APPS_SCRIPT_URL` | `tni-bot` (main) | `cron_send.py`, search bots | Web app URL of main Apps Script project (`apps_script_collector.gs`) |
| `DAILY_APPS_SCRIPT_URL` | `tni-bot` (main) | `cron_send.py`, search bots | Web app URL for daily summaries |
| `REFUEL_APPS_SCRIPT_URL` | `tni-bot` (main) / `TNI-SITE-DOWN` | `refuel_plan_report.py`, `botlookup_relay.py` | Web app URL for refuel tracking |
| `SD_APPS_SCRIPT_URL` | `TNI-SITE-DOWN` | `botlookup_relay.py` | Web app URL of standalone Site Down project (`site_down_v2.gs`) |
| `TELEGRAM_API_ID` | `tni-bot` (main) / `TNI-SITE-DOWN` | `daily_read_report.py`, `botlookup_relay.py` | Telegram account API ID |
| `TELEGRAM_API_HASH` | `tni-bot` (main) / `TNI-SITE-DOWN` | `daily_read_report.py`, `botlookup_relay.py` | Telegram account API hash |
| `TELEGRAM_SESSION` | `tni-bot` (main) / `TNI-SITE-DOWN` | `daily_read_report.py`, `botlookup_relay.py` | Telethon session string |

---

## 🔧 Key Design Decisions

1. **Per-person tracking:** Both Search Stats and Note Read use per-person format with 3Day/7Day/Month
2. **3Day format:** `d0/d1/d2` = today / yesterday / day-before-yesterday
3. **Deduplication:** Team member lists deduplicate by name (keep highest search count)
4. **Read Cutoff:** Note reads only count if read before/at 20:25 Myanmar cutoff time (anytime today prior to 20:25)
5. **Team members source:** Sheet col E rows 4-59 (not Telegram group participants) — ensures only actual team members are counted
6. **CONTROL gets consolidated:** All teams + CONTROL data in one message
7. **Team groups get own report:** Each team only sees their own data
8. **Note detection:** Messages matching ≥2 keywords: "team leader", "site down", "make plan", "rescue", "mdg", "mbb"
9. **All user-facing text in English** — code comments may remain in Vietnamese
10. **Team 5 merged into Team 2** group

---

## 🚀 How to Test

### cron_send.py (local):
```bash
# Requires .env with SEND_BOT_TOKEN, APPS_SCRIPT_URL
python cron_send.py
```

### daily_read_report.py (GitHub Actions only):
```
GitHub → Actions → "Daily Note Read Report (20:30 Myanmar)" → Run workflow
```
Requires: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` in GitHub Secrets

### daily_read_report.py (local):
```bash
# Add to .env:
# TELEGRAM_API_ID=...
# TELEGRAM_API_HASH=...
# TELEGRAM_SESSION=...
python daily_read_report.py
```

---

## 📝 Workflow Files

| File | Schedule | Script |
|---|---|---|
| `daily_task.yml` | workflow_dispatch (GAS trigger) | `cron_send.py` |
| `daily_plan_report.yml` | 11:00 UTC (17:30 Myanmar) + manual | `daily_plan_report.py` |
| `daily_read_report.yml` | 14:00 UTC (20:30 Myanmar) + manual | `daily_read_report.py` |
| `botlookup_relay.yml` | — | `botlookup_relay.py` |
| `send_teams_telethon.yml` | — | `send_teams_telethon.py` |
| `check_read_status.yml` | — | `check_read_status.py` |
| `check_read_loop.yml` | — | `check_read_loop.py` |

---

## ⚠️ Important Notes

1. **Apps Script deployment:** `apps_script_collector.js` is a LOCAL copy. Changes must be manually copied to Google Apps Script Editor and re-deployed (Publish → Deploy as web app → New version)
2. **Telethon session:** The session string is a personal Telegram account login. If the session expires, generate a new one with `get_session.py`
3. **Search data = 0:** If all search values show 0, check that Apps Script is deployed with the latest version that includes per-person search fields
4. **Duplicate names:** The system deduplicates by name. If two different people have the same name, only one will show
5. **Rate limiting:** Telethon calls have 0.3s delays between API calls to avoid Telegram rate limits

---

## 📊 Resource Consumption & Quotas

To prevent resource exhaustion and monitor usage limits, the system operates under the following quotas:

### 1. GitHub Actions (Minutes Quota)
- **Limit:** 2,000 free minutes/month (for private repos; unlimited/free for public repos).
- **Consumption:**
  - `botlookup_relay`: Runs every 30 minutes from 03:30 to 22:10 (38 runs/day). Each run takes ~40s (0.7 min). Day total: ~27 minutes.
  - Daily reports (`plan`, `read_report`, `daily_task`, `cable`, `refuel`): Runs ~10 times/day total. Each run takes ~1 min. Day total: ~10 minutes.
  - **Estimated Total:** ~37 minutes/day = **~1,100 minutes/month** (~55% of the free quota).
- **Monitoring:** View details in GitHub Profile → Settings → Billing & Plans → Plans and usage → Actions.

### 2. Google Apps Script (GAS Quota)
- **UrlFetchApp calls (Telegram Sends):**
  - **Limit:** 20,000 fetch calls/day (consumer Gmail) or 100,000 fetch calls/day (Google Workspace).
  - **Consumption:** Only called on updates and daily summaries (~150 calls/day total). Uses **< 1%** of quota.
- **Trigger Executions:**
  - **Limit:** 90 minutes/day execution time (consumer Gmail) or 6 hours/day (Google Workspace).
  - **Consumption:** The 5-minute `checkAndSend` trigger runs for ~2-3 seconds per execution (~15 mins/day total). Uses **~16%** of quota.
- **Monitoring:** View details in Apps Script Dashboard → G Suite Developer Console → Quotas.

### 3. Telegram API Rate Limits
- **Limits:** Max 30 messages/second to different chats; max 20 messages/minute within a single group.
- **Controls:** Telethon API calls in our Python scripts use `asyncio.sleep(0.3)` between individual chat/user checks to prevent rate limiting issues.

