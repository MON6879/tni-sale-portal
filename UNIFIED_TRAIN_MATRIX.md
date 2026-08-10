# 🚂 BẢN ĐỒ CHI TIẾT TỔNG THỂ CÁC CHUYẾN TÀU CODE THỐNG NHẤT (MASTER UNIFIED TRAIN MANIFEST V7.0)

Hệ thống được quy hoạch hoàn chỉnh thành **3 CHUYẾN TÀU CHÍNH (3 MAIN TRAIN LINES)** phân định rõ ràng đến từng **Toa Tàu (Carriage)**, **Dãy Ghế (Seat Row)**, **Số Ghế (Target Seat / Column Index)**, **Hạt Nhân Xử Lý (Core Nucleus / Sheet GID)** và **Sợi Dây Liên Kết (Pipeline Wires)**:

---

## 🔵 CHUYẾN TÀU 1: CHUYẾN TÀU SEARCH & TRA CỨU REALTIME 24/7 (SEARCH ENGINE LINE)
> **Cơ chế vận hành**: Realtime Serverless Webhook (< 0.1s) trên Vercel Cloud (`https://tni-bot.vercel.app/api/search_bot`). Trực chiến 24/7 phản hồi tức thì.

| Toa # | Tên Toa Tàu | Dãy Ghế & Trigger Key | Số Ghế (Cột Dữ Liệu) | Sợi Dây Liên Kết (Pipeline Wire) | Hạt Nhân Xử Lý & Sheet GID | Thông Tin Cuối Cùng (Final Output) |
|---|---|---|---|---|---|---|
| **Toa 1** | 📋 Task & WO Search | **Dãy A (Đơn lẻ)**: `TNIxxxx`, `TNIxxxx_0x`, `/tni` | • **Ghế 1A**: Col B (`TNI Code`)<br>• **Ghế 1B**: Col H (`Task/WO String`) | Telegram $\rightarrow$ `search_bot.py` $\rightarrow$ `format_task_wo()` | `perform_unified_tni_search(full_info=False)` (`Team_Sum` GID `893574714`) | Chỉ 📋 Task & 🔧 WO list (Đã lọc bỏ Site Info) |
| **Toa 2** | 🏢 Site Info & Cable & DIA | **Dãy A (Đơn lẻ)**: `Info: TNIxxxx`, `/info` | • **Ghế 2A**: Col B (`Site Info`)<br>• **Ghế 2B**: Col C (`Cable`)<br>• **Ghế 2C**: Col D (`GPON`)<br>• **Ghế 2D**: Col E (`DIA`) | Telegram $\rightarrow$ `search_bot.py` $\rightarrow$ `perform_unified_tni_search()` | `perform_unified_tni_search(full_info=True)` (`Name Site` GID `171059303`) | Chỉ 🏢 Site, 🔌 Cable, 📶 GPON, 🌐 DIA (Đã lọc bỏ Task/WO) |
| **Toa 3** | 📑 Open / Not Close WOs | **Dãy B (Gom nhóm)**: `/t1notclose` .. `/t4notclose` | • **Ghế 3A**: Col H (`Category Label`)<br>• **Ghế 3B**: Col I (`WO Content`) | Telegram $\rightarrow$ `search_bot.py` $\rightarrow$ `lookup_notclose()` | `lookup_notclose()` (`TL_WaitCD` GID `1110926116`) | Danh sách 📑 WOs chưa đóng của Team |
| **Toa 4** | ⏳ Wait CD WOs | **Dãy B (Gom nhóm)**: `/t1waitcd` .. `/t4waitcd` | • **Ghế 4A**: Col H (`Category Label`)<br>• **Ghế 4B**: Col I (`WO Content`) | Telegram $\rightarrow$ `search_bot.py` $\rightarrow$ `lookup_waitcd()` | `lookup_waitcd()` (`TL_WaitCD` GID `1110926116`) | Danh sách ⏳ WOs chờ CD của Team |
| **Toa 5** | 🧹 Clear Site History | **Dãy A (Đơn lẻ)**: `Clear TNIxxxx`, `/clear` | • **Ghế 5A**: Header Scan Col Index<br>• **Ghế 5B**: Content Rows | Telegram $\rightarrow$ CSV Export Site Down Sheet | `lookup_clear_site()` (`Search Site Clear` GID `610944071`) | Bảng 🧹 Lịch sử Clear Site & Sự cố |
| **Toa 6** | 📊 Team Leader Summary | **Dãy B (Gom nhóm)**: `T1`, `T2`, `T3`, `T4` (Private) | • **Ghế 6A**: Col B (`Team Code`)<br>• **Ghế 6B**: Col H (`Summary Text`) | Telegram $\rightarrow$ `search_bot.py` $\rightarrow$ `lookup_team()` | `lookup_team()` (`Team_Sum` GID `893574714`) | Báo cáo 📊 Tổng hợp Team Leader |
| **Toa 7** | 👤 Staff Personal Lookup | **Dãy A (Đơn lẻ)**: `mysite`, `mycable`, `mydia` | • **Ghế 7A**: Col A (`User ID`)<br>• **Ghế 7B**: Col C, D, E, F | Telegram $\rightarrow$ `get_staff_data()` | `get_staff_data()` (`Staff` GID `1684930643`) | Bảng 👤 Trạm, Tuyến cáp, DIA phân công cá nhân |
| **Toa 8** | 🏗️ Construction Search | **Dãy A (Đơn lẻ)**: `cons TNIxxxx`, `/cons`, `/pro` | • **Ghế 8A**: Col A (`TNI Code`)<br>• **Ghế 8B**: Col B (`Install`)<br>• **Ghế 8C**: Col C (`Remove`) | Telegram $\rightarrow$ Construction Sheet Export | `lookup_construction_site()` (Spreadsheet `1ViXXv5P8jSgx5heBqEP419ZkSR77C3OsflK0xpHMoi8`) | Báo cáo 🏗️ Tiến độ thi công, Vật tư Lắp đặt & Thu hồi |
| **Toa 9** | 📋 Menu Directory | **Dãy C (Biểu mẫu)**: `menu`, `/menu`, `/daily`, `/plan` | • **Ghế 9A**: Directory Links<br>• **Ghế 9B**: Mẫu `/daily` (`Daily result:`)<br>• **Ghế 9C**: Mẫu `/plan` (`Daily Plan:`) | Telegram $\rightarrow$ `send_help_menu()` / `send_daily_template()` | Internal Menu Engine & In-memory Pre-index RAM | Bảng 📋 Danh mục 9 Toa Tàu kèm mẫu Plain Text |

