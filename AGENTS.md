# 🇬🇧 STRICT RULE: CHATBOT RESPONSES & TEMPLATE CONTENTS MUST BE IN ENGLISH

> ⚠️ **QUY TẮC BẮT BUỘC**: TOÀN BỘ NỘI DUNG PHẢN HỒI TỰ ĐỘNG, THÔNG BÁO, MENU VÀ TEMPLATE CỦA CHATBOT GỬI TRÊN TELEGRAM BẮT BUỘC PHẢI BẰNG TIẾNG ANH 100% (ENGLISH ONLY FOR ALL BOT MESSAGES & TEMPLATES).

---

# ⏰ STRICT SCHEDULE RULE: REPORT 1, 2, 3, 4 DAILY SENDING TIMES

> ⚠️ **QUY TẮC BẮT BUỘC**: THỜI GIAN GỬI BÁO CÁO TỰ ĐỘNG CHO REPORT 1, 2, 3, 4 (TEAMS 1 TO 4 VIA GITHUB ACTIONS — TOA 1+11) LÀ ĐÚNG **05:48 AM** VÀ **15:48 PM** HÀNG NGÀY; VÀ TOA BOTLOOKUP RELAY LÀ ĐÚNG PHÚT **:06** VÀ **:36** HÀNG GIỜ (MÚI GIỜ MYANMAR `Asia/Yangon` UTC+6:30).

---

# 🛡️ STRICT RULE: ĐỌC VÀ TUÂN THỦ TUYỆT ĐỐI DOCUMENTATION TRƯỚC KHI SỬA KẾT NỐI & ENDPOINT

> ⚠️ **QUY TẮC BẮT BUỘC**: TUYỆT ĐỐI KHÔNG ĐƯỢC TIỆN TAY THAY ĐỔI HOẶC ĐOÁN ĐƯỜNG DẪN WEBHOOK / ENDPOINT CỦA BẤT KỲ BOT NÀO. PHẢI KIỂM TRA DOCS CHUẨN TRƯỚC KHI THỰC HIỆN!

---

# 📥 STRICT DATA COLLECTION RULE: NEWEST DATA ALWAYS INSERTED AT THE VERY TOP

> ⚠️ **QUY TẮC BẮT BUỘC THU THẬP DỮ LIỆU**: MỌI BỘ THU THẬP THÔNG TIN (MDG REPORT, INVENTORY, REFUEL REQUEST, DAILY REPORT, DAILY PLAN, READ GROUP LOGS, V.V.) KHI GHI VÀO GOOGLE SHEETS BẮT BUỘC PHẢI CHÈN DỮ LIỆU MỚI LÊN ĐẦU BẢNG TÍNH (DÒNG 2, NGAY BÊN DƯỚI HÀNG TIÊU ĐỀ HEADER ROW 1 DÙNG `insertRowsBefore(2, ...)` HOẶC RECORD DÒNG 2). TUYỆT ĐỐI KHÔNG ĐƯỢC NỐI DỮ LIỆU VÀO CUỐI BẢNG TÍNH (`appendRow`) LÀM NGƯỜI DÙNG PHẢI KÉO XUỐNG DƯỚI!

---

## 📌 1. Bản đồ Webhook Cố Định (Strict Endpoint Registry)

Mọi thao tác cài đặt hoặc khôi phục Webhook Telegram đều phải đối chiếu chính xác 100% với danh sách sau:

| Bot Name | Telegram Username | Webhook Endpoint URL | File Handler trong Codebase |
|---|---|---|---|
| **Search Bot** | `@SEARCHTNITASKWOBOT` | `https://tni-bot.vercel.app/api/search_bot` | `api/search_bot.py` |
| **Asset Bot (Collector)** | `@TNIASSETorderREQUEST_BOT` | `https://tni-bot.vercel.app/api/collector` | `api/collector.py` |
| **Site Down Bot (Relay)** | `@tni_site_down_bot` | `https://tni-bot.vercel.app/api/site_down_relay` | `botlookup_relay.py` |
| **Construction Bot** | `@8903841312` (`10 TNI_SITE`) | Apps Script Web App Endpoint | `13_TNI_CONSTRUCTION.gs` |

---

## 📋 2. Quy trình 3 bước bắt buộc trước khi chỉnh sửa:

1. 📖 **Đọc lại Docs hiện hành**: Phải đọc `SYSTEM_DOC.md`, `system_map.md` và `history/backup_context_...md` trước khi gọi bất kỳ lệnh `setWebhook` hay sửa URL kết nối nào.
2. 🔍 **Xác minh Bot Token & Webhook URL**: Tuyệt đối không gán nhầm Bot Token của Search Bot (`@SEARCHTNITASKWOBOT`) vào Webhook của Site Down Relay hay Collector.
3. 💾 **Thực hiện đủ 7 bước Quy tắc "LƯU ĐI" bắt buộc**:
   - **Bước 1:** Cập nhật snapshot backup context vào `history/backup_context_...md`.
   - **Bước 2:** Đồng bộ mã nguồn Python/GS qua tất cả các repo cục bộ (`tni-bot` & `tni_site_down_repo`).
   - **Bước 3:** Commit & Push lên GitHub (`phonghdpxd-cmd/tni-bot` & `phonghdpxd-cmd/TNI-SITE-DOWN`).
   - **Bước 4:** Dọn dẹp sạch sẽ tất cả cache `__pycache__`.
   - **Bước 5:** **Đồng bộ 100% tất cả logic liên quan (Full Logical Cross-Sync)** — Khi sửa Endpoint/URL/Cron Schedule/Tra cứu, phải đồng bộ tức thì tất cả các file code, workflow step condition, fallback variables và tài liệu docs liên quan.
   - **Bước 6:** **Kiểm thử thực tế (Live Output Verification)** — Chạy test payload/script để xác nhận 0 lỗi phát sinh và phản hồi thực tế chính xác 100%.
   - **Bước 7:** **Báo cáo rõ Số Toa Tàu & Số Ghế (Toa # - Ghế #) đã sửa đổi trong câu trả lời cho Người Dùng (KHÔNG chèn tên/số ghế vào nội dung tin nhắn Telegram Chatbot gửi cho nhân viên)!**
