# 📋 BACKUP CONTEXT — 18/09/2026 (Phiên v821)
# Xử Lý Triệt Để Lỗi 2 Tin Trùng Nhau Không Xóa Tin Cũ (Report 5 EOD & Updated), Bọc Thép Multi-Key Purge, Tri-Repo Parity & Deploy Main GAS @445 (RULE PM-46)

---

## 1. BỐI CẢNH & PHẢN HỒI TỪ NGƯỜI DÙNG

- **Yêu cầu từ Người Dùng**:
  ```text
  sao 2 tin trùng nhau không xóa tin cũ đi
  ```
- **Hình ảnh đính kèm từ Telegram Group (`TNI TEAM 3 PLAN - ALARM`, chat_id `-1004369170658`)**:
  - **Tin nhắn 1 (18:43 MMT)**:
    `📋 5. Report [EOD] — Daily Plan & Results (18/09/2026) — Team3 Bokpyin`
    `📅 18/09/2026 | 🕒 18:43`
    `📌 Comparison of plan for 18/09/2026 vs actual completed stations.`
  - **Tin nhắn 2 (19:15 MMT)**:
    `📋 5. Report [Updated] — Daily Plan & Results (18/09/2026) — Team3 Bokpyin`
    `📅 18/09/2026 | 🕒 19:15`
    `📌 Comparison of plan for 18/09/2026 vs actual completed stations.`
  - Cả 2 tin nhắn có nội dung so sánh tiến độ kế hoạch trong ngày giống hệt nhau, hiển thị nối tiếp nhau trong nhóm chat mà tin cũ [EOD] không bị xóa khi tin mới [Updated] phát ra.

---

## 2. NGUYÊN NHÂN GỐC (ROOT CAUSE FORENSICS)

1. **Phân Mảnh Khóa Lưu Trữ GAS PropertiesService (`Storage Key Partitioning`)**:
   - Trong `daily_plan_report.py`, hàm `run_eod_or_update(mode)` khai báo:
     ```python
     mode_label = "EOD" if mode == "eod" else "Updated"
     delete_prefix = "PLAN_EOD" if mode == "eod" else "PLAN_UPD"
     delete_key = f"{delete_prefix}_{group_key}"
     ```
   - Tại nhịp 18:41 (Toa 3 - EOD), tin nhắn phát ra có `msg_id = 6547` và được lưu vào GAS dưới khóa `PLAN_EOD_T3`.
   - Đến nhịp 19:11 (Toa 4 - Updated), script chuyển sang dùng khóa `delete_key = "PLAN_UPD_T3"`.
   - Khi gọi `delete_old_messages_bot(..., delete_key="PLAN_UPD_T3")`, do khóa `PLAN_UPD_T3` chưa tồn tại hoặc rỗng trong ngày, hàm hoàn toàn không biết đến `msg_id = 6547` đang nằm ở `PLAN_EOD_T3`. Vì vậy, Bot API không xóa tin cũ!

2. **Bộ Lọc Tiêu Đề Telethon Quá Hẹp (`Overly Strict Title Match`)**:
   - Đoạn code dự phòng xóa qua Telethon tiêu đề:
     ```python
     tg_delete_by_title(str(chat_id), f"📋 5. Report [{mode_label}]", bot_token=SEND_BOT_TOKEN)
     ```
   - Khi nhịp Updated chạy, `mode_label == "Updated"`, hàm chỉ tìm kiếm chuỗi `"📋 5. Report [Updated]"`.
   - Chuỗi này hoàn toàn không khớp với `"📋 5. Report [EOD]"` của tin nhắn lúc 18:43.
   - Kết quả: Cả cơ chế Bot API và cơ chế Telethon đều trượt việc xóa tin EOD!

3. **Lệch Đồng Bộ Giữa Các Repository (Tri-Repo Out-of-Sync)**:
   - File `daily_plan_report.py` trên runner GHA (`tni-sitedown`) không được đồng bộ đầy đủ các cải tiến dọn tin và lọc nhóm từ `Task and WO`, dẫn đến quy trình xóa tin cũ bị rẽ nhánh và tích tụ rác.

