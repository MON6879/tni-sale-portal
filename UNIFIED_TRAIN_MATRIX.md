# 🚂 UNIFIED CODE TRAIN & NUCLEAR INTERCONNECTION MATRIX (Đoàn Tàu Code Thống Nhất & Sợi Dây Liên Kết Hạt Nhân)

> **Document Status:** Official Master System Architecture (v5.0 — Top 1% World-Class Grade)  
> **Last Updated:** 2026-08-10  
> **System Name:** TNI Bot System — Unified Code Train ("Đoàn Tàu Code Thống Nhất")

---

## 📌 1. TỔNG QUAN MÔ HÌNH ĐOÀN TÀU CODE THỐNG NHẤT

Hệ thống được thiết kế như **1 Đoàn Tàu Code Thống Nhất**, trong đó:
- **Toa Tàu (Carriage)**: Phân chia theo miền nghiệp vụ cụ thể (Search Engine, Auto Reports, Asset Collector, Site Down Relay, Refuel, Daily Plan, Construction).
- **Hàng Ghế (Row of Seats)**: Phân chia từ khóa kích hoạt (Search Key / Slash Commands) hoặc Cột dữ liệu (Data Column / Tab GID).
- **Sợi Dây Liên Kết (Interconnection Wires)**: Luồng dữ liệu tự động nối liền từ Giao diện Telegram Bot $\rightarrow$ Engine Classifier $\rightarrow$ Vercel/Telethon/GAS $\rightarrow$ Hạt Nhân Bảng Tính Google Sheets.

```
                                  🚂 ĐẦU KÉO THỐNG NHẤT (UNIFIED TRAIN SYSTEM)
                                                        │
   ┌──────────────────────┬─────────────────────────────┼─────────────────────────────┬─────────────────────────────┐
   │                      │                             │                             │                             │
🔍 SEARCH BOT TRAINS     📊 AUTO REPORT TRAINS         📋 DAILY PLAN TRAINS          ⛽ REFUEL & CABLE TRAINS      🏗️ CONSTRUCTION TRAIN
(Toa 1 - 9 Telegram)     (Toa 1+11: 05:48 & 15:48)     (Toa 3,4,5: Plan Reports)     (Toa 7-11: Refuel & Cable)    (Toa 8: Cons Search)
```

---

## 🚆 2. MA TRẬN PHÂN CHIA TOA TÀU, HÀNG GHẾ & SỢI DÂY LIÊN KẾT (FULL INTERCONNECTION MATRIX)

### 🅰️ NHÓM TOA TÀU SEARCH TELEGRAM BOT (REALTIME SEARCH ENGINE)

| Toa # | Tên Toa | Hàng Ghế (Search Key / Trigger) | Sợi Dây Liên Kết (Core Pipeline / Wire) | Data Sheet / GID | Hạt Nhân Xử Lý (Core Engine Function) | Kết Quả Phản Hồi (Target Output) |
|---|---|---|---|---|---|---|
| **TOA 1** | 📋 Task & WO | `TNIxxxx`, `TNIxxxx_0x`, `/tni`, `/find` | Telegram $\rightarrow$ `api/search_bot.py` $\rightarrow$ `format_task_wo()` | `Team_Sum` (GID `893574714`) Col B $\rightarrow$ Col H | `perform_unified_tni_search(full_info=False)` | 📋 Task list, 🔧 WO list, 🔔 Alarms (Excludes Site Info) |
| **TOA 2** | 🏢 Site Info & Cable | `Info: TNIxxxx`, `info TNIxxxx`, `/info` | Telegram $\rightarrow$ `api/search_bot.py` $\rightarrow$ `perform_unified_tni_search()` | `Name Site` (GID `171059303`) Col A $\rightarrow$ B,C,D,E | `perform_unified_tni_search(full_info=True)` | 🏢 Site Info, 🔌 Cable, 📶 GPON, 🌐 DIA (Excludes Task/WO) |
| **TOA 3** | 📑 Open / Not Close WOs | `T1notclose`, `T2notclose`, `T3notclose`, `T4notclose`, `/t1notclose` | Telegram $\rightarrow$ `tni_search_core` $\rightarrow$ `lookup_notclose()` | `TL_WaitCD` (GID `1110926116`) Col H $\rightarrow$ Col I | `lookup_notclose(team_code)` | 📑 Open / Unclosed WOs for specified Team |
| **TOA 4** | ⏳ Wait CD WOs | `T1waitcd`, `T2waitcd`, `T3waitcd`, `T4waitcd`, `/t1waitcd` | Telegram $\rightarrow$ `tni_search_core` $\rightarrow$ `lookup_waitcd()` | `TL_WaitCD` (GID `1110926116`) Col H $\rightarrow$ Col I | `lookup_waitcd(team_code)` | ⏳ WOs waiting for CD for specified Team |
| **TOA 5** | 🧹 Clear Site History | `Clear TNIxxxx`, `clear TNIxxxx`, `/clear` | Telegram $\rightarrow$ Site Down Sheet CSV Export | `Site Clear` (GID `610944071`) on Sheet `1FvDhIwq...` | `lookup_clear_site(tni)` | 🧹 Clear Site History Records |
| **TOA 6** | 📊 Team Leader Summary | `T1`, `T2`, `T3`, `T4` (Private Chat) | Telegram $\rightarrow$ `lookup_team()` | `Team_Sum` (GID `893574714`) Col B $\rightarrow$ Col H | `lookup_team(team_code)` | 📊 Team Leader Operational Summary |
| **TOA 7** | 👤 Staff Personal Lookup | `mysite`, `mycable`, `mydia`, `mydata`, `mysite <ID>` | Telegram $\rightarrow$ `get_staff_data()` | `Staff` (GID `1684930643`) Col A (User ID) | `get_staff_data(user_id, field)` | 👤 Personal Assignments & Staff Records |
| **TOA 8** | 🏗️ Construction Search | `cons TNIxxxx`, `pro TNIxxxx`, `/cons`, `/pro`, `construction` | Telegram $\rightarrow$ Construction Sheet `1ViXXv5P...` CSV Export | `Search Construction` tab Col A $\rightarrow$ Col B,C,D,E | `lookup_construction_site(tni)` | 🏗️ Construction Progress, Installation & Remove details |
| **TOA 9** | 📋 Menu & Command Guide | `menu`, `/menu`, `men`, `/men`, `help`, `/help`, `/start` | Telegram $\rightarrow$ `send_help_menu()` | Internal Menu Engine | `send_help_menu(chat_id)` | 📋 9-Carriage Command Directory with clickable code examples |

