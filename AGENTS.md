# 💬 STRICT RULE: TEMPLATE PHẢN HỒI THU THẬP CHUẨN GỌN TỐI ĐA 2 DÒNG (MAX 2-LINE BOT ACKNOWLEDGMENT POLICY)

> ⚠️ **QUY TẮC BẮT BUỘC (2-LINE TEMPLATE STANDARD)**: MỌI TIN NHẮN PHẢN HỒI THU THẬP TỰ ĐỘNG CỦA BOT (INVENTORY, MDG, CABLE, ASSET, V.V.) BẮT BUỘC PHẢI NGẮN GỌN TỐI ĐA ĐÚNG 2 DÒNG, TUYỆT ĐỐI KHÔNG CHÈN TÊN/SỐ GHẾ, KHÔNG RƯỜM RÀ:
> - **Dòng 1**: [Icon] [Tên Tác Vụ] ✅ #[Mã REF] | 📍 [Mã Trạm / Tuyến] | 🗓️ [DD/MM/YYYY HH:MM]
> - **Dòng 2**: 📸 Reply photo to attach (hoặc hành động tiếp theo)

---

# 🎯 STRICT RULE: CHÍNH XÁC PHẠM VI — SỬA ĐÚNG NƠI ĐÚNG CHỖ, TUYỆT ĐỐI KHÔNG TIỆN TAY SỬA TẦM BẬY SANG CHỖ KHÁC (STRICT SCOPE ISOLATION & ZERO-SIDE-EFFECT POLICY)

> ⚠️ **QUY TẮC BẮT BUỘC TỐI THƯỢNG (SCOPE ISOLATION & ZERO-COLLATERAL-DAMAGE)**:
> 1. **Sửa Đúng Nơi Đúng Chỗ (Strict Targeted Execution)**: Khi Người Dùng yêu cầu sửa lỗi hay tính năng ở thành phần nào, BẮT BUỘC chỉ tìm đúng file, đúng hàm, đúng dòng liên quan trực tiếp đến thành phần đó để xử lý.
> 2. **Tuyệt Đối Không Tiện Tay Sửa Tầm Bậy (Zero Collateral Modification)**: CẤM TUYỆT ĐỐI việc tiện tay sửa, đổi tên, tái cấu trúc (refactor) hoặc can thiệp vào bất kỳ file, hàm, biến hay component nào khác ngoài phạm vi được yêu cầu!
> 3. **Nhìn Thấy Hết ID & Bản Đồ Trước Khi Sửa (Verify Exact ID First)**: BẮT BUỘC phải tra cứu đối chiếu đúng Script ID, Spreadsheet ID, Bot Token và Webhook URL trong system_map.md và AGENTS.md. TUYỆT ĐỐI KHÔNG ĐƯỢC đoán mò hay gán nhầm endpoint của dự án này sang dự án khác!
> 4. **Kiểm Tra Không Ảnh Hưởng Chéo (Zero Side-Effect Verification)**: Sau khi sửa, BẮT BUỘC phải chạy kiểm thử live output để chứng minh thành phần được sửa đã hoạt động chính xác 100% VÀ toàn bộ các thành phần khác trong hệ thống vẫn hoạt động nguyên vẹn, không phát sinh bất kỳ lỗi mới nào!

---

# 💎 STRICT RULE: LÀM TRIỆT ĐỂ 100% — KHÔNG BỎ CUỘC KHI GIÁN ĐOẠN, NHÌN THẤY HẾT DỮ LIỆU MỚI ĐƯA PHƯƠNG ÁN (100% PERSISTENT & EXHAUSTIVE EXECUTION POLICY)

> ⚠️ **QUY TẮC BẮT BUỘC TỐI THƯỢNG (ZERO-SHORTCUT & PERSISTENCE POLICY)**: 
> 1. **Làm Triệt Để 100% (Exhaustive Full Scope)**: Tuyệt đối KHÔNG làm tiện tay, không sửa nửa vời, không để lại bất kỳ dữ liệu tĩnh cũ, ngày tháng sai lệch hay layout lỗi trên bất kỳ component nào.
> 2. **Không Bỏ Cuộc Khi Gián Đoạn (Persistent Continuation)**: Khi gặp lỗi gián đoạn (timeout, disconnected, network error, browser cache, API error...), BẮT BUỘC phải tự động kiên trì tiếp tục thực hiện từng bước, retry liên tục cho đến khi hoàn tất trọn vẹn 100% mục tiêu, KHÔNG được dừng lại giữa chừng rồi báo cáo hoàn thành ảo!
> 3. **Nhìn Thấy Hết Dữ Liệu Thực Tế Mới Đưa Phương Án (Look at All Real Data First)**: Trước khi đề xuất phương án hoặc viết code, BẮT BUỘC phải dùng script/query quét và đọc trực tiếp 100% dữ liệu nguồn thực tế (Google Sheets, Live Web DOM, Telegram API, GAS), nhìn thấy toàn bộ các dòng, cột, modal, table rồi mới đưa ra giải pháp xử lý triệt để, KHÔNG được giả định hay đoán mò!
> 4. **Kiểm Tra Thực Tế & Đầy Đủ Bằng Chứng (Live Output Verification)**: Sau khi thực hiện, phải kiểm tra live (HTTP 200, grep so khớp, live log), chứng minh đã chạy thông suốt rồi mới bàn giao cho Người Dùng.

