# 🧠 BACKUP CONTEXT — v824: FIX LỖI OBJECT OBJECT TÊ LIỆT XÓA TIN CŨ ĐIỂM DANH GROUP 10 (RULE PM-33)

- **Thời gian**: 2026-10-05 17:45 MMT
- **Phân hệ**: Attendance Report (Ghế `GAS-ATTENDANCE-4`)
- **Tác nhân**: Antigravity Pair-Programming
- **Script ID**: `166XawHNCvkXmo7NGjydYJPTpaQMr1FTk_cqFSjFm8yiSxLEjsyr73XtW`
- **Spreadsheet ID**: `18zQB4i0Fu4QfKKkkUZUd6SKWIEbdWDiwdpgNSaL9v54`
- **Group 10 (TNI DAILY ADDTENDANCE)**: `-5465634644`
- **Deployments cập nhật**:
  - Deployment 1: `AKfycbzSz_ISXgertxBDadw4BBQX1JdMjW650_o4He0o4Lh-uf1hV5O3YaE-ohlqI2CHyAcVFg` -> `@123`
  - Deployment 2: `AKfycbyFIDGDS5k7wy-hNp2p1PNvte0CQ6cSiNYLyBmNc00Yi1b6IueOob9bKmu4zoQ1A6Cs` -> `@124`

---

## 1. HIỆN TƯỢNG VÀ YÊU CẦU NGƯỜI DÙNG
- Người dùng gửi ảnh chụp màn hình nhóm Telegram **10. TNI DAILY ADDTENDANCE** vào lúc 16:35 ngày 05/10/2026 kèm yêu cầu:
  *"Xóa tin cũ đi chứ sao lặp lại lỗi rồi"*
- Trên ảnh hiển thị các tin nhắn điểm danh của các đội (Team 1, Team 2 Main, Team 2 S1, Team 3 Main...) gửi lúc 08:47 sáng bị lặp lại nhiều lần, các tin nhắn cũ từ các đợt chạy trước không hề được tự động xóa trước khi gửi đợt mới.

---

## 2. NGUYÊN NHÂN GỐC (ROOT CAUSE ANALYSIS — POST-MORTEM PM-33)
1. **Thay đổi kiểu dữ liệu trả về của hàm tiện ích `sendTgMsgGetId_`**:
   - Ở commit `3b9276c`, hàm `sendTgMsgGetId_` được cải tiến để trả về một Object: `{ ok: boolean, messageId?: number, error?: string }` (thay vì trả về số nguyên `message_id` như phiên bản ban đầu).
   - Hàm `sendDailyAttendanceReport` đã được cập nhật để trích xuất `sendRes.messageId`.
2. **Bỏ quên 2 hàm gửi template điểm danh vào Group 10**:
   - Trong `sendDailyAttendanceTemplates()` (dòng 1504):
     ```javascript
     var newMid = sendTgMsgGetId_(token, DAILY_ATT_CHAT, msgText);
     if (newMid) props.setProperty("daily_tpl_" + tpl.key + "_mid", String(newMid));
     ```
   - Trong `sendGroup10MembershipSummary()` (dòng 1737):
     ```javascript
     var newMid = sendTgMsgGetId_(token, DAILY_ATT_CHAT, fullMsg);
     if (newMid && (!targetChatId || targetChatId === DAILY_ATT_CHAT)) {
       props.setProperty("daily_tpl_summary_mid", String(newMid));
     }
     ```
   - Lệnh `String(newMid)` đã ép kiểu cả đối tượng JavaScript thành chuỗi **`"[object Object]"`** và lưu vào `ScriptProperties`.
3. **Luồng xóa tin cũ bị tê liệt hoàn toàn**:
   - Khi trigger nhịp tiếp theo (09:15 MMT hoặc bất kỳ đợt chạy sau) kích hoạt, code đọc `oldMid` từ `ScriptProperties`, nhận về chuỗi `"[object Object]"`.
   - Hàm `deleteTgMessage_` thực hiện `Number("[object Object]")` ra kết quả `NaN`.
   - Payload gửi lên Telegram API `/deleteMessage` có dạng `{"chat_id": -5465634644, "message_id": null}`, bị Telegram từ chối với mã lỗi `400 Bad Request`.
   - Các tin nhắn cũ của đợt 08:45 không hề bị xóa, trong khi đợt 09:15 tiếp tục gửi đè xuống dưới khiến toàn bộ danh sách điểm danh 8 đội và bảng thành viên bị nhân bản lặp lại trong nhóm.

---

## 3. CÁC THAO TÁC ĐÃ XỬ LÝ & BẢO ĐẢM TRIỆT ĐỂ

1. **Dọn sạch toàn bộ 24 tin nhắn mồ côi cũ của Bot trong Group 10**:
   - Rà soát xác thực an toàn qua Telegram API, chỉ nhắm đúng tin nhắn do Bot (`id: 8628370628`) gửi đi, bảo đảm 100% không đụng chạm đến tin nhắn của nhân viên và người dùng.
   - Đã xóa sạch 2 đợt tin cũ tích tụ: đợt 08:47 (`[3838, 3840..3845, 3848, 3850, 3852, 3857]`) và đợt sau (`[3858..3865, 3867, 3869, 3871, 3873, 3875]`).
2. **Sửa code trích xuất số nguyên `messageId`**:
   - Cập nhật cả 2 hàm `sendDailyAttendanceTemplates` và `sendGroup10MembershipSummary`:
     ```javascript
     var newMid = sendTgMsgGetId_(token, DAILY_ATT_CHAT, msgText);
     if (newMid && newMid.ok && newMid.messageId) {
       props.setProperty("daily_tpl_" + tpl.key + "_mid", String(newMid.messageId));
     }
     ```
3. **Bọc thép bảo vệ hàm `deleteTgMessage_` & `delete_templates_now`**:
   - Chặn đứng các giá trị chuỗi rác `"[object Object]"` và `NaN` trước khi gọi Telegram API:
     ```javascript
     if (!mid || mid === "[object Object]" || isNaN(Number(mid))) continue;
     ```
4. **Deploy Cloud & Phúc tra Live**:
   - `clasp push --force` đẩy code lên Google Apps Script.
   - Deploy cập nhật đồng thời Deployment `@123` và Deployment `@124`.
   - Chạy test live `delete_templates_now`: Đã xóa thành công 9 tin với ID số thực sự: `["3884","3885","3886","3887","3888","3889","3890","3891","3892"]`.
   - Kích hoạt gửi 1 bộ tin mẫu chuẩn mới nhất qua `send_templates_now` (lưu ID số từ `3893` đến `3901`), đảm bảo từ nay các đợt chạy 08:45 và 09:15 sẽ tự động xóa sạch tin cũ của đợt trước.

---

## 4. QUY TẮC ĐÚC RÚT VÀO AGENTS.MD (RULE PM-33)
- **RULE PM-33 — Trích Xuất Message ID Số Nguyên Khi Lưu Vào ScriptProperties Chống Lỗi Object Object Làm Liệt Luồng Xóa Tin Cũ**: Bắt buộc trích xuất `res.messageId` và bọc kiểm tra `!mid || mid === "[object Object]" || isNaN(Number(mid))` trong toàn bộ luồng xóa tin. Đã đồng bộ vào 4 file `AGENTS.md` của toàn hệ thống.
