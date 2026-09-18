# 📜 BẢN LƯU NGỮ CẢNH HỆ THỐNG — VIRTUAL SECRETARY FIX & SPEAKER 2-CLICK TOGGLE (RULE PM-44)
⏰ **Thời gian thực hiện:** 18/09/2026 19:45:00 (MMT)
🏷️ **Phiên bản:** v819 / RULE PM-44
🎯 **Nhiệm vụ:**
1. Thêm chức năng bấm lần 2 thì nút loa tắt (Speaker Button 2-Click Toggle & Pulse Visual Feedback).
2. Sửa dứt điểm lỗi hỏi trợ lý không trả lời (Fix Assistant Not Answering Root Causes).

---

## 🔍 ROOT CAUSE ANALYSIS & DETAILED FIXES

### 1. Tại sao hỏi trợ lý không trả lời (Assistant Not Answering):
- **Nguyên nhân gốc 1 (Fatal DOM ReferenceError):** Trong hàm `appendBotMessage(htmlContent, senderSeat)` tại dòng 8573, code khai báo `const botHtml = ...;` nhưng lại gọi `container.insertAdjacentHTML('beforeend', html);` (gọi biến `html` không tồn tại trong scope) ➔ Trình duyệt ném `ReferenceError: html is not defined` ngay lập tức!
- **Nguyên nhân gốc 2 (Uncaught Silent Drop):** Trong `handleQuery`, hàm `this.dispatchAndAnswer(query)` được gọi trong `setTimeout` mà không bọc `try...catch`. Khi gặp `ReferenceError` trên, exception làm sập callstack trong im lặng, typing spinner bị xóa và không có bất kỳ tin nhắn phản hồi nào được hiển thị cho người dùng.
- **Nguyên nhân gốc 3 (Thiếu biến toàn cục `allEngineers`):** Trong `loadStats`, mảng 28 kỹ sư được parse vào biến cục bộ `var allEngineers = [];` nhưng không được gán lên `window.allEngineers` ➔ `WOAgent.getEngineers()` luôn trả về `[]`.
- **Nguyên nhân gốc 4 (Thiếu Null-Guards):** Biểu thức `${this.escapeHtml(e.team_code.replace('MYT_TNI_',''))}` ném `TypeError` nếu `team_code` bị undefined.
- **Nguyên nhân gốc 5 (Xử lý đa ý định cho câu hỏi người dùng):** Câu hỏi *"kiểm tra cho tôi các nhân viên nào không nên không đóng gỗ để và các nhiệm vụ T4"* kết hợp cả 2 ý định: Xem nhiệm vụ/tiến độ Team 4 Kawthoung VÀ danh sách kỹ sư tồn đọng/chưa đóng WO toàn mạng. Đã bổ sung bộ định tuyến đa ý định (Composite Intent Router) trả lời trọn vẹn cả 2 phần.

### 2. Bấm lần 2 tắt loa (Speaker Button Toggle):
- Đã bổ sung cơ chế kiểm tra `window.speechSynthesis.speaking` hoặc `this.isSpeaking`.
- Bấm lần 1: Kích hoạt giọng đọc Web Speech API (`SpeechSynthesisUtterance`), đổi nhãn nút sang `⏹️ Dừng Đọc`, đổi màu đỏ `#EF4444` và gán class `.speaking-pulse`.
- Bấm lần 2: Gọi `stopSpeaking()` -> `window.speechSynthesis.cancel()`, gỡ bỏ class `.speaking-pulse`, hoàn nguyên nhãn nút về `🔊 Đọc Báo Cáo`.
- Tự động hoàn nguyên khi đọc xong (`utter.onend`) hoặc gặp lỗi (`utter.onerror`).
- Đồng bộ dừng chéo giữa loa thanh điều hướng trên cùng (`toggleAIVoice`) và loa của Trợ lý ảo (`ChiefSecretaryAgent`).

---

## 📂 DANH SÁCH FILE THAY ĐỔI
1. `index.html` (root)
2. `executive_dashboard.html` (root)
3. `Task and WO/index.html`
4. `Task and WO/executive_dashboard.html`
5. `tni-search/index.html`
6. `tni-search/executive_dashboard.html`
7. `AGENTS.md` (root, `Task and WO/AGENTS.md`, `tni-search/AGENTS.md`) - Bổ sung RULE PM-44