---

# ⚡ STRICT PRIORITY RULE: GAS DIRECT SENDING FIRST, GITHUB ACTIONS FALLBACK SECOND

> ⚠️ **QUY TẮC BẮT BUỘC**: MỌI BẢN TIN / THÔNG BÁO / BÁO CÁO CÓ THỂ GỬI ĐƯỢC BẰNG GOOGLE APPS SCRIPT (GAS) QUA `UrlFetchApp.fetch()` BẮT BUỘC PHẢI ƯU TIÊN GỬI TRỰC TIẾP TỪ GAS TRÊN GOOGLE CLOUD; CHỈ KHI GAS KHÔNG THỂ XỬ LÝ ĐƯỢC (TÁC VỤ CẦN TÀI KHOẢN NICK CÁ NHÂN USER ACCOUNT TELETHON SEED HOẶC THAO TÁC CÀO DỮ LIỆU ĐẶC THÙ) MỚI DÙNG GITHUB ACTIONS DỰ PHÒNG!

---

# 🛡️ STRICT RULE: KIẾN TRÚC 5 TRỤ CỘT BẤT KHẢ XÂM PHẠM (ZERO-FAILURE ARCHITECTURE)

> ⚠️ **QUY TẮC BẮT BUỘC (ZERO BUG POLICY)**: TUYỆT ĐỐI KHÔNG ĐƯỢC CÀI ĐẶT CODE CÓ KHẢ NĂNG GÂY NGHẼN, TỰ HỦY RUNNER HAY SẬP CHUỖI LIÊN HOÀN (DÙ CỐ Ý HAY VÔ TÌNH). MỌI COMPONENT BẮT BUỘC PHẢI TUÂN THỦ 5 TRỤ CỘT:
> 1. **Cửa Sổ Kháng Trễ Động (Sliding Window Timing)**: Runner khởi động sớm $\rightarrow$ Sleep đến :06:00/:36:00 MMT; Runner khởi động trễ do GitHub queue $\rightarrow$ Chạy ngay lập tức với 0s delay, TUYỆT ĐỐI KHÔNG HỦY BỎ!
> 2. **Quét Lịch Sử Duy Nhất 1 Lần (Single-Pass Scanning)**: Mỗi nhóm Telegram chỉ quét đúng 1 lần duy nhất (< 3s) và so khớp tiêu đề trong RAM, triệt tiêu 100% nguy cơ Timeout và Telegram FloodWait.
> 3. **Cô Lập Lỗi Độc Lập (Zero Cascading Failure)**: Mọi script độc lập phải được bọc cô lập lỗi (`python script.py || true`) để không bao giờ làm chết chùm các báo cáo khác.
> 4. **Khóa Độc Quyền Phiên Telethon (Concurrency Locking)**: Cài đặt `concurrency: group: ...` trên GitHub Actions để các tác vụ Telethon không bao giờ tranh chấp hay đè phiên.
> 5. **Kênh Kép Song Hành (GAS Direct First, GitHub Second)**: GAS Cloud đảm nhiệm phát tin chính; GitHub Actions đóng vai trò dự phòng và cào Telethon.

---

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
3. 💾 **Thực hiện đủ 8 bước Quy tắc "LƯU ĐI" bắt buộc**:
   - **Bước 1:** Cập nhật snapshot backup context vào `history/backup_context_...md`.
   - **Bước 2:** Đồng bộ mã nguồn Python/GS qua tất cả các repo cục bộ (`tni-bot` & `tni_site_down_repo`).
   - **Bước 3:** Commit & Push lên GitHub (`phonghdpxd-cmd/tni-bot` & `MON6879/tni-sitedown-relay`).
   - **Bước 4:** Dọn dẹp sạch sẽ tất cả cache `__pycache__`.
   - **Bước 5:** **Đồng bộ 100% tất cả logic liên quan (Full Logical Cross-Sync)** — Khi sửa Endpoint/URL/Cron Schedule/Tra cứu, phải đồng bộ tức thì tất cả các file code, workflow step condition, fallback variables và tài liệu docs liên quan.
   - **Bước 6:** **Cập nhật tài liệu hệ thống (Mandatory Docs Sync)** — Khi thêm/xóa/sửa Toa, Ghế, Endpoint, Cron Schedule hoặc cấu trúc hệ thống, BẮT BUỘC phải cập nhật đồng bộ `system_map.md`, `SYSTEM_DOC.md` và `AGENTS.md` (Bản đồ Webhook) cho khớp 100% với code thực tế. TUYỆT ĐỐI KHÔNG ĐƯỢC để tài liệu lệch so với code!
   - **Bước 7:** **Kiểm thử thực tế (Live Output Verification)** — Chạy test payload/script để xác nhận 0 lỗi phát sinh và phản hồi thực tế chính xác 100%.
   - **Bước 8:** **Báo cáo rõ Số Chuyến Tàu, Số Toa Tàu & Số Ghế (Chuyến Tàu Số # — Toa # — Ghế #) đã sửa đổi trong câu trả lời cho Người Dùng (KHÔNG chèn tên/số ghế vào nội dung tin nhắn Telegram Chatbot gửi cho nhân viên)!**