---

### 🅱️ NHÓM TOA TÀU TỰ ĐỘNG HÓA 5 PHÚT (GITHUB ACTIONS CRON `train_5min.yml`)

| Toa # | Tên Toa | Giờ Khởi Hành (MMT) | Engine & Script | Sợi Dây Liên Kết (Dependencies) | Hạt Nhân Bảo Vệ / Fail-safe |
|---|---|---|---|---|---|
| **Toa 0** | 🏥 Keepalive & Webhook Lock | Mọi chuyến (*/5 offset 3) | cURL $\rightarrow$ `train_5min.yml` step 1 | Search Bot (`/api/search_bot`), Asset Collector (`/api/collector`), Site Down Relay (`/api/site_down_relay`), Main GAS, Construction GAS | Sưởi Vercel Serverless không bị cold-start; Khóa `setWebhook` Telegram |
| **PRE** | 🔔 Pre-Warm | 05:43, 15:43 | cURL $\rightarrow$ `train_5min.yml` step 1 | Ping kích hoạt toàn bộ GAS & Vercel Endpoints 5 phút trước giờ báo cáo | Đảm bảo RAM/Cache Vercel và Google Sheets sẵn sàng 100% |
| **Toa 1+11** | 📊 Reports 1,2,3,4 + BOD | 05:48, 15:48 | 🤖 Bot API $\rightarrow$ `cron_send.py`, `daily_bod_assign.py` | `SEND_BOT_TOKEN`, `REPORT_TASK_BOT_TOKEN`, `TECHNICAL_DEP_BOT_TOKEN`, Apps Script API | Chạy song song độc lập bằng Bot API tokens |
| **Toa 3** | 📋 Plan 5A (EOD) | 05:58, 15:58 | 📱 Telethon $\rightarrow$ `daily_plan_report.py --mode eod` | Telegram Client (@Phongha79), Google Sheets `daily_plan` | Quét Telegram 200 msgs $\rightarrow$ Deduplicate Newest-First $\rightarrow$ Insert Sheet row 2 |
| **Toa 4** | 📋 Plan 5B (Update) | 21:03 | 📱 Telethon $\rightarrow$ `daily_plan_report.py --mode update` | Telegram Client (@Phongha79), Sheet `daily_plan` | Đọc tin nhắn điều chỉnh kế hoạch ban đêm |
| **Toa 5** | 📋 Plan 5C (Morning) | 05:28, 08:28, 09:53, 15:23, 19:03, 22:03 | 📱 Telethon $\rightarrow$ `daily_plan_report.py --mode morning` | Telegram Client (@Phongha79), `is_daily_plan_msg()`, `deduplicate_plans_by_date()` | Quét plan hôm nay; Fallback lấy từ Sheet nếu scan rỗng |
| **Toa 6** | 📖 Report 6 (Read) | 14:03, 16:03, 17:18, 19:08, 20:33 | 📱 Telethon $\rightarrow$ `daily_read_report.py` | Telegram Client (@Phongha79), Sheet `read_log` | Quét ai đã đọc tin nhắn chỉ đạo |
| **Toa 7** | 🔌 Cable Daily Report | 05:53, 15:53 | 🤖 Bot API $\rightarrow$ `cable_report.py` | `COLLECTOR_BOT_TOKEN`, `CABLE_APPS_SCRIPT_URL` | Báo cáo sự cố & tiến độ cáp |
| **Toa 8** | ⛽ Refuel Request | 05:53, 13:03, 15:53 | 🤖 Bot API $\rightarrow$ `refuel_send.py` | `REFUEL_BOT_TOKEN`, `REFUEL_APPS_SCRIPT_URL` | Báo cáo yêu cầu nhiên liệu máy phát |
| **Toa 9** | ⛽ Refuel Plan 1 | 13:08, 22:08 | 📱 Telethon $\rightarrow$ `refuel_plan_report.py --report 1` | Telegram Client (@Phongha79), `REFUEL_BOT_TOKEN` | Tổng hợp kế hoạch đổ dầu Team |
| **Toa 10** | ⛽ Refuel Plan 2 + 2.1 | 13:13, 18:03, 22:13 | 📱 Telethon $\rightarrow$ `refuel_plan_report.py --report 2` | Telegram Client (@Phongha79), `REFUEL_BOT_TOKEN` | Kiểm tra ngày giám sát FT & Kế hoạch cấp phát |
| **Toa 11** | ⛽ Refuel Plan 4 | 22:18 | 📱 Telethon $\rightarrow$ `refuel_plan_report.py --report 4` | Telegram Client (@Phongha79), `REFUEL_BOT_TOKEN` | Tổng kết nhiên liệu cuối ngày |

