# 🧠 BACKUP CONTEXT — v823: FIX LỆNH /take_leave & /half_leave TRẢ VỀ TEMPLATE & XÓA FAKE LEAVE ROWS (RULE PM-48)

- **Timestamp**: 19/09/2026 17:35 MMT
- **Phân hệ**: Attendance (GAS-ATTENDANCE-4)
- **Deployment ID**: `AKfycbzSz_ISXgertxBDadw4BBQX1JdMjW650_o4He0o4Lh-uf1hV5O3YaE-ohlqI2CHyAcVFg` (@100)
- **Script ID**: `166XawHNCvkXmo7NGjydYJPTpaQMr1FTk_cqFSjFm8yiSxLEjsyr73XtW`
- **Spreadsheet ID**: `18zQB4i0Fu4QfKKkkUZUd6SKWIEbdWDiwdpgNSaL9v54` (tab `Sum report morning attendance`)
- **Group 10 (TNI DAILY ADDTENDANCE)**: `-5465634644`
- **Webhook Endpoint**: `https://tni-bot.vercel.app/api/attendance` (Vercel Proxy chống 302 redirect)

---

## 1. YÊU CẦU NGƯỜI DÙNG & HIỆN TƯỢNG SỰ CỐ
- **Hiện tượng**: Người dùng gửi ảnh chụp màn hình thắc mắc: *"sao tìm tempalte take leave mà ra cái gì vậy"*.
- **Chi tiết lỗi**: Khi người dùng gõ `/take_leave@TNI_DAILY_ADDTENDANCE_BOT` hoặc `/half_leave@TNI_DAILY_ADDTENDANCE_BOT` với mục đích tra cứu bản mẫu (template) cú pháp xin nghỉ phép để copy, Bot lại lập tức tự động ghi nhận người bấm là `TNI` đang nghỉ phép (Take Leave Full Day / Half Day Leave), chèn 2 dòng fake (`ATT-0035` và `ATT-0036`) vào tab `Sum report morning attendance` của Google Sheets và gửi tin nhắn xác nhận đã ghi nhận nghỉ phép.

---

## 2. NGUYÊN NHÂN GỐC (ROOT CAUSE — POST-MORTEM PM-48)
- Trong phiên cập nhật `@98`, nhánh code `if (cleanCmd === "/take_leave" || ...)` được đặt ở đầu xử lý text (dòng 213–274) để xử lý nhanh lệnh báo nghỉ. Nhánh này tự động lấy `senderName` rồi gọi `sumSheet.insertRowsBefore(2, 1)` chèn một dòng xin nghỉ vào Sheet mà không trả về bản mẫu.
- Việc này chặn đứng luồng tra cứu `isExplicitTemplateCommand` ở phía dưới, biến lệnh tra cứu mẫu thành lệnh hành động ghi đè dữ liệu.

---

## 3. CÁC THAY ĐỔI ĐÃ THỰC HIỆN
1. **Xóa bỏ hoàn toàn khối code tự chèn dòng nghỉ phép** (dòng 213–274 trong `TNI attendance.js`).
2. **Định tuyến toàn bộ biến thể lệnh báo nghỉ** (`/take_leave`, `/half_leave`, `/leave`, `/takeleave`, `/halfleave`, `/leave_half`, `/leavehalf`, `/template_leave`, `/template_leave_half`) vào `isExplicitTemplateCommand`.
3. **Nâng cấp `handleAttendanceTemplateQuery_()`**:
   - Trả về bản mẫu Markdown Code Block chuẩn, có hướng dẫn chạm vào để copy:
     - `/take_leave`: Trả về mẫu *Full Day Leave*.
     - `/half_leave`: Trả về mẫu *Half Day Leave*.
     - `/leave`: Trả về cả 2 mẫu *Full Day* & *Half Day*.
4. **Cập nhật mô tả Bot Command Menu**:
   - `take_leave` -> `Get template: Take leave full day`
   - `half_leave` -> `Get template: Take leave half day`
   - Gọi `setupAttendanceBotCommands()` để refresh danh sách command trên tất cả Scope của Telegram.
5. **Dọn sạch 2 dòng dữ liệu fake trên Sheet**:
   - Thêm action `delete_fake_leave` vào `doGet()`.
   - Gọi thực thi live qua GAS WebApp URL, đã xóa thành công 2 dòng fake `ATT-0035` và `ATT-0036` của `TNI`. Tab `Sum report morning attendance` đã sạch hoàn toàn.
6. **Deploy GAS Cloud**:
   - Chạy `clasp push --force` và `clasp deploy -i AKfycbzSz_ISXgertxBDadw4BBQX1JdMjW650_o4He0o4Lh-uf1hV5O3YaE-ohlqI2CHyAcVFg -d "v100: take_leave and half_leave return copyable templates"`.
   - Version mới `@100` đã hoạt động live.
7. **Đúc Rule PM-48**:
   - Đã ghi nhận Rule PM-48 vào toàn bộ 4 file `AGENTS.md` (Root, Task and WO, tni-search, tni-sitedown) và cập nhật `system_map.md`.
