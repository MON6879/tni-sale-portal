# BACKUP CONTEXT — 12/09/2026 (Phiên bản v799)
# THIẾT LẬP CƠ CHẾ TƯƠNG TÁC TỰ CHỦ KHÔNG MA SÁT: RULE PM-25 TRIỆT TIÊU CÂU HỎI YES/NO THỪA THÃI & CHUẨN XÁC HÓA PHẢN XẠ HÀNH ĐỘNG CỦA AI

---

## 1. BỐI CẢNH & YÊU CẦU NGƯỜI DÙNG
- **Yêu cầu Người Dùng**: 
  - *"Có cách nào giảm câu hỏi Yes No sau khi đưa vào rule không"*
  - *"Mời chuyên gia đọc systeam map và lịch sử để đưa ra phương án hỏi Yes no ít và hiệu quả nhất"*
  - *"đưa vào rule đi"*
- **Thực trạng**: AI các phiên trước thường xuyên dừng lại hỏi xin phép ("Anh có muốn làm không?", "Tôi bắt đầu nhé?", "Anh có đồng ý phương án này không?") làm gián đoạn dòng công việc của Người Dùng, đặc biệt khi Người Dùng có phong cách chỉ đạo rất ngắn gọn và quyết đoán (*"tiếp"*, *"1"*, *"sửa đi"*, gửi ảnh lỗi).

---

## 2. ĐIỀU TRA HỆ THỐNG & NGUYÊN NHÂN GỐC
1. **Nguồn gốc câu hỏi thừa**:
   - Rule `ASK-FIRST POLICY` cũ quy định: *"Thấy chưa rõ là phải hỏi ngay..."*. AI các phiên sau bị ám ảnh bởi 2 sự cố lịch sử (v599 xóa 13 file GAS, v786 hardcode migration) nên suy diễn quá đà thành phản xạ sợ sai, ngay cả với các tác vụ kỹ thuật chuẩn cũng dừng lại hỏi Yes/No cho an toàn.
   - Rule `AUTO-SAVE POLICY` lại yêu cầu AI tự động 100% không chờ nhắc. Hai quy tắc này gây xung đột nhận thức cho AI.
2. **Khảo sát System Map (1.408 dòng)**:
   - Toàn bộ các quy trình nghiệp vụ (6 Bước Lưu Đi, Single Train 5 phút, Chat ID centralization, Error Isolation `|| true`, Clasp deploy) đã được hệ thống hóa cực kỳ chi tiết, có runbook rõ ràng.
   - AI hoàn toàn đủ căn cứ kỹ thuật để **TỰ QUYẾT ĐỊNH 100%** mà không cần hỏi xin phép.

---

## 3. GIẢI PHÁP ĐÃ ĐÓNG BĂNG VÀO RULE PM-25
Thay thế toàn bộ `ASK-FIRST POLICY` mơ hồ cũ bằng **RULE PM-25: STRICT ESCALATION & ZERO-FRICTION AUTONOMY POLICY**:

### A. Tầng 1: TUYỆT ĐỐI CẤM HỎI — 100% TỰ ĐỘNG THỰC THI (Autonomous Exec)
- Toàn bộ 6 bước "Lưu Đi" (backup context, sync repos, commit, push, deploy, clear cache).
- Khảo sát mã nguồn, đọc dữ liệu thật từ Google Sheets / Telegram API / Web DOM.
- Sửa bug code, sửa lỗi cú pháp, bọc lỗi `try...except`, thêm `|| true` trong GitHub Actions.
- Đồng bộ logic giữa các repository theo System Map.
- **AI BẮT BUỘC TỰ ĐỘNG THỰC THI 100% TỪ ĐẦU ĐẾN CUỐI, CẤM HỎI XIN PHÉP!**

### B. Tầng 2: THỰC THI MẶC ĐỊNH & THÔNG BÁO SAU (Smart Default with Opt-Out)
- Khi có nhiều phương án kỹ thuật (chọn mốc giờ cron cho Toa mới, đặt tên biến, định tuyến background Serverless): AI TỰ ĐỘNG CHỌN phương án an toàn và tối ưu nhất theo `system_map.md` để làm luôn.
- Ghi rõ trong báo cáo: *"Đã xử lý theo phương án tối ưu A; nếu muốn đổi sang B xin báo lại."* Không dừng lại hỏi mở!

### C. Tầng 3: DUY NHẤT 3 KỊCH BẢN SINH TỬ ĐƯỢC PHÉP HỎI (The 3 Hard Stops)
AI CHỈ ĐƯỢC PHÉP dừng lại hỏi Người Dùng khi rơi vào đúng 3 tình huống:
1. Lệnh yêu cầu **XÓA file mã nguồn gốc** (`.gs`, `.yml`, `.py` — phòng ngừa sự cố v599).
2. Viết hàm Reorder/Migration thay đổi **CẤU TRÚC cột** của Google Sheet đang chứa dữ liệu sống (phòng ngừa sự cố v786).
3. Yêu cầu đụng vào **phân hệ Khóa Thép Site Down** khi chưa có mật khẩu `UNLOCK STEEL: Phucat@7979`.

### D. Chuẩn Mẫu Hỏi 1-Phím (One-Key Confirmation)
Khi thuộc 3 kịch bản trên, CẤM hỏi Yes/No dài dòng. BẮT BUỘC dùng form:
> ⚠️ **[CẢNH BÁO RỦI RO SINH TỬ]**: Thao tác này sẽ [Xóa file X / Đổi cấu trúc cột Sheet Y].
> - **Gõ `1`** (hoặc `ok`): Để tôi thực thi ngay.
> - **Gõ `0`**: Để hủy bỏ.

### E. Smart Fallback Cho Lệnh Ngắn Cộc Lốc
- Khi Người Dùng gửi các lệnh cực ngắn (*"tiếp"*, *"sửa đi"*, *"làm đi"*, *"1"*, hoặc chỉ gửi ảnh chụp màn hình lỗi / đoạn log sự cố):
- TUYỆT ĐỐI CẤM hỏi ngây ngô: *"Anh muốn sửa gì?"*.
- BẮT BUỘC tự phân tích OCR/log ➔ trích xuất lỗi/mã trạm/nhóm ➔ truy vết lịch sử bước trước ➔ tự sửa code dứt điểm ➔ tự động Lưu Đi ➔ báo cáo kết quả: **"ĐÃ LƯU ĐI ✅"**.

---

## 4. BẢNG PHÂN BỔ SỐ GHẾ HỆ THỐNG & TRẠNG THÁI TRIỂN KHAI
| Ghế Phân Hệ | File | Version / Trạng Thái | Mô Tả Thay Đổi |
| :--- | :--- | :--- | :--- |
| **CORE-RULES** | `AGENTS.md` (x3 repos) | **v799** ✅ | Đóng băng RULE PM-25: Triệt tiêu câu hỏi Yes/No thừa |
| **INTERACTION** | Toàn bộ các phiên AI | **v799** ✅ | Áp dụng Bản đồ 3 Tầng Ra Quyết Định (Decision Matrix) |
| **DOCS** | `history/backup_context_20260912_v799.md` | **v799** ✅ | Lưu vết bối cảnh nghiên cứu và ban hành quy tắc |
