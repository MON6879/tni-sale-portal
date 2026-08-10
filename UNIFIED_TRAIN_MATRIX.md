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
| **Toa 1** | 🏗️ Construction Collector | **Dãy A**: Tin nhắn `Pro` / `/pro` | Col A: TNI Code<br>Col B: Install/Remove<br>Col F: Link Drive `📥 DOWNLOAD ALL (N Photos)` | Telegram Bot `10 TNI_SITE` (`8903841312`) $\rightarrow$ GAS | `13_TNI_CONSTRUCTION.gs` (Spreadsheet `1ViXXv5P8jSgx5heBqEP419ZkSR77C3OsflK0xpHMoi8`) | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 2** | 📦 Asset, MDG, INV & Cable Collector | **Dãy A**: Nhóm `@TNIASSETorderREQUEST_BOT`<br>• **Ghế 2A (MDG)**: Ảnh MDG Run<br>• **Ghế 2B (INV)**: Ảnh Inventory Fuel<br>• **Ghế 2C (Cable)**: Ảnh Đứt cáp<br>• **Ghế 2D (Asset)**: Ảnh Đơn vật tư | • **Ghế 2A (MDG)**: Col E Link `📥 DOWNLOAD ALL (N Photos)`<br>• **Ghế 2B (INV)**: Col E Link `📥 DOWNLOAD ALL (N Photos)`<br>• **Ghế 2C (Cable)**: Col D Link `📥 DOWNLOAD ALL (N Photos)`<br>• **Ghế 2D (Asset)**: Col F Link `📥 DOWNLOAD ALL (N Photos)` | Telegram Bot `@TNIASSETorderREQUEST_BOT` $\rightarrow$ Vercel | `api/collector.py` $\rightarrow$ `post_mdg_sheet()` $\rightarrow$ `REFUEL_APPS_SCRIPT_URL` | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 3** | ⛽ Refuel & DG Collector | **Dãy B**: Tin nhắn kế hoạch cấp phát dầu | Col A: Team<br>Col B: Fuel Volume<br>Col C: DG Hours | Telethon `@Phongha79` $\rightarrow$ GAS Backend | `refuel_plan_report.py` $\rightarrow$ Refuel GAS | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 4** | 🚨 Site Down Incident Collector | **Dãy A**: Nhóm Botlookup NOC Pro | Col A: TNI Code<br>Col B: Incident Type<br>Col C: Timestamp | Telethon `@Phongha79` $\rightarrow$ GAS Backend | `botlookup_relay.py` $\rightarrow$ `SD_APPS_SCRIPT_URL` (`1FvDhIwq8HxKfS2MqrwZMapIEsv7dwafaAVVnK0lpXow`) | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 5** | 📋 Daily Plan Collector | **Dãy C**: Tin nhắn `daily plan`, `hot task` | Col A: Date<br>Col B: Team<br>Col C: Plan Content | Telethon `@Phongha79` / Search Bot $\rightarrow$ GAS | `daily_plan_report.py` $\rightarrow$ `DAILY_APPS_SCRIPT_URL` (`daily_plan`) | **Dòng 2 (`insertRowsBefore(2)`)** |
| **Toa 6** | 🛠️ Daily Maintenance Collector | **Dãy C**: Lệnh `/daily` & Ảnh đính kèm | Col A: User ID<br>Col B: Form Fields<br>Col C: Link Drive `📥 DOWNLOAD ALL (N Photos)` | Search Bot `@SEARCHTNITASKWOBOT` $\rightarrow$ GAS | `submit_daily()` + `submit_photo()` $\rightarrow$ `DAILY_APPS_SCRIPT_URL` | **Dòng 2 (`insertRowsBefore(2)`)** |
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
| **ĐỘC LẬP** | 🟢 1. CRON ĐỘC LẬP (Site Down Relay) | Phút `:03` & `:33` hàng giờ (Ví dụ: 14:03, 14:33, 15:03, 15:33, 16:03, 16:33...) | Cào tin trạm sập NOC Pro CHÍNH THỨC | `botlookup_relay.yml` | Telethon `@Phongha79` $\rightarrow$ Sheet Site Down Row 2 | Cào tin trạm sập NOC Pro CHÍNH THỨC không trễ 1s (Chạy độc lập siêu tốc ~5s) |

