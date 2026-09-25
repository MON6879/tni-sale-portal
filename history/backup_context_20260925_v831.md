# 🧠 BACKUP CONTEXT — 25/09/2026 (Phiên v831)
**Hệ thống**: TNI Operations & Sale Web Portals  
**Mục tiêu**: Thẩm định toàn diện bảo mật Web Portal sau khi public GitHub, khử trùng 100% PII và thiết lập RULE PM-57 bọc thép quy trình an ninh mạng.

---

## 1. Tóm Tắt Hiện Trạng & Rà Soát Bảo Mật
1. **GitHub Pages (`MON6879/tni-sale-portal`)**:
   - Được kích hoạt để giải quyết sự cố mạng tại Myanmar bị chặn domain `*.vercel.app` (ERR_CONNECTION_TIMED_OUT).
   - Đã nhúng hệ thống Cổng bảo vệ Mật khẩu (`#pwd-gate`) dùng thuật toán băm SHA-256 (`TNI@2026`), cơ chế tự động hết phiên sau 8 tiếng (480 phút) và cưỡng bức/nhắc nhở đổi mật khẩu định kỳ 30 ngày.
2. **Khử trùng dữ liệu cá nhân (Zero-PII Client Law)**:
   - Đã rà soát và khử trùng toàn bộ số điện thoại thật (`0965 1900...`, `0978...`, `0945...`) chuyển thành số hotline mẫu `0965 000 00X`.
   - Đã thay thế toàn bộ email cá nhân (`@gmail.com`) của nhân viên và admin (`phonghdpxd@gmail.com`, `htoolaynyaw@gmail.com`, `zinkoko@...`) thành email định danh công vụ `@tni.com`.
   - Đã ẩn danh hóa 100% tên nhân viên thật (`Zin Ko Ko`, `Min Min`, `Aung Thu`, `Kyaw Swar` ➔ `Staff Sales 01`, `Staff Tech 01`...).
   - Đã đồng bộ cổng mật khẩu vào cả 3 file: `sale.html`, `index.html`, và `executive_dashboard.html`.
3. **Phân tích Backend GAS (`sale_backend.gs`)**:
   - Máy chủ Google Apps Script đã có sẵn cơ chế xác thực Token (`saleAuth_`), giới hạn tốc độ (Rate Limit 60 req/phút).
   - Tự động cắt bỏ các cột tài chính/giá vốn (`stripFinanceCols_`) nếu người gọi không có quyền Admin/Finance.

---

## 2. Thiết Lập RULE PM-57 (Bảo Mật Web Public)
Đã đúc thành **RULE PM-57** và đồng bộ vào cả 4 file `AGENTS.md`:
- `d:\6. AI\1. QLTC\AGENTS.md`
- `d:\6. AI\1. QLTC\Task and WO\AGENTS.md`
- `d:\6. AI\1. QLTC\tni-search\AGENTS.md`
- `d:\6. AI\1. QLTC\tni-sitedown\AGENTS.md`

Nội dung cốt lõi của RULE PM-57:
1. **Khử trùng 100% PII client-side**: CẤM hardcode SĐT thật, email cá nhân, tên thật vào file HTML/JS/CSS.
2. **Cổng mật khẩu bắt buộc**: 100% file `.html` public phải tích hợp `#pwd-gate` SHA-256 + session 8h + nhắc đổi pass 30 ngày.
3. **Cô lập Secret ở Server**: Token, Service Account, PAT chỉ nằm trong Secrets/Properties; backend kiểm tra token trước khi trả dữ liệu.
4. **Quy trình 5 bước thẩm định bảo mật**: Bắt buộc chạy kiểm tra Regex PII, Secrets, Cổng khóa, Backend Auth, Đồng bộ trước khi release bất kỳ tính năng mới nào.

---

## 3. Git Commits & Đồng Bộ
- `Task and WO`: Commit `12e3fcf` (sanitize PII), Commit `9469619` (add RULE PM-57).
- `tni-search`: Commit `38cffcc` (sanitize & pwd-gate), Commit `f961ff1` (add RULE PM-57).
- `tni-sitedown`: Commit `2acb48f` (add RULE PM-57, bảo tồn Steel-Lock).
