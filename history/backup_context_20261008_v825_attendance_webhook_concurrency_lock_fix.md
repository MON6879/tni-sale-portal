# 🧠 BACKUP CONTEXT — v825: BỌC THÉP CONCURRENCY ĐIỂM DANH NHÓM 10 (RULE PM-90)

- **Thời gian**: 2026-10-08 21:30 MMT
- **Phân hệ**: Attendance System (Ghế `GAS-ATTENDANCE-4`)
- **Tác nhân**: Antigravity Pair-Programming
- **Script ID**: `166XawHNCvkXmo7NGjydYJPTpaQMr1FTk_cqFSjFm8yiSxLEjsyr73XtW`
- **Spreadsheet ID**: `18zQB4i0Fu4QfKKkkUZUd6SKWIEbdWDiwdpgNSaL9v54`
- **Group 10 (TNI DAILY ADDTENDANCE)**: `-5465634644`
- **Deployments cập nhật**:
  - Deployment 1: `AKfycbzSz_ISXgertxBDadw4BBQX1JdMjW650_o4He0o4Lh-uf1hV5O3YaE-ohlqI2CHyAcVFg` -> `@130`
  - Deployment 2: `AKfycbyFIDGDS5k7wy-hNp2p1PNvte0CQ6cSiNYLyBmNc00Yi1b6IueOob9bKmu4zoQ1A6Cs` -> `@131`

---

## 1. HIỆN TƯỢNG VÀ YÊU CẦU NGƯỜI DÙNG
- Người dùng phản ánh: *"sao không thu thập có cái thu có cái không vậy"* kèm ảnh chụp màn hình nhóm Telegram **10. TNI DAILY ADDTENDANCE** vào sáng 08/10/2026:
  + 08:38: User PT gửi ảnh có Timemark (TNI0008, 12.089324°N, 99.011583°E).
  + 08:39: User KT (Khant Si thu T3) gửi ảnh có Timemark.
  + 08:40: User MT (Maung maung T2) gửi ảnh có Timemark.
- Cả 3 lượt gửi trên hoàn toàn KHÔNG được bot ghi nhận vào tab `List Attendance` và bot không phản hồi tin nhắn trong nhóm.
- Ngược lại, vào các khung giờ sau đó (09:07, 09:11, 09:52, 10:31, 12:04, 12:11, 12:52, 13:48, 15:44), các tin nhắn gửi riêng lẻ cách nhau vài chục phút đến vài tiếng lại được bot thu thập thành công 100%.

---

## 2. NGUYÊN NHÂN GỐC (ROOT CAUSE ANALYSIS — POST-MORTEM PM-90)
1. **Nghẽn Concurrency & Timeout 25s do tích hợp hàm Rebuild toàn bộ Sheet vào doPost**:
   - Trong `doPost(e)` của `TNI attendance.js`, mỗi khi có 1 ảnh nộp vào bot, hệ thống tự động gọi đồng bộ 2 hàm:
     + `buildGeneralTab()` (quét toàn bộ lịch sử điểm danh, tính toán cho 56 nhân sự, vẽ lại bảng General): mất **17.36 giây**!
     + `buildSumWorkTab()` (quét và tính toán lại toàn bộ công tháng của mọi nhân viên, vẽ lại bảng Sum work): mất **10.55 giây**!
   - Tổng thời gian xử lý 1 ảnh lên tới **35 ~ 40 giây**!
   - Trong khi đó, proxy Vercel (`api/attendance.py`) chỉ cấu hình `timeout=25` (25 giây).
   - Vào khung giờ cao điểm sáng (**08:30 - 08:45 MMT**), các đội đồng loạt gửi ảnh điểm danh dồn dập vào cùng 1 thời điểm.
   - Request đầu tiên chiếm dụng tài nguyên GAS trong 35-40s. Các request tiếp theo bị nghẽn (do Google Sheets bị lock tài nguyên), chờ quá 25s ➔ Vercel bị `ReadTimeout`!
