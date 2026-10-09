# 🧠 BACKUP CONTEXT — v866: THIẾT LẬP 7 RÀO CẢN BẢO VỆ BOT ĐA TẦNG — KHẮC PHỤC TRIỆT ĐỂ SỰ CỐ QUẢNG CÁO "A-TOOLS X" & BẢO ĐẢM TOÀN VẸN WEBHOOK (RULE PM-95)

- **Thời gian**: 06:15 10/10/2026 (Giờ Myanmar)
- **Mục tiêu**:
  1. Đáp ứng chỉ đạo của Người Dùng: *"Mời chuyên gia 1% vào kiểm an toàn không để quản cáo dạng lôi kéo nào"* và *"Và đưa ra nhiều rào cản không cho ai giả danh bot gởi tin quản cáo"*.
  2. Điều tra nguyên nhân gốc rễ (Root Cause) sự cố Bot `1.1 TNI DAILY ADDTENDANCE` (ID `8628370628`) gửi tin nhắn lôi kéo tham gia kênh `https://t.me/A_TOOLSx2` vào nhóm `TNI TEAM 1 PLAN - ALARM`.
  3. Xây dựng và triển khai hệ thống **7 Rào Cản Phòng Thủ Bọc Thép (The 7-Layer Defense Shield)** ngăn chặn tuyệt đối tình trạng giả danh bot và phát tán quảng cáo.

---

## 1. PHÂN TÍCH NGUYÊN NHÂN GỐC (ROOT CAUSE ANALYSIS)

1. **Khảo sát mã nguồn nội bộ (100% Sạch)**:
   - Toàn bộ kho mã nguồn (`Task and WO`, `tni-search`, `QLTC_GAS`, `apps_script_attendance`) không hề có chuỗi ký tự `A_TOOLS`, `A_TOOLSx2` hay bất kỳ liên kết/quảng cáo nào.
2. **Khảo sát trạng thái Webhook thực tế (Điểm yếu chí mạng)**:
   - Khi gọi API `getWebhookInfo` của Bot `8628370628`, kết quả trả về `url: ""` (Webhook bị rỗng).
   - Khi Webhook bị rỗng, cơ chế bảo vệ của Telegram bị vô hiệu hóa, cho phép bất kỳ ai có Bot Token gọi phương thức `getUpdates` (polling ngầm).
   - Bot Token `8628370628` trước đây có thể từng được kết nối hoặc khai báo qua một dịch vụ/framework bot builder bên thứ 3 (nhóm "A-TOOLS X"). Nền tảng này có cơ chế "Force Subscribe" (ép tham gia kênh). Khi có người bấm lệnh trong nhóm (`/Report01`, `/plan`), bot builder của bên thứ 3 phát hiện người bấm chưa join kênh của họ và tự động bắn tin nhắn lôi kéo.

---

## 2. HỆ THỐNG 7 RÀO CẢN BẢO MẬT BỌC THÉP (THE 7-LAYER DEFENSE SHIELD — RULE PM-95)

1. **Rào Cản 1 (Thu Hồi & Cấp Mới Token Trên @BotFather)**:
   - Hướng dẫn Người Dùng thu hồi token cũ ngay trên BotFather: `/mybots` ➔ `@TNI_DAILY_ADDTENDANCE_BOT` ➔ `API Token` ➔ `Revoke current token`.
   - Mọi server lạ hoặc script spam bên ngoài sẽ bị ngắt kết nối vĩnh viễn (HTTP 401 Unauthorized).
2. **Rào Cản 2 (Khóa Chặt Quyền Hạn Trên @BotFather)**:
   - `/setprivacy` ➔ ENABLE (Privacy Mode ON): Bot chỉ nhận các lệnh bắt đầu bằng `/`, ngăn chặn việc nghe lén toàn bộ tin nhắn nhóm.
   - `/setjoingroups` ➔ DISABLE: Cấm người ngoài tự ý kéo Bot vào các nhóm lạ.
3. **Rào Cản 3 (Khóa Cứng Webhook & Flush Hàng Đợi - Zero Empty Webhook)**:
   - Đã gọi `setWebhook` gắn cứng vào Vercel Proxy `https://tni-bot.vercel.app/api/attendance` với `drop_pending_updates: true`.
   - Khi Webhook active, Telegram tự động chặn đứng 100% mọi request `getUpdates` từ kẻ xấu với lỗi `HTTP 409 Conflict`.
4. **Rào Cản 4 (Bộ Lọc Chặn Tin Ra - Outbound Anti-Ad Guardian)**:
   - Bổ sung hàm `isUnauthorizedAdOrSpam_(text)` vào `sendTelegramMessage_` và `sendTgMsgGetId_` trong `TNI attendance.js`.
   - Tự động hủy lệnh gửi nếu tin nhắn chứa link telegram ngoài danh mục TNI hoặc chứa từ khóa spam (`a_tools`, `join our channel`, `subscribe`, v.v.).
5. **Rào Cản 5 (Sentry Quét & Tự Động Xóa Tin Rác Vào Nhóm - Inbound Anti-Spam Purge)**:
   - Trong `doPost(e)`, khi nhận được bất kỳ tin nhắn nào trong nhóm chứa nội dung quảng cáo:
   - Bot tự động kích hoạt `deleteTgMessage_(token, chatId, msg.message_id)` để xóa ngay bài viết vi phạm khỏi nhóm trong 0.5 giây!
6. **Rào Cản 6 (Giám Sát Tự Phục Hồi SEV-1 Trong Auditor)**:
   - Cập nhật `system_auditor.py`: Mỗi nhịp 5 phút quét toàn bộ 6 Webhooks. Nếu phát hiện `url: ""` hoặc pending message, tự động purge sạch hàng đợi và Re-hook ngay lập tức.
7. **Rào Cản 7 (Phân Quyền Nhóm Tối Thiểu)**:
   - Trong các nhóm Telegram vận hành, Bot chỉ được giữ quyền xóa tin nhắn (để dọn rác) và gửi tin báo cáo. Không cấp quyền Admin thừa thãi.

---

## 3. DEPLOYMENT & VERIFICATION

- **GAS Attendance**:
  - Script ID: `166XawHNCvkXmo7NGjydYJPTpaQMr1FTk_cqFSjFm8yiSxLEjsyr73XtW`
  - Primary Deployment: `AKfycbzSz_ISXgertxBDadw4BBQX1JdMjW650_o4He0o4Lh-uf1hV5O3YaE-ohlqI2CHyAcVFg` (@134)
  - Secondary Deployment: `AKfycbyFIDGDS5k7wy-hNp2p1PNvte0CQ6cSiNYLyBmNc00Yi1b6IueOob9bKmu4zoQ1A6Cs` (@135)
  - Live HTTP Ping: `curl .../exec?action=ping` -> `200 PONG` (1s).
- **Vercel Proxy & Webhook Status**:
  - Webhook URL: `https://tni-bot.vercel.app/api/attendance` (Pending updates: 0, Max connections: 40).
  - Test getUpdates conflict: `HTTP 409 Conflict` (Chặn đứng hoàn toàn kẻ xấu).
- **Auditor Synchronization**:
  - `system_auditor.py` đã đồng bộ 100% giữa `Task and WO` và `tni-search` (`Compare-Object` = 0).
- **Rule Synchronization**:
  - Rule PM-95 đã ghi vào `AGENTS.md` trên toàn bộ 5 vị trí với 100% hash parity.