---

## 🟢 CHUYẾN TÀU 2: CHUYẾN TÀU THU THẬP & GHI DỮ LIỆU VÀO DÒNG 2 (DATA INGESTION LINE)
> **Cơ chế vận hành**: Sự kiện & Cron Automation Ingestion. **Quy tắc tuyệt đối 100%: Chèn dữ liệu mới vào Dòng 2 (`insertRowsBefore(2)`)** ngay bên dưới Hàng Tiêu Đề Header Row 1.

| Toa # | Tên Toa Tàu | Dãy Ghế & Từ Khóa Quét | Số Ghế (Vị Trí Cột Lưu) | Sợi Dây Liên Kết (Pipeline Wire) | Hạt Nhân Xử Lý & Target Sheet | Quy Tắc Chèn Bắt Buộc |
|---|---|---|---|---|---|---|
| **Toa 1** | 🏗️ Construction Collector | **Dãy A**: Tin nhắn `Pro` / `/pro` | Col A: TNI Code<br>Col B: Install/Remove<br>Col F: Link Drive `📥 DOWNLOAD ALL` | Telegram Bot `10 TNI_SITE` (`8903841312`) $\rightarrow$ GAS | `13_TNI_CONSTRUCTION.gs` (Spreadsheet `1ViXXv5P8jSgx5heBqEP419ZkSR77C3OsflK0xpHMoi8`) | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 2** | 📦 Asset, MDG & Inventory Collector | **Dãy A**: Nhóm `6. TNI M&E request + Run MDG + Invetory Fuel`<br>• **Ghế 2A**: Mẫu `MDG` + `Site ID: TNI`<br>• **Ghế 2B**: Mẫu `Inventory fuel:` + `DG ID: TNI` | • **Ghế 2A (MDG)**: Col A (Site ID), Col B (MDG ID), Col C (Run time), Col D (Kwh)<br>• **Ghế 2B (INV)**: Col A (DG ID), Col B (Fuel cm), Col C (Fuel %), Col D (Level) | Telegram Bot `@TNIASSETorderREQUEST_BOT` $\rightarrow$ Vercel | `api/collector.py` $\rightarrow$ `post_mdg_sheet()` $\rightarrow$ `REFUEL_APPS_SCRIPT_URL` | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 3** | ⛽ Refuel & DG Collector | **Dãy B**: Tin nhắn kế hoạch cấp phát dầu | Col A: Team<br>Col B: Fuel Volume<br>Col C: DG Hours | Telethon `@Phongha79` $\rightarrow$ GAS Backend | `refuel_plan_report.py` $\rightarrow$ Refuel GAS | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 4** | 🚨 Site Down Incident Collector | **Dãy A**: Nhóm Botlookup NOC Pro | Col A: TNI Code<br>Col B: Incident Type<br>Col C: Timestamp | Telethon `@Phongha79` $\rightarrow$ GAS Backend | `botlookup_relay.py` $\rightarrow$ `SD_APPS_SCRIPT_URL` (`1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow`) | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 5** | 📋 Daily Plan Collector | **Dãy C**: Tin nhắn `daily plan`, `hot task` | Col A: Date<br>Col B: Team<br>Col C: Plan Content | Telethon `@Phongha79` / Search Bot $\rightarrow$ GAS | `daily_plan_report.py` $\rightarrow$ `DAILY_APPS_SCRIPT_URL` (`daily_plan`) | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 6** | 🛠️ Daily Maintenance Collector | **Dãy C**: Lệnh `/daily` & Ảnh đính kèm | Col A: User ID<br>Col B: Form Fields<br>Col C: Drive Photo Link | Search Bot `@SEARCHTNITASKWOBOT` $\rightarrow$ GAS | `submit_daily()` + `submit_photo()` $\rightarrow$ `DAILY_APPS_SCRIPT_URL` | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 7** | 📖 Read Group Logs Collector | **Dãy B**: Lịch sử đã xem tin nhắn | Col A: User ID<br>Col B: Group ID<br>Col C: Read Timestamp | Telethon `@Phongha79` $\rightarrow$ GAS | `daily_read_report.py` $\rightarrow$ Sheet `read_log` | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 8** | 🔌 Cable Cut Incident Collector | **Dãy A**: Báo cáo đứt cáp & suy hao | Col A: Cable Route<br>Col B: Loss Point<br>Col C: Solution | Telethon `@Phongha79` $\rightarrow$ GAS | `cable_report.py` $\rightarrow$ Sheet `cable_log` | **Dòng 2 (`insertRowsBefore(2)`)** |

