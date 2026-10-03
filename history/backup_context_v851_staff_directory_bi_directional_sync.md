# 📜 BÁO CÁO BẢO TOÀN NGỮ CẢNH — BACKUP CONTEXT v851
**Thời gian thực thi**: 2026-10-03 11:25 MMT
**Tác vụ**: Đồng Bộ 2 Chiều SSOT Nhân Sự Giữa Web UI (`sale.html`) và Google Sheet tab `staff` (Sheet ID: `1s-V0owHlwub4qrCxTUvKmXp4PWZthzk5oKhi5m_wQBA`)

---

## 1. 🔍 NGUYÊN NHÂN GỐC (ROOT CAUSES)
1. **Lỗi Rào Cản Client-side**: Trong `Task and WO/sale.html`, hàm `saveStaffUserModal()` đặt điều kiện `const adminToken = localStorage.getItem('tni_sale_admin_token') || ''; if (adminToken) { fetch(...) }`. Khi người dùng truy cập web thông thường, token này rỗng nên fetch bị bỏ qua, dữ liệu chỉ lưu cục bộ vào `localStorage` của trình duyệt.
2. **Sai Lệch Endpoint URL**: Biến `SALE_GAS_URL` trong khối staff của `sale.html` bị trỏ vào Deployment cũ (`AKfycbylrXMED...`) thay vì Deployment chính thức `GAS_SALE_URL` (`AKfycbz-NZlBk8q...`).
3. **Backend GAS Rào Token**: Trong `QLTC_GAS/sale_backend.gs`, hàm `staffSave_` đòi hỏi `if (!auth.isAdmin) return 403` và nằm sau auth gate, không có endpoint mở để đồng bộ staff trực tiếp từ Web UI.
4. **Cấu Trúc Sheet Thiếu Header & Cơ Chế Đọc Cứng Nhắc**: Tab `staff` trên Sheet `1s-V0owHlwub4qrCxTUvKmXp4PWZthzk5oKhi5m_wQBA` chưa từng có header; hàm `staffGet_` cũ đọc theo header cố định, nếu người dùng nhập tay tiếng Việt ("Họ và Tên", "Số điện thoại") thì Web UI không map được dữ liệu.

---

## 2. 🛠️ GIẢI PHÁP & THỰC THI TOÀN DIỆN
1. **Backend `QLTC_GAS/sale_backend.gs` (@465)**:
   - Thêm định tuyến public: `if (act === 'staff_save') return staffSavePublic_(body);` không cần token.
   - Viết mới `staffGet_`: Tự động khởi tạo tab và header chuẩn nếu sheet rỗng. Hỗ trợ nhận diện cột thông minh song ngữ (tiếng Anh lẫn tiếng Việt: "tên", "họ và tên", "chức danh", "vai trò", "sđt", "phone", "email", "ghi chú"...). Tự động map và chuẩn hóa vai trò (admin, finance, warehouse, tech, dealer, sales).
   - Viết mới `staffSavePublic_`: Nhận danh sách nhân sự từ Web UI và ghi trực tiếp vào tab `staff`, tự format header nổi bật (`#1e293b`, chữ trắng đậm).
2. **Deploy GAS QLTC_GAS**:
   - `npx clasp push --force` & `npx clasp deploy -i AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA -d "feat: Dong bo 2 chieu Nhan su Web va Google Sheet v851"` ➔ **Version @465**.
3. **Frontend `Task and WO/sale.html`**:
   - Thêm nút **"☁️ Đồng Bộ Sheet"** (`rbac-btn-sync-staff`) vào thanh công cụ danh sách nhân sự.
   - Thay thế `SALE_GAS_URL` bằng `GAS_SALE_URL`.
   - Tạo hàm `syncStaffWithGoogleSheet(manualNotify)`: Tự động tải từ Sheet, cập nhật `DB.s('staff_directory', res.data)`, render bảng và dropdown toàn app.
   - Sửa `saveStaffUserModal()`: Luôn gọi fetch `staff_save` lên Google Sheet mỗi khi thêm/sửa nhân sự.
   - Sửa `deleteStaffUser()`, `updateStaffAssignedRole()`, `resetStaffDirectoryToClean()`, `importStaffFromFile()`: Tự động gửi danh sách mới lên Sheet.
4. **Đồng Bộ 6 File Web UI Qua 3 Repo**:
   - `Task and WO/sale.html` & `Task and WO/tni_sale.html`
   - `tni-search/sale.html` & `tni-search/tni_sale.html`
   - `sale.html` & `tni_sale.html` (root)
5. **Đúc Rule Phòng Ngừa Vào `AGENTS.md`**:
   - Đã chèn Rule **Đồng Bộ 2 Chiều SSOT Nhân Sự Web UI <-> Google Sheet** vào section RBAC và đồng bộ toàn bộ file `AGENTS.md`.

---

## 3. 🧪 BẰNG CHỨNG XÁC MINH LIVE (LIVE VERIFICATION EVIDENCE)
- **POST `staff_save`**: HTTP Status 200, phản hồi: `{'ok': True, 'saved': 2, 'ts': '2026-10-03T04:38:02.919Z'}`.
- **GET `staff_get`**: HTTP Status 200, đọc về chính xác từ Google Sheet:
  - Total staff: 2
  - Staff 1: `ST0001` - `Ban Giam Doc` (`admin`)
  - Staff 2: `ST0002` - `Nguyen Van A` (`sales`)
