# BACKUP CONTEXT — 12/09/2026 (Phiên bản v796)
# CHUẨN HÓA MẪU TIN PHẢN HỒI THU THẬP & ĐỊNH TUYẾN EMOJI BỌC THÉP CHO PHÂN HỆ M&E (INVENTORY / MDG / CHANGE OIL)

---

## 1. BỐI CẢNH & YÊU CẦU NGƯỜI DÙNG
- **Yêu cầu Người dùng**: Cập nhật mẫu tin phản hồi tự động khi thu thập tin nhắn trong nhóm `«6. M&E - TNI Run MDG + Invetory Fuel»` (`-1002341257404`):
  ```text
  ⛽ REF:00009 | TNI0246_1 | 09/09/2026 07:57
  ✅ Reply Confirm to close | sent photo MDG after sent text report
  ```
- **Xác nhận từ Người dùng qua hội đàm**:
  - Dòng 2 dùng chính xác cú pháp: `✅ Reply Confirm to close | sent photo MDG after sent text report`.
  - Áp dụng đồng bộ cho cả 3 phân hệ báo cáo trong nhóm:
    1. **Inventory Fuel (⛽)**
    2. **MDG Run Report (⚡)**
    3. **Change Oil MDG (🛢️)**

---

## 2. PHÂN TÍCH FORENSIC & NGUYÊN NHÂN GỐC (ROOT CAUSE FORENSICS)
- **Cơ chế hoạt động**:
  - Bot Collector (`@TNIASSETorderREQUEST_BOT`) nhận webhook tại endpoint `https://tni-bot.vercel.app/api/collector` (quản lý bởi repo `phonghdpxd-cmd/tni-bot` / `Task and WO`).
  - Khi nhân viên gửi tin báo cáo (Change Oil, Inventory Fuel, MDG Run), bot ghi nhận vào Google Sheet qua Apps Script và gửi phản hồi xác nhận 2 dòng có mã `REF:XXXXX`.
  - Khi nhân viên gửi ảnh (`msg.photo`) hoặc gõ `Confirm` bằng cách reply tin nhắn của bot, bot phân tích `reply_to_message.text` để xác định loại tác vụ: `inv_add_photo` / `mdg_add_photo` / `oil_add_photo` hoặc `inv_confirm` / `mdg_confirm` / `oil_confirm`.
- **Rủi ro kỹ thuật nghiêm trọng phát hiện trong code cũ**:
  - Code cũ kiểm tra từ khóa trong `reply_to_message.text.upper()`:
    ```python
    if "INVENTORY" in rt_upper: action_name = "inv_add_photo"
    elif "MDG" in rt_upper: action_name = "mdg_add_photo"
    ```
  - Khi mẫu mới rút gọn dòng 1 thành `⛽ REF:00009 | TNI0246_1 | 09/09/2026 07:57` (không còn chữ "INVENTORY"), và dòng 2 chứa cụm `sent photo MDG after sent text report` (có chữ "MDG"):
  - Nếu kiểm tra theo từ khóa cũ, cả 3 phân hệ đều chứa chữ "MDG" ở dòng 2, dẫn đến việc người dùng reply ảnh hoặc gõ `Confirm` cho Inventory hay Change Oil đều bị nhận nhầm thành MDG Run Report (`mdg_add_photo`, `mdg_confirm`)!

---

## 3. GIẢI PHÁP ĐÃ THỰC THI (IMPLEMENTATION)

### A. Chuẩn Hóa Mẫu Tin Phản Hồi 2 Dòng Cho Cả 3 Phân Hệ (`api/collector.py`)
1. **Change Oil MDG (🛢️)**:
   - Dòng 1: `🛢️ <b>REF:{ref}</b> | {site_show} | {now.strftime('%d/%m/%Y %H:%M')}`
   - Dòng 2: `✅ Reply <code>Confirm</code> to close | sent photo MDG after sent text report`
2. **Inventory Fuel (⛽)**:
   - Dòng 1: `⛽ <b>REF:{ref}</b> | {dg_show} | {now.strftime('%d/%m/%Y %H:%M')}`
   - Dòng 2: `✅ Reply <code>Confirm</code> to close | sent photo MDG after sent text report`
3. **MDG Run Report (⚡)**:
   - Dòng 1: `⚡ <b>REF:{ref}</b> | {site_show} | {now.strftime('%d/%m/%Y %H:%M')}`
   - Dòng 2: `✅ Reply <code>Confirm</code> to close | sent photo MDG after sent text report`

### B. Nâng Cấp Bộ Định Tuyến Bọc Thép Bằng Icon (Emoji-First Action Routing)
- Khi nhận ảnh reply:
  ```python
  if "⛽" in rt_text or "INVENTORY" in rt_upper:
      action_name = "inv_add_photo"
  elif "🛢️" in rt_text or "CHANGE OIL" in rt_upper or "OIL" in rt_upper:
      action_name = "oil_add_photo"
  elif "⚡" in rt_text or "MDG" in rt_upper:
      action_name = "mdg_add_photo"
  ```
- Khi nhận lệnh `Confirm` reply:
  ```python
  ref_m = re.search(r"REF[:\s#]*(\d+)", reply_text, re.IGNORECASE)
  if ref_m:
      ref_id = ref_m.group(1)
      action_name = "mdg_confirm"
      if "⛽" in reply_text or "INVENTORY" in reply_text.upper():
          action_name = "inv_confirm"
      elif "🛢️" in reply_text or "CHANGE OIL" in reply_text.upper() or "OIL" in reply_text.upper():
          action_name = "oil_confirm"
      elif "⚡" in reply_text or "MDG" in reply_text.upper():
          action_name = "mdg_confirm"
  ```

### C. Đồng Bộ & Đúc Rule Vào `AGENTS.md`
- Đã đồng bộ `api/collector.py` trên cả 2 repository:
  - `Task and WO` (`phonghdpxd-cmd/tni-bot` -> Vercel Production)
  - `tni-search` (`MON6879/TNI-DONE`)
- Đã cập nhật Rule đúc kết vào cả 4 file `AGENTS.md`:
  - `AGENTS.md` (root)
  - `Task and WO/AGENTS.md`
  - `tni-search/AGENTS.md`
  - `tni-sitedown/AGENTS.md`

---

## 4. BẢNG PHÂN HỆ & TRẠNG THÁI TRIỂN KHAI
| Ghế Phân Hệ | File | Version / Trạng thái | Mô Tả Thay Đổi |
| :--- | :--- | :--- | :--- |
| **COLLECTOR-BOT** (Vercel) | `Task and WO/api/collector.py` | v4.3 ✅ | Chuẩn hóa mẫu reply 2 dòng & định tuyến emoji `⛽`, `🛢️`, `⚡` |
| **SEARCH-HUB** | `tni-search/api/collector.py` | v4.3 ✅ | Đồng bộ mẫu reply 2 dòng & định tuyến emoji |
| **RULE ENGINE** | `AGENTS.md` (x4 repos) | v796 ✅ | Cập nhật Rule 2-line template & Emoji-First Action Routing |
