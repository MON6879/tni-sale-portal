# BACKUP CONTEXT — 12/09/2026 (Phiên bản v797)
# KHẮC PHỤC TRIỆT ĐỂ SỰ CỐ ĐỌNG TIN BÁO CÁO CABLE LINK DOWN (BOT 15) & THI HÀNH NGUYÊN TẮC DUY NHẤT 1 TIN MỚI NHẤT

---

## 1. BỐI CẢNH & YÊU CẦU NGƯỜI DÙNG
- **Yêu cầu Người dùng**: "đọc system map xóa sạch tin cũ chỉ để 1 tin mới nhất" (kèm ảnh chụp màn hình nhóm `8 TNI CABLE BROKEN SOS`).
- **Hiện trạng từ ảnh chụp**:
  - Nhóm Telegram `8 TNI CABLE BROKEN SOS` (`-5531350787`) bị đọng 2 bản tin Link Down Report liên tiếp:
    - Tin 1 lúc 10:18 MMT (Message ID 45).
    - Tin 2 lúc 11:18 MMT (Message ID 50).
  - Cả 2 bản tin cùng tồn tại, bản tin cũ không bị tự động xóa khi bản tin mới được đăng.

---

## 2. ĐIỀU TRA FORENSIC & NGUYÊN NHÂN GỐC (ROOT CAUSE FORENSICS)
Qua rà soát chuyên sâu từng Message ID thực tế qua Bot API Telegram và Google Apps Script:
1. **Lịch sử đọng tin thực tế**:
   - Quét toàn bộ Message ID trong nhóm cho thấy Bot 15 đã phát ra các tin báo cáo định kỳ: `45` (10:18), `47` (10:46), `50` (11:18), `52` (11:46).
   - Nguyên nhân bản tin cũ không bị xóa:
     - **Nguyên nhân 1 (Xung đột Ghost Cron)**: Workflow `train_5min.yml` còn lịch chạy tự động `schedule: - cron: '1/5 * * * *'` kích hoạt song song trên 3 repository (`Task and WO`, `tni-search`, `tni-sitedown-relay`). Khi nhiều runner chạy gần cùng lúc, runner sau gửi tin và ghi đè message ID mới vào GAS PropertiesService, khiến ID của runner trước bị mất dấu trong cơ sở dữ liệu và trở thành "tin mồ côi" (orphaned message) trên Telegram.
     - **Nguyên nhân 2 (URL Fallback trong delete_old_helper.py)**: Biến môi trường `APPS_SCRIPT_URL` trên GitHub Actions secrets nếu chứa deployment cũ (hoặc chuỗi không khớp) thì `delete_old_helper.py` ưu tiên gọi URL cũ trước dẫn đến timeout hoặc trả về mảng rỗng `[]`, khiến lệnh xóa tin cũ bị bỏ qua.
     - **Nguyên nhân 3 (Bảo vệ mảng rỗng khi xóa hết)**: Trong `delete_old_helper.py`, điều kiện `if not key or not msgids: return` khiến khi toàn bộ tin đã xóa xong (`msgids = []`), hàm return sớm mà không gọi GAS để xóa thuộc tính `MSGIDS_...`.

---

## 3. CÁC HÀNH ĐỘNG ĐÃ THỰC THI

### A. Dọn Sạch Toàn Bộ Tin Báo Cáo Cũ Trên Telegram
- Đã gọi Telegram Bot API `deleteMessage` xóa sạch 100% tất cả các bản tin báo cáo cũ:
  - Message ID 45 (10:18): **ĐÃ XÓA ✅**
  - Message ID 47 (10:46): **ĐÃ XÓA ✅**
  - Message ID 50 (11:18): **ĐÃ XÓA ✅**
  - Message ID 52 (11:46): **ĐÃ XÓA ✅**
  - Message ID 53: **ĐÃ XÓA ✅**
- Duy nhất chỉ còn **1 bản tin Link Down Report mới nhất** trong nhóm: Message ID 54!

### B. Bọc Thép delete_old_helper.py & cable_link_down_report.py
1. **Harden URL Fallback**: Ép buộc kiểm tra và chuyển hướng ngay về `MAIN_GAS_FALLBACK` (`AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA`) nếu `APPS_SCRIPT_URL` không hợp lệ hoặc chứa deployment cũ.
2. **Cho phép lưu mảng rỗng (`[]`)**: Sửa `if not key or msgids is None: return` để khi xóa hết tin, GAS PropertiesService được dọn sạch triệt để.
3. **Giữ mảng ID tích lũy**: Đảm bảo không bao giờ bị rơi rụng ID tin cũ nếu có lỗi mạng.

### C. Triệt Tiêu Hoàn Toàn Ghost Cron
- Comment out hoàn toàn `schedule: - cron:` trong `Task and WO/.github/workflows/train_5min.yml` và `tni-search/.github/workflows/train_5min.yml`.
- Duy nhất chỉ có 1 đầu tàu chạy cron tự động trên `MON6879/tni-sitedown-relay`, tuân thủ tuyệt đối **STRICT SINGLE-TRAIN RULE**.

---

## 4. BẢNG PHÂN HỆ & TRẠNG THÁI TRIỂN KHAI
| Ghế Phân Hệ | File | Version / Trạng thái | Mô Tả Thay Đổi |
| :--- | :--- | :--- | :--- |
| **BOT-CABLE-15** | `cable_link_down_report.py` | v1.1 ✅ | Harden URL fallback, tích hợp dọn sạch tin cũ chỉ để 1 tin mới nhất |
| **HELPER ENGINE** | `delete_old_helper.py` | v2.1 ✅ | Fix URL fallback chốt chặn deployment & cho phép lưu mảng rỗng `[]` |
| **TRAIN ENGINE** | `train_5min.yml` (x3 repos) | v797 ✅ | Vô hiệu hóa triệt để Ghost Cron trên Task and WO & tni-search |
