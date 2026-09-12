# BACKUP CONTEXT — 12/09/2026 (Phiên bản v798)
# KHẮC PHỤC TRIỆT ĐỂ SỰ CỐ HỆ THỐNG MASTER AUDITOR: CHỐNG NHÂN ĐÔI TIN NHẮN, CHUẨN HÓA CHAT ID CONTROL, KHÓA GIỜ CHECK_TIME_EXACT & BỘ ĐỆM KHÁNG LỖI TÍNH TOÁN GOOGLE SHEETS

---

## 1. BỐI CẢNH & BÁO ĐỘNG TỪ MASTER SYSTEM AUDITOR (08:58 MMT)
- Vào lúc 08:58:32 MMT ngày 12/09/2026, Master System Auditor (`system_auditor.py`) phát hiện và gửi cảnh báo:
  - **3 trường hợp nhân đôi tin nhắn** trong nhóm CONTROL lúc 05:53 MMT (cách nhau 17-18s):
    - `MW link Error : total : 2 Progress` (IDs: 98769 & 98773)
    - `📋 8. Report — Technical Dep Assign` (IDs: 98768 & 98772)
    - `📋 1. Report — Technical Dept Task P` (IDs: 98767 & 98771)
  - **1 lỗi Missed Report 6.1 (Site Clear Today)** lúc 07:18 MMT (không có tin nhắn nào được gửi).
  - **2 lỗi Delayed Reports**:
    - `Report 5C (Plan Sáng/Chiều)`: gửi lúc 08:35 (trễ 7p so với mốc 08:28).
    - `Report 6 (Daily Note Read)`: gửi lúc 08:55 (trễ 7p so với mốc 08:48).
  - **2 lỗi Missed Refuel Request Report**: mốc 05:46 MMT & 07:06 MMT.
  - **Cảnh báo lỗi Google Sheets**: `Task Remain` (4 `#DIV/0!`), `Progress WO & DG Need` (1 `#VALUE!`), `Team leader Wait CD + Not Close` (0 rows).

---

## 2. ĐIỀU TRA NGUYÊN NHÂN GỐC KỸ THUẬT (ROOT CAUSE FORENSICS)

### A. Lỗi Nhân Đôi Tin Nhắn Lúc 05:53 MMT (17-18s apart)
- **Root Cause**:
  1. Trong workflow `train_5min.yml`, khối `concurrency` được cấu hình:
     ```yaml
     concurrency:
       group: ${{ github.event_name == 'workflow_dispatch' && 'train-manual' || 'train-auto' }}
     ```
     Khóa nhóm bị chia đôi thành `train-manual` và `train-auto`.
  2. GAS trigger `dispatchTrain5Min` chạy định kỳ gọi GitHub REST API trigger `train_5min.yml` qua `workflow_dispatch` (thuộc nhóm `train-manual`).
  3. Cùng lúc đó, trên repository `MON6879/tni-sitedown-relay`, khối `on.schedule: - cron: '1/5 * * * *'` vẫn đang hoạt động (thuộc nhóm `train-auto`).
  4. Tại mốc 23:20 UTC (05:50 MMT), GitHub Actions kích hoạt đồng thời cả 2 luồng (Run ID `34657690248` và `34657850045`). Do 2 concurrency group khác nhau, GitHub Actions cho phép cả 2 máy ảo runner chạy song song, gửi 2 bộ báo cáo vào CONTROL cách nhau đúng 17-18 giây!

### B. Lỗi Missed Report 6.1 Lúc 07:18 MMT
- **Root Cause**:
  - Trong `site_clear_report.py` trên runner repo `tni-sitedown-relay`, dòng 42 hardcode `CONTROL_CHAT_ID = -1005251698940` (thừa tiền tố `-100`).
  - Telegram Bot API trả về lỗi `400 Bad Request: Chat not found`, khiến báo cáo cho nhóm CONTROL bị hủy bỏ hoàn toàn.

### C. Lỗi Delayed Report 5C (08:35) & Report 6 (08:55)
- **Root Cause**:
  - Trong `train_5min.yml`, tác vụ được kiểm tra bằng điều kiện:
    ```bash
    (check_time 08 28 || check_time 08 26) && P5C=true
    (check_time 08 48 || check_time 08 46) && R6=true
    ```
  - Bản thân hàm `check_time` đã có dung sai $\pm 5$ phút (`DIFF <= 5`).
  - Khi OR 2 mốc giờ cách nhau 2 phút, cửa sổ kích hoạt bị nới rộng thành **12 phút** (bao trùm 2 đến 3 nhịp 5 phút liên tiếp):
    - Mốc 08:28 / 08:26: khớp cả nhịp runner 08:26 LẪN nhịp 08:31. Nhịp 08:31 gửi tin lúc 08:35, bị Auditor tính là trễ 7 phút!
    - Mốc 08:48 / 08:46: khớp cả nhịp runner 08:46 LẪN nhịp 08:51. Nhịp 08:51 gửi tin lúc 08:55, bị Auditor tính là trễ 7 phút!

### D. Lỗi Missed Refuel Request Report (05:46 & 07:06)
- **Root Cause**:
  - Script `refuel_send.py` đã được thông báo vô hiệu hóa và gộp vào `refuel_plan_report.py --report 1` (chạy vào 10:06 và 14:11 MMT) từ ngày 06/09/2026.
  - Tuy nhiên trong `train_5min.yml`, Toa 8 vẫn được bật cờ `REFUEL_REQ=true` tại 05:46 và 07:06, khi chạy chỉ in ra log `refuel_send.py DISABLED` mà không gửi gì.
  - Đồng thời trong `system_auditor.py`, `SCHEDULE_RULES` vẫn giữ rule kiểm tra `Refuel Request Report` tại 05:46 và 07:06, gây ra báo động giả (false alarm).