---

## 🔴 CHUYẾN TÀU 3: CHUYẾN TÀU TỰ ĐỘNG BÁO CÁO & GIÁM SÁT HẸN GIỜ (SCHEDULED AUTOMATION LINE)
> **Cơ chế vận hành**: GitHub Actions `train_5min.yml` (cron `3/5 * * * *`) + `botlookup_relay.yml` (cron `6,36 * * * *`).

| Toa # | Tên Toa Tàu | Giờ Khởi Hành (MMT) | Dãy Ghế (Nhiệm Vụ) | Sợi Dây Liên Kết (Pipeline Wire) | Hạt Nhân Xử Lý & Target Bot | Thông Tin Phản Hồi |
|---|---|---|---|---|---|---|
| **Toa 0** | 🏥 Keepalive & Webhook Lock | Mọi 5 phút 24/7 | Sưởi Vercel & Khóa Webhook | `train_5min.yml` step 1 $\rightarrow$ cURL | Ping Vercel `/api/search_bot`, `/collector`, `/relay` | Giữ sưởi Vercel RAM & Khóa Telegram Webhook URL |
| **PRE** | 🔔 Pre-Warm | 05:43 & 15:43 MMT | Warmup RAM trước 5 phút | `train_5min.yml` step 1 $\rightarrow$ cURL | Warmup Google Sheets CSV & Vercel Cache | Chuẩn bị tài nguyên sẵn sàng trước giờ báo cáo lớn |
| **Toa 1+11** | 📊 Reports 1-4 + BOD | 05:48 & 15:48 MMT | Báo cáo Backlog, Cron & BOD | `backlog_send.py` + `cron_send.py` + `daily_bod_assign.py` | Bot API Tokens $\rightarrow$ Telegram Groups | Tự động gửi báo cáo công việc hàng ngày |
| **Toa 3** | 📋 Plan 5A (EOD) | 05:58 & 15:58 MMT | Quét Kế hoạch EOD | `daily_plan_report.py --mode eod` | Telethon `@Phongha79` $\rightarrow$ Sheet `daily_plan` Row 2 | Quét plan EOD $\rightarrow$ Chèn Dòng 2 Google Sheets |
| **Toa 4** | 📋 Plan 5B (Update) | 21:03 MMT | Quét Plan điều chỉnh đêm | `daily_plan_report.py --mode update` | Telethon `@Phongha79` $\rightarrow$ Sheet `daily_plan` Row 2 | Quét plan update $\rightarrow$ Chèn Dòng 2 Google Sheets |
| **Toa 5** | 📋 Plan 5C (Morning) | 05:28, 08:28, 09:53, 15:23, 19:03, 22:03 MMT | Quét Plan sáng & chiều | `daily_plan_report.py --mode morning` | Telethon `@Phongha79` $\rightarrow$ Sheet `daily_plan` Row 2 | Quét plan sáng/chiều $\rightarrow$ Chèn Dòng 2 Google Sheets |
| **Toa 6** | 📖 Report 6 (Read) | 14:03, 16:03, 17:18, 19:08, 20:33 MMT | Quét nhật ký đọc tin | `daily_read_report.py` | Telethon `@Phongha79` $\rightarrow$ Sheet `read_log` Row 2 | Quét nhật ký đọc tin nhắn chỉ đạo |
| **Toa 7+8** | 🔌 Cable & Refuel Req | 05:53, 13:03, 15:53 MMT | Báo cáo Cáp & Cấp dầu | `cable_report.py` + `refuel_send.py` | Bot API Tokens $\rightarrow$ Telegram Groups | Báo cáo sự cố cáp & Yêu cầu cấp nhiên liệu |
| **Toa 9** | ⛽ Refuel Plan 1 | 13:08 & 22:08 MMT | Kế hoạch đổ dầu Team | `refuel_plan_report.py --report 1` | Telethon `@Phongha79` $\rightarrow$ Refuel GAS | Tổng hợp kế hoạch đổ dầu Team |
| **Toa 10** | ⛽ Refuel Plan 2 + 2.1 | 13:13, 18:03, 22:13 MMT | Cấp phát & Giám sát FT | `refuel_plan_report.py --report 2` + `--report 21` | Telethon `@Phongha79` $\rightarrow$ Refuel GAS | Kế hoạch cấp phát & Giám sát FT |
| **Toa 11** | ⛽ Refuel Plan 4 | 22:18 MMT | Tổng kết dầu cuối ngày | `refuel_plan_report.py --report 4` | Telethon `@Phongha79` $\rightarrow$ Refuel GAS | Tổng kết nhiên liệu máy phát cuối ngày |
| **ĐỘC LẬP** | 🚨 Site Down Relay | Phút `:06` & `:36` hàng giờ | Cào tin trạm sập NOC Pro | `botlookup_relay.yml` $\rightarrow$ `botlookup_relay.py` | Telethon `@Phongha79` $\rightarrow$ Sheet Site Down Row 2 | Cào tin trạm sập NOC Pro $\rightarrow$ Bắn cảnh báo Telegram |