2. **Anti-pattern trả về HTTP 200 khi Vercel gặp Exception nuốt chửng tin nhắn**:
   - Khi bị `ReadTimeout`, khối `except Exception as e` của `api/attendance.py` lại gửi `self.send_response(200)` cho Telegram!
   - Telegram nhận HTTP 200 ➔ Nhầm tưởng tin nhắn đã được xử lý xong và **XÓA BỎ VĨNH VIỄN CÁC TIN ĐÓ KHỎI HÀNG ĐỢI, KHÔNG BAO GIỜ RETRY** (thực tế mất 28 updates Telegram từ 770994826 đến 770994854).
3. **Thiếu LockService trên GAS**:
   - Các luồng nhận ảnh đồng thời không có khóa độc quyền, tranh chấp vị trí dòng số 2 trên `List Attendance` gây lỗi `SpreadsheetApp concurrent access error` hoặc ghi đè / mất dòng.
4. **Hàm getAttendanceSlot_ cắt mốc hẹp (< 08:30)**:
   - Làm các ảnh gửi từ 08:31 đến 09:30 bị gán vào `slot_custom_8`, làm sai lệch thống kê và nguy cơ bị chặn nhầm.

---

## 3. CÁC BIỆN PHÁP ĐÃ THỰC THI & KHẮC PHỤC TRIỆT ĐỂ
1. **Tách rời 100% `buildGeneralTab()` và `buildSumWorkTab()` ra khỏi luồng `doPost`**:
   - `doPost` chỉ làm: download ảnh từ Telegram, lưu Drive, chèn 1 dòng vào `List Attendance`, gửi tin xác nhận Telegram (`✅ Recorded #...`).
   - Thời gian thực thi `doPost` rút ngắn từ **37 giây** xuống chỉ còn **3 ~ 5 giây** (nhanh gấp 8 lần, không bao giờ lo chạm trần timeout).
   - Di dời `buildGeneralTab()` và `buildSumWorkTab()` về chạy định kỳ sau khi chốt đợt template trong `sendDailyAttendanceTemplates()` (08:45 và 09:15 MMT) và `sendDailyAttendanceReport()` (09:00 MMT), hoặc khi người dùng gọi `/sum_work`.
2. **Bọc thép LockService 10s cho thao tác ghi Sheet**:
   - Sử dụng `LockService.getScriptLock()` với `waitLock(10000)` bảo vệ độc quyền đoạn kiểm tra STT `nextNum`, kiểm tra trùng lặp và ghi dòng `insertRowAfter(1)` + `setValues`.
   - Vì thời gian trong lock chỉ mất ~200-500ms, hàng chục nhân sự nộp ảnh cùng lúc được xử lý tuần tự mượt mà trong vài giây.
3. **Chuẩn hóa slot sáng trong `getAttendanceSlot_`**:
   - Mở rộng `totalMin <= 9 * 60 + 30` (đến 09:30 MMT) cho `slot_morning_1`.
4. **Sửa Vercel Proxy trả HTTP 504 khi có lỗi**:
   - Đổi mã trả về trong `except` của `api/attendance.py` thành HTTP 504 Gateway Timeout để Telegram giữ tin và retry nếu mạng chập chờn.
5. **Deploy Cloud & Phúc tra Live**:
   - `clasp push --force` thành công 2 file `appsscript.json` và `TNI attendance.js`.
   - Deploy cập nhật Deployment 1 lên `@130` và Deployment 2 lên `@131`.
   - Kiểm tra HTTP Live: phản hồi HTTP 200 trong 5.00s.
   - Chạy test làm mới thành công cả 2 tab `General` và `Sum work`.

---

## 4. QUY TẮC ĐÚC RÚT VÀO AGENTS.MD (RULE PM-90)
- **RULE PM-90 — Bọc Thép Concurrency Điểm Danh Nhóm 10: Tách Khối Rebuild Nặng Khỏi Webhook doPost, Bảo Vệ LockService 10s & Chống Timeout Nuốt Tin**: Đã đồng bộ vào toàn bộ 4 file `AGENTS.md` của hệ thống.