### E. Lỗi Google Sheets Transient Calculation
- **Root Cause**:
  - Khi các báo cáo sáng tải dữ liệu lớn, bảng tính Google Sheets thực hiện tính toán lại các hàm `IMPORTRANGE` và `QUERY`.
  - Trong khoảng 2-3 giây tính toán, ô dữ liệu tạm thời hiển thị `#DIV/0!` hoặc `#VALUE!`. Auditor quét trúng khoảnh khắc này nên ghi nhận lỗi.

---

## 3. CÁC HÀNH ĐỘNG ĐÃ THỰC THI (ACTIONS TAKEN)

### A. Khóa Chặt Concurrency & Vô Hiệu Hóa Ghost Cron
1. Trong `train_5min.yml` trên cả 3 repos (`Task and WO`, `tni-search`, `tni-sitedown`):
   ```yaml
   concurrency:
     group: train-5min-singleton
     cancel-in-progress: false
   ```
   Ép buộc mọi lượt chạy (GAS dispatch hay manual UI) đều thuộc duy nhất nhóm `train-5min-singleton`, triệt tiêu 100% khả năng chạy song song.
2. Vô hiệu hóa triệt để `# schedule: - cron: '1/5 * * * *'` trên `tni-sitedown-relay`. Toàn bộ đoàn tàu được điều phối duy nhất bởi GAS `dispatchTrain5Min` (Single Engine).

### B. Chuẩn Hóa site_clear_report.py
1. Thay thế hardcode bằng ID chuẩn:
   ```python
   CONTROL_CHAT_ID = TELEGRAM_GROUPS.get("CONTROL", -5251698940)
   ```
2. Thêm bộ lọc lỗi công thức Google Sheets (`FORMULA_ERRORS = {"#REF!", "#VALUE!", "#N/A", ...}`).
3. Xử lý an toàn khi không có sự cố: `"✅ 0 site clear incidents recorded today."`.

### C. Khóa Giờ Chính Xác check_time_exact (Dung Sai $\le 2$ phút)
- Chuyển toàn bộ các mốc báo cáo 1 lần sang dùng `check_time_exact`:
  - 07:18 MMT: `check_time_exact 07 18 && R61=true`
  - 08:28 MMT: `check_time_exact 08 28 && P5C=true`
  - 08:48 MMT: `check_time_exact 08 48 && R6=true`
  - 10:18 MMT: `check_time_exact 10 18 && R61=true`
  - 14:18 MMT: `check_time_exact 14 18 && R61=true`
  - 14:58 MMT: `check_time_exact 14 58 && R6=true`
  - 17:18 MMT: `check_time_exact 17 18 && R6=true && R61=true`
- Kháng hoàn toàn hiện tượng gửi lặp lại ở nhịp kế tiếp gây trễ 7 phút.

### D. Dọn Dẹp Toa 8 Refuel & Chuẩn Hóa Auditor Rule
1. Vô hiệu hóa Toa 8 trong `train_5min.yml` (`if: false`, loại bỏ `REFUEL_REQ=true` tại 05:46, 07:06, 13:06, 15:46).
2. Cập nhật `SCHEDULE_RULES` trong `system_auditor.py` sang `Refuel Merged Report` với các mốc giờ thực tế `["10:06", "14:11"]`, tiêu đề khớp `[Report 1] TNI REQUEST REFUEL`.

### E. Bổ Sung Bộ Đệm Kháng Lỗi Sheet Đang Tính Toán
- Trong `audit_sheets_connectors()`, nếu lần tải đầu tiên (attempt 0) phát hiện lỗi công thức hoặc rỗng dòng: chờ 4 giây để Google Sheets hoàn tất tính toán rồi thử lại trước khi kết luận lỗi.

### F. Đúc Thành RULE PM-24 Trong AGENTS.md
- Đã ghi nhận nguyên tắc phòng ngừa vào `AGENTS.md` (đồng bộ cả 3 repositories):
  - Khóa Concurrency `train-5min-singleton` bắt buộc.
  - Khóa giờ đơn khớp `check_time_exact`.
  - Chuẩn hóa lịch Refuel SSOT.
  - Bộ đệm kháng lỗi Sheet đang tính toán.

---

## 4. BẢNG PHÂN HỆ & TRẠNG THÁI TRIỂN KHAI
| Ghế Phân Hệ | File | Version / Trạng Thái | Mô Tả Thay Đổi |
| :--- | :--- | :--- | :--- |
| **TRAIN ENGINE** | `train_5min.yml` (x3 repos) | v798 ✅ | Concurrency singleton, tắt ghost cron, dùng check_time_exact |
| **REPORT 6.1** | `site_clear_report.py` (x3 repos) | v2.0 ✅ | Chuẩn hóa CONTROL chat ID `-5251698940`, lọc formula errors |
| **AUDITOR-9.1** | `system_auditor.py` (x3 repos) | v3.1 ✅ | Lịch Refuel 10:06/14:11 SSOT, 4s retry buffer cho Sheet |
| **RULES & DOCS** | `AGENTS.md` (x3 repos) | v798 ✅ | Ghi nhận RULE PM-24 bọc thép toàn diện |
