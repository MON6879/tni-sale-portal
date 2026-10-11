# Backup Context Snapshot — Version 864 (2026-10-09)

## Overview: Khắc Phục Lỗi Cào Thiếu & Sai Lệch Báo Cáo Tổng Hợp Site Down Team 3 (Rule PM-91)

### 1. Bối Cảnh & Sự Cố
- Người dùng phát hiện và phản ánh:
  1. *"sao không thu thập có cái thu có cái không vậy"*
  2. *"sao file gốc có 3 Site Team 3 mà hai báo cáo tổng hợp sai là sao"*
  Kèm 3 ảnh chụp màn hình chứng minh:
  - Bảng tính Google Sheet `1 🔒 Input Site down Telegram`, ô `AY7` có 3 trạm Team 3 (`TNI0416 : 7.9, TNI0105 : 283.8, TNI0402 : 285.7`).
  - Bản tin `SUMMARY — SITE DOWN ALL TEAMS` gửi vào nhóm `5 TNI TECHNICA DEP CONTROL SITE` lúc 05:48 chỉ có 1 trạm (`TNI0416 : 7.5`).
  - Bản tin `SUMMARY — ALL TEAMS` gửi vào nhóm `5 TNI TECHNICA DEP CONTROL SITE` lúc 05:48 cũng chỉ có 1 trạm (`TNI0416 : 7.5`).
- Mật khẩu mở Khóa Thép: `UNLOCK STEEL: Phucat@7979`.

### 2. Nguyên Nhân Gốc (Root Cause Analysis)
1. **Lỗi Cào Thiếu Data trong `botlookup_relay.py`**:
   - Khi chatbot `@auto_nocpro_bot` trả về dữ liệu 29 trạm sự cố, Telegram tự động chia phản hồi thành nhiều tin liên tiếp.
   - Tin 1 có header `"Tanintharyi Region"` + các trạm mới sập. Tin 2+ chứa các trạm sập lâu ngày (>100h) và không có chữ `"tanintharyi"`.
   - File `botlookup_relay.py` trong repo `Task and WO` bị trôi phiên bản (chỉ lọc `tni_messages = [m for m in bot_messages if "tanintharyi" in m.lower()]` và lấy `tni_messages[-1]`), làm rớt toàn bộ Tin 2 (trong đó có `TNI0105` và `TNI0402` của Team 3).
2. **Khóa Dedup Ô AW7 Bị Nghẽn Bỏ Sót Cập Nhật Dữ Liệu**:
   - Để ngăn lặp tin do công thức Duration nhảy số (`7.5h` -> `7.6h`), Rule PM-83 chỉ dedup bằng chuỗi mốc giờ `tsKey` (`09/10/2026 05:46`).
   - Khi dữ liệu trạm được bổ sung lên Sheet (từ 1 lên 3 trạm), mốc giờ `tsKey` vẫn là `05:46`.
   - Hàm `processSummaryAwAz` kiểm tra `tsKey === lastTs` thấy trùng nên chặn 100%, không gửi cập nhật sang Telegram dù bảng tính đã đủ 3 trạm.

### 3. Giải Pháp Bọc Thép (Rule PM-91)
1. **Đồng Bộ Hoá 100% `botlookup_relay.py` Đa Phần (Dual-Condition Multi-Part)**:
   - Sử dụng `is_tni_data_msg(m)` (`"tanintharyi" in m` OR `any(line[:3] == "TNI")`) và `\n.join(tni_parts)` đồng bộ qua cả 3 repositories (`Task and WO`, `tni-search`, `tni-sitedown`).
2. **Dedup Bằng Station Signature Chống Nhảy Số Duration**:
   - Signature: `sigKey = tsKey + "__CNT:" + counts + "__SITES:" + sitesSig`.
   - Khi Duration nhảy số: `sigKey` không đổi $\rightarrow$ Chặn lặp 100%.
   - Khi số lượng hoặc mã trạm thay đổi: `sigKey` thay đổi $\rightarrow$ Cho phép gửi cập nhật ngay lập tức!
3. **Kích Hoạt `processSummaryAwAz` Trong `store_site_down`**:
   - Sau khi ghi Cột A và tính toán Cột C, tự động gọi `processSummaryAwAz(sheet, false)` để đồng bộ Tin 2 ngay lập tức nếu danh sách trạm thay đổi.

### 4. Kết Quả Triển Khai & Phúc Tra Live
- Google Apps Script `apps_script_sitedown`: Version `@111` (Deployment `AKfycbyCibIj4QN7oG5BZc_ju1iS-DUmd9nNdrMn9UN-WD8qf6jVoU_OKOf2yfbi10qGMFF-`).
- Live Verify 1: POST `action=process_aw_az` $\rightarrow$ `HTTP 200 {"ok":true,"sent_tin2":true}` (đã cập nhật thành công 3 trạm Team 3, 18 trạm Team 1, 11 trạm Team 2 sang Telegram).
- Live Verify 2: POST `action=process_aw_az` $\rightarrow$ `HTTP 200 {"ok":true,"sent_tin2":false}` (dedup chặn lặp thành công).
- Tri-Repo Parity: 100% đồng bộ `botlookup_relay.py`, `site_down_v2.gs`, và `AGENTS.md`.
- Khóa Thép Site Down tự động đóng lại theo đúng quy tắc an toàn.