---

## 🧬 3. SÁU HẠT NHÂN QUY TẮC BẮT BUỘC (NUCLEAR LOGIC RULES)

1. **Hạt Nhân Webhook Async Decoupling (3s Telegram SLA):**
   * Mọi Webhook endpoint trên Vercel phải trả về `HTTP 200 OK` ngay lập tức (~10ms) trước khi thực thi logic nặng bằng `threading.Thread`.

2. **Hạt Nhân Quét Plan & Exclusion Blocklist:**
   * `is_daily_plan_msg()` tuyệt đối KHÔNG chứa các từ khóa trong nội dung Plan hợp lệ của Team Leader.
   * `deduplicate_plans_by_date()` phải giữ bản tin MỚI NHẤT (Newest-First): `if key not in latest_map: latest_map[key] = p`.

3. **Hạt Nhân Chống Xung Đột Telethon Session:**
   * Mọi tác vụ dùng Telethon (`@Phongha79`) phải dàn xếp lệch thời gian tối thiểu 5 phút. Không bao giờ cho 2 script Telethon chạy đồng thời trong cùng 1 tick 5 phút.

4. **Hạt Nhân Phút Lẻ Offset 3 Chống Nghẽn Cron:**
   * Mọi cron schedule chính của hệ thống phải đặt ở phút lẻ `:03, :08, :13, :18, :23, :28, :33, :38, :43, :48, :53, :58` để tránh nghẽn hàng đợi GitHub Actions toàn cầu ở phút tròn.

5. **Hạt Nhân Thu Thập Dữ Liệu Ghi Đầu Bảng Tính (Top Row Insertion):**
   * Mọi bộ thu thập dữ liệu (Daily Plan, Read Log, Refuel, Inventory...) khi ghi vào Google Sheets BẮT BUỘC phải chèn dòng mới lên đầu (Dòng 2, bên dưới Header Row 1) bằng `insertRowsBefore(2, ...)`. Tuyệt đối không dùng `appendRow()`.

6. **Hạt Nhân Khung Thời Gian Botlookup Relay 6 Phút:**
   * Botlookup Relay chạy tại phút `:06 & :36` MMT — đúng 6 phút sau khi Bot công ty đăng tin tổng hợp lúc `:00 & :30`.

---

## 🛡️ 4. QUY TRÌNH "LƯU ĐI" BẮT BUỘC 6 BƯỚC (STRICT SAVE PROCEDURE)

```
[Bước 1: Snapshot Backup] ──► [Bước 2: Đồng Bộ Mã Nguồn] ──► [Bước 3: Commit & Push All Repos]
                                                                            │
[Bước 6: Live Output Verification] ◄── [Bước 5: Full Cross-Sync] ◄── [Bước 4: Dọn Pycache]
```
