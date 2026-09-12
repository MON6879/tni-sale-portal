# Backup Context: Hỗ Trợ Thu Thập 2 Loại Template 1 Cho Bot 15 TNI CABLE

**Ngày thực hiện:** 12/09/2026  
**Người yêu cầu:** User  
**Mục tiêu:**
1. Hỗ trợ 2 loại Template 1 cho Bot 15 TNI CABLE (`@TNI_CABLE_BOT`):
   - **Loại 1 (Truyền thống)**: `Team 1 today()...` (chứa `today`, `route broken`, `splicer`...).
   - **Loại 2 (Mới từ Link Down Report)**: Tin nhắn tiến độ sự cố đường truyền cáp đang đứt:
     `Progress: 12/09/26 07:38 <=> 🟢 T3 - IP : TNI0341SRT001-TNI0507SRT001`
     `🔗 link down - 07/09/26 13:10 => 11/09/2026 18:24:34 Ground condition not yet good`
2. Tự động nhận diện Team Name (`T1..T4`, `T1s1..T4s1`, `Team 1..4`) và gán chấm màu chuẩn Site Down (`🟠T1`, `🔵T2`, `🟢T3`, `🟡T4`).
3. Tự động tạo dòng mới tại Hàng 2 tab `Detail cable` với mã REF ID mới.
4. Với Loại 2: Ghi ngay toàn bộ nội dung tiến độ sự cố vào Cột J (`Route Broken`).
5. Bot phản hồi xác nhận 2 dòng chuẩn gọn:
   - Dòng 1: `🔌 REF:XXXXX | [TeamTag] | DD/MM/YYYY HH:MM`
   - Dòng 2: `📷 Reply photos to attach | ✅ Reply Done to close`
6. Lưu `MSG_REF_CACHE` để khi người dùng gửi ảnh / reply ảnh vào tin nhắn này, Bot sẽ tự động xác định đúng dòng để lưu ảnh vào Cột I (`Photos`).

---

## 1. Các Thành Phần Cập Nhật

### A. Vercel Webhook (`Task and WO/api/cable_bot.py`)
- Bổ sung `TEAM_EMOJIS` và hàm `extract_team_info()`.
- Bổ sung bộ lọc chặn tin tự động của chính Bot 15 (`text.startswith("🔌") and "LINK DOWN REPORT"`).
- Nâng cấp nhận diện Step 1: `is_type1` và `is_type2`.
- Gửi payload với `template_type: "type_2_link_down"` và `route_broken: text`.
- Nâng cấp `resolve_ref_from_msg()` hỗ trợ trích xuất Team Name và Incident Name từ tin nhắn Loại 2 khi reply ảnh / Done.

### B. Google Apps Script (`QLTC_GAS/apps_script_cable.gs`)
- Hàm `extractTeam_()`: Hỗ trợ cả `Team \d+` và `T[1-4]` (`T1..T4`, `T1s1..T4s1`).
- Hàm `cableAddTemplate()`: Hỗ trợ ghi nhận nội dung vào Cột J (`Route Broken`) cho Loại 2.
- Clasp push 18 files và clasp deploy:
  - Script ID: `1rvgWwrAMDbqtmqwOfqzguXB7m9snA5UZeOs9iGu64VJbejlNAkH2m6uR`
  - Deployment ID: `AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA`
  - Version: `@430`

---

## 2. Kiểm Tra & Đồng Bộ
- Syntax `cable_bot.py`: Pass (`py_compile` 0 errors).
- Đồng bộ code sang `Task and WO`, `tni-sitedown`, `QLTC_GAS`.