### ⛽ MA TRẬN GHẾ HẠT NHÂN BÁO CÁO NHIÊN LIỆU (FUEL REPORTS SEATS MATRIX):

#### **TOA 7+8: 🔌 CABLE & REFUEL REQUEST (05:53, 13:03, 15:53 MMT)**
- **Dãy Ghế F-REQ (Yêu Cầu Cấp Nhiên Liệu Khẩn Cấp)**:
  - `Ghế F-REQ1`: Yêu cầu cấp nhiên liệu Team 1 Dawei $\rightarrow$ Bot API $\rightarrow$ Group `9 TNI REQUEST REFUEL`
  - `Ghế F-REQ2`: Yêu cầu cấp nhiên liệu Team 2 Myeik $\rightarrow$ Bot API $\rightarrow$ Group `9 TNI REQUEST REFUEL`
  - `Ghế F-REQ3`: Yêu cầu cấp nhiên liệu Team 3 Bokpyin $\rightarrow$ Bot API $\rightarrow$ Group `9 TNI REQUEST REFUEL`
  - `Ghế F-REQ4`: Yêu cầu cấp nhiên liệu Team 4 Kawthoung $\rightarrow$ Bot API $\rightarrow$ Group `9 TNI REQUEST REFUEL`

#### **TOA 9: ⛽ REFUEL PLAN 1 (13:08 & 22:08 MMT)**
- **Dãy Ghế F-P1 (Kế Hoạch Dự Trù Nhiên Liệu Máy Phát Team)**:
  - `Ghế F-P1-T1`: Refuel Plan 1 Team 1 Dawei (`refuel_plan_report.py --report 1`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P1-T2`: Refuel Plan 1 Team 2 Myeik (`refuel_plan_report.py --report 1`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P1-T3`: Refuel Plan 1 Team 3 Bokpyin (`refuel_plan_report.py --report 1`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P1-T4`: Refuel Plan 1 Team 4 Kawthoung (`refuel_plan_report.py --report 1`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS

#### **TOA 10: ⛽ REFUEL PLAN 2 & 2.1 (13:13, 18:03, 22:13 MMT)**
- **Dãy Ghế F-P2 (Cấp Phát & Giám Sát Nhiên Liệu Kỹ Thuật Viên FT)**:
  - `Ghế F-P2-T1`: Refuel Plan 2 Team 1 Dawei (`refuel_plan_report.py --report 2`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P2-T2`: Refuel Plan 2 Team 2 Myeik (`refuel_plan_report.py --report 2`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P2-T3`: Refuel Plan 2 Team 3 Bokpyin (`refuel_plan_report.py --report 2`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P2-T4`: Refuel Plan 2 Team 4 Kawthoung (`refuel_plan_report.py --report 2`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
- **Dãy Ghế F-P21 (Nhật Ký Tiêu Thụ Nhiên Liệu Máy Phát Hàng Giờ)**:
  - `Ghế F-P21-T1`: Refuel Plan 2.1 Team 1 Dawei (`refuel_plan_report.py --report 21`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P21-T2`: Refuel Plan 2.1 Team 2 Myeik (`refuel_plan_report.py --report 21`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P21-T3`: Refuel Plan 2.1 Team 3 Bokpyin (`refuel_plan_report.py --report 21`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P21-T4`: Refuel Plan 2.1 Team 4 Kawthoung (`refuel_plan_report.py --report 21`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS

#### **TOA 11: ⛽ REFUEL PLAN 4 (22:18 MMT)**
- **Dãy Ghế F-P4 (Quyết Toán Tổng Kết Nhiên Liệu Cuối Ngày)**:
  - `Ghế F-P4-T1`: Refuel Plan 4 Team 1 Dawei (`refuel_plan_report.py --report 4`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P4-T2`: Refuel Plan 4 Team 2 Myeik (`refuel_plan_report.py --report 4`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P4-T3`: Refuel Plan 4 Team 3 Bokpyin (`refuel_plan_report.py --report 4`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS
  - `Ghế F-P4-T4`: Refuel Plan 4 Team 4 Kawthoung (`refuel_plan_report.py --report 4`) $\rightarrow$ Telethon $\rightarrow$ Refuel GAS

---

## 📊 CHUYẾN TÀU SỐ 4: EXECUTIVE WEB BI PORTAL SYNC LINE (`https://tni-bot.vercel.app`)

> **Cơ chế vận hành**: Realtime DOM & Data Cache Auto-Sync. **Quy tắc tuyệt đối 100%: Đồng bộ con số chính xác 1-to-1 giữa Hình 1 (Cards) và Hình 2 (Performance Chart)**.

| Toa # | Tên Toa Tàu | Dãy Ghế & Từ Khóa Quét | Số Ghế (Vị Trí Cột Lưu) | Sợi Dây Liên Kết (Pipeline Wire) | Hạt Nhân Xử Lý & Target Web Portal | Quy Tắc Đồng Bộ Bắt Buộc |
|---|---|---|---|---|---|---|
| **Toa 1** | 🏢 Executive Team Cards Sync (Hình 1) | **Dãy A**: 4 Thẻ Team Leaders<br>• Team 1 Dawei<br>• Team 2 Myeik<br>• Team 3 Bokpyin<br>• Team 4 Kawthoung | • **Ghế 1A**: Total Assigned WOs<br>• **Ghế 1B**: WO Close (G) & Completion %<br>• **Ghế 1C**: Overdue FOT (N) & Remain WO (P)<br>• **Ghế 1D**: Wait CD & CD Not Close (A) | Google Sheets `Tên Sum WO` $\rightarrow$ Vercel `data_cache.json` | Web BI Portal `tni-bot.vercel.app` (`index.html`) | Đọc số liệu thực tế realtime từ Google Sheets |
| **Toa 2** | 📊 Performance Comparison Chart Sync (Hình 2) | **Dãy B**: Đồ thị Bar Chart So sánh 4 Teams | • **Ghế 2A**: Total WO (P+G)<br>• **Ghế 2B**: FOT Close (G)<br>• **Ghế 2C**: Remain WO (P)<br>• **Ghế 2D**: Remain Overdue (N)<br>• **Ghế 2E**: CD Not Close (A) | JS Dynamic Event `syncWebBiPortalData()` | Web BI Portal `woChartInstance` (`index.html`) | **Bắt buộc tự động đọc 100% dữ liệu từ Hình 1**, đảm bảo Hình 1 và Hình 2 luôn bằng nhau |
| **Toa 3** | 📋 Summary All Name System Roster (Bảng 3) | **Dãy C**: Bảng Roster 24 Nhân Viên Kỹ Thuật | • **Ghế 3A**: Ranking & Completion Rate % 24 FTs | Google Sheets `Tên Sum WO` $\rightarrow$ Vercel | Web BI Portal Table 3 (`index.html`) | Tự động sắp xếp từ % cao xuống % thấp |

### 🔍 MA TRẬN GHẾ HẠT NHÂN CHI TIẾT (NUCLEUS SEATS DETAIL MATRIX):

#### **TOA 1: 🏢 EXECUTIVE TEAM CARDS SYNC (HÌNH 1 — 4 THẺ TEAM LEADERS)**
- **Dãy Ghế 1A (Total Assigned WOs)**:
  - `Ghế 1A1`: Total Assigned WO Team 1 Dawei (`394 WOs`)
  - `Ghế 1A2`: Total Assigned WO Team 2 Myeik (`209 WOs`)
  - `Ghế 1A3`: Total Assigned WO Team 3 Bokpyin (`95 WOs`)
  - `Ghế 1A4`: Total Assigned WO Team 4 Kawthoung (`103 WOs`)
- **Dãy Ghế 1B (WO Close — G)**:
  - `Ghế 1B1`: FOT Close (G) Team 1 Dawei (`72 WOs`)
  - `Ghế 1B2`: FOT Close (G) Team 2 Myeik (`119 WOs`)
  - `Ghế 1B3`: FOT Close (G) Team 3 Bokpyin (`32 WOs`)
  - `Ghế 1B4`: FOT Close (G) Team 4 Kawthoung (`81 WOs`)
- **Dãy Ghế 1C (Overdue FOT — N)**:
  - `Ghế 1C1`: Overdue FOT (N) Team 1 Dawei (`151 WOs`)
  - `Ghế 1C2`: Overdue FOT (N) Team 2 Myeik (`24 WOs`)
  - `Ghế 1C3`: Overdue FOT (N) Team 3 Bokpyin (`14 WOs`)
  - `Ghế 1C4`: Overdue FOT (N) Team 4 Kawthoung (`0 WOs`)
- **Dãy Ghế 1D (WO Remain — P)**:
  - `Ghế 1D1`: WO Remain (P) Team 1 Dawei (`322 WOs`)
  - `Ghế 1D2`: WO Remain (P) Team 2 Myeik (`90 WOs`)
  - `Ghế 1D3`: WO Remain (P) Team 3 Bokpyin (`63 WOs`)
  - `Ghế 1D4`: WO Remain (P) Team 4 Kawthoung (`22 WOs`)
- **Dãy Ghế 1E (Wait CD & CD Not Close — A)**:
  - `Ghế 1E1`: Wait CD Team 1 (`23 WOs`) | CD Not Close (A) Team 1 (`41 WOs`)
  - `Ghế 1E2`: Wait CD Team 2 (`8 WOs`) | CD Not Close (A) Team 2 (`23 WOs`)
  - `Ghế 1E3`: Wait CD Team 3 (`0 WOs`) | CD Not Close (A) Team 3 (`3 WOs`)
  - `Ghế 1E4`: Wait CD Team 4 (`0 WOs`) | CD Not Close (A) Team 4 (`2 WOs`)
- **Dãy Ghế 1F (WO Close 3-Day History)**:
  - `Ghế 1F1`: Team 1 3-Day Close (`09/08: 7 WOs` | `08/08: 1 WO` | `07/08: 1 WO`)
  - `Ghế 1F2`: Team 2 3-Day Close (`09/08: 14 WOs` | `08/08: 0 WO` | `07/08: 1 WO`)
  - `Ghế 1F3`: Team 3 3-Day Close (`09/08: 5 WOs` | `08/08: 0 WO` | `07/08: 0 WO`)
  - `Ghế 1F4`: Team 4 3-Day Close (`09/08: 14 WOs` | `08/08: 0 WO` | `07/08: 0 WO`)
- **Dãy Ghế 1G (Rank & Completion Status)**:
  - `Ghế 1G1`: Team 1 Rank & Target (`Rank #4` | `17.3%/50%` | `❌ Not Met`)
  - `Ghế 1G2`: Team 2 Rank & Target (`Rank #2` | `54.8%/50%` | `✅ Met`)
  - `Ghế 1G3`: Team 3 Rank & Target (`Rank #3` | `33.7%/50%` | `❌ Not Met`)
  - `Ghế 1G4`: Team 4 Rank & Target (`Rank #1` | `78.6%/50%` | `✅ Met`)
- **Dãy Ghế 1H (Plan 11/08/2026 — Cột M Google Sheet — Màu Hồng Đậm `#EC4899`)**:
  - `Ghế 1H1`: Plan 11/08 Team 1 Dawei (`40 WOs` — Deep Pink `#EC4899`)
  - `Ghế 1H2`: Plan 11/08 Team 2 Myeik (`11 WOs` — Deep Pink `#EC4899`)
  - `Ghế 1H3`: Plan 11/08 Team 3 Bokpyin (`8 WOs` — Deep Pink `#EC4899`)
  - `Ghế 1H4`: Plan 11/08 Team 4 Kawthoung (`3 WOs` — Deep Pink `#EC4899`)

#### **TOA 2: 📊 PERFORMANCE COMPARISON CHART SYNC (HÌNH 2 — ĐỒ THỊ CHART)**
- `Ghế 2A`: Dataset Total WO — Realtime Auto-Sync `[394, 209, 95, 103]` từ Ghế 1A1-1A4.
- `Ghế 2B`: Dataset FOT Close (G) — Realtime Auto-Sync `[72, 119, 32, 81]` từ Ghế 1B1-1B4.
- `Ghế 2C`: Dataset Remain WO (P) — Realtime Auto-Sync `[322, 90, 63, 22]` từ Ghế 1D1-1D4.
- `Ghế 2D`: Dataset Overdue FOT (N) — Realtime Auto-Sync `[151, 24, 14, 0]` từ Ghế 1C1-1C4.
- `Ghế 2E`: Dataset CD Not Close (A) — Realtime Auto-Sync `[41, 23, 3, 2]` từ Ghế 1E1-1E4.

#### **TOA 3: 📋 SUMMARY ALL NAME SYSTEM ROSTER (BẢNG 3 — ROSTER 24 FTs)**
- `Ghế 3A`: Bảng Roster 24 nhân viên kỹ thuật đồng bộ % hoàn thành và phân hạng tự động.