---

## 3. GIẢI PHÁP ĐÃ TRIỂN KHAI TRIỆT ĐỂ (RULE PM-46)

1. **Xóa Ngay Lập Tức Tin Rác Đang Tồn Đọng Bằng Bot API**:
   - Truy vấn trực tiếp PropertiesService của GAS, lấy ra `msg_id = 6547` tại `PLAN_EOD_T3` và `msg_id = 12956` tại `PLAN_EOD_CONTROL`.
   - Kích hoạt gọi Telegram Bot API `deleteMessage` xóa sạch ngay lập tức tin nhắn trùng lặp 6547 trong nhóm Team 3 và tin nhắn 12956 trong nhóm CONTROL (`{"ok":true,"result":true}`).

2. **Thống Nhất Khóa Lưu Trữ & Quét Sạch Mọi Khóa Phụ (`Multi-Key Purge`)**:
   - Chuẩn hóa `delete_prefix = "PLAN_5B"` cho cả 2 nhịp EOD và Updated.
   - Trước khi phát tin mới, hệ thống duyệt và dọn sạch qua Bot API tất cả các khóa:
     `PLAN_5B_{group_key}`, `PLAN_EOD_{group_key}`, `PLAN_UPD_{group_key}`.
   - Sau khi gửi tin mới thành công, lưu `msg_ids` đồng thời vào `PLAN_5B_{group_key}` và `PLAN_{mode_label}_{group_key}`, đồng thời reset rỗng (`[]`) khóa của mode đối nghịch (`save_msgids(..., f"PLAN_{other_mode}_{group_key}", [])`).
   - Áp dụng tương tự cho cả nhóm CONTROL (`PLAN_5B_CONTROL`, `PLAN_EOD_CONTROL`, `PLAN_UPD_CONTROL`).

3. **Nâng Cấp Xóa Tiêu Đề Cấp Cao Telethon (`High-Level Root Purge`)**:
   - Thay thế việc truyền tiêu đề gắn nhãn mode bằng việc quét tiêu đề gốc cấp cao:
     `tg_delete_by_title(str(chat_id), "📋 5. Report", bot_token=SEND_BOT_TOKEN)`
     `tg_delete_by_title(str(chat_id), "📋 5B. Plan today compare Result", bot_token=SEND_BOT_TOKEN)`
   - Chuỗi `"5. report"` bao trùm cả `[EOD]` và `[Updated]`, bảo đảm xóa sạch mọi tin tối trước đó mà hoàn toàn không ảnh hưởng đến tin sáng (`5.1 Report` / `5A. Plan daily`).

4. **Tri-Repo Parity 100%**:
   - Đồng bộ 100% nội dung `daily_plan_report.py`, `system_auditor.py`, `AGENTS.md` qua cả 3 kho lưu trữ: `Task and WO`, `tni-search`, `tni-sitedown`.
   - Kiểm thử biên dịch `py_compile` trên cả 3 file: 0 lỗi.

5. **Deploy Main GAS @445**:
   - Đẩy 20 file lên dự án `QLTC_GAS` và cập nhật Primary Deployment ID `AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA` lên Version `@445`.
   - Cập nhật nhãn SSOT `@445` cho `system_auditor.py` trên cả 3 repos.

---

## 4. KẾT QUẢ PHÚC TRA THỰC TẾ (LIVE VERIFICATION)

- **Xóa tin nhắn 6547 tại nhóm Team 3 (`-1004369170658`)**: `{"ok":true,"result":true}` (Thành công 100%).
- **Xóa tin nhắn 12956 tại nhóm CONTROL (`-5251698940`)**: `{"ok":true,"result":true}` (Thành công 100%).
- **Deploy Main GAS Version**: `@445` (Primary Deployment ID active).
- **Tri-Repo Parity Check**:
  - `daily_plan_report.py`: `Compare-Object` = 0 (100% khớp).
  - `system_auditor.py`: `Compare-Object` = 0 (100% khớp).
  - `AGENTS.md`: `Compare-Object` = 0 (100% khớp).
