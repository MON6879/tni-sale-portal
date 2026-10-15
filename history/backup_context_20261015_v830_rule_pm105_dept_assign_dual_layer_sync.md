# Backup Context v830 — Department Assign Dual-Layer Sync Engine & Ghế Giám Sát AUDITOR-DEPT-9.7 (Rule PM-105)
**Thời gian:** 15/10/2026  
**Phiên bản Hệ Thống:** `v830`  
**Ghế Thực Thi:** `DEPT-ASSIGN-SYNC` (Mở rộng `BI-WO-SYNC` - `sync_wo_detail.py`) & `AUDITOR-DEPT-9.7` (`system_auditor.py`) & `BI Portal` (`index.html`, `executive_dashboard.html`)  

---

## 1. Bối Cảnh & Root Cause (Sự Cố Tab Department Assign Bị Dữ Liệu Tĩnh Mồ Côi)
1. **Hiện tượng**: Tab `Department Assign` (`🏢 Department Assignment Overview (Phòng Dep Tasks)`) trên BI Portal (`executive_dashboard.html` và `index.html`) hiển thị 4 dòng dữ liệu tĩnh đã cũ (Admin repair CCTV, Asset Inventory Site, Technical, Transmission) được hardcode lúc dựng layout ban đầu.
2. **Root Cause**:
   - Tab `Department Assign` trước đây chưa được nối vào bất kỳ luồng cào tự động nào.
   - Script định kỳ `sync_wo_detail.py` (Ghế `BI-WO-SYNC`) chỉ cào tab `WO Detail` (GID `159298579`), `Sum all WO Team` (GID `1840482617`) và `BOD assign` (GID `1482565085`), bỏ sót hoàn toàn tab `Input task` (GID `1755404595`).
   - `system_auditor.py` (Ghế `AUDITOR-9.1`) chưa có connector và hàm kiểm toán cho tab `Input task`, khiến 355 đầu việc thực tế và 321 task quá hạn hoàn toàn bị bỏ quên ngoài hệ thống giám sát.

---

## 2. Giải Pháp Kỹ Thuật Triển Khai

1. **Nâng cấp Ghế `BI-WO-SYNC` (`sync_wo_detail.py`)**:
   - Thêm cào trực tiếp GID `1755404595` (`Input task`) qua Google GViz API.
   - Xây dựng hàm tiền kết xuất HTML `build_dept_assign_html(df_dept)` kết xuất chính xác 355 dòng dữ liệu đầu việc sống từ 6 phòng ban (CM: 21, Finance: 27, M&E: 166, Manager: 54, PM: 54, Transmission: 33) với đầy đủ mã màu trạng thái (Done: xanh ngọc, In Progress: vàng cam, Overdue: đỏ/hồng).
   - Tích hợp thanh lọc nhanh theo phòng ban (`Filter Dept: All, M&E, Manager, PM, Transmission, Finance, CM`).
   - Tự động thay thế nội dung panel `dept-assign-panel` trong các file HTML production trên cả 2 repository (`Task and WO`, `tni-search`).
   - Lưu trữ bản cache JSON tốc độ cao tại `Task and WO/api/dept_assign_cache.json` và `tni-search/api/dept_assign_cache.json`.
2. **Frontend Dual-Layer Live Sync (`index.html` & `executive_dashboard.html`)**:
   - Tích hợp hàm JavaScript `refreshDeptAssignLive()` kết nối trực tiếp `gviz/tq?tqx=out:csv&gid=1755404595` (Zero-CORS).
   - Tích hợp hàm `filterDeptTable(deptName, btn)` lọc động tức thời trên trình duyệt theo phòng ban.
   - Bổ sung nút bấm làm mới `Đồng bộ Dữ liệu Live` kèm hiệu ứng xoay icon font-awesome spinner.
   - Gắn sự kiện tự động kích hoạt Live Sync khi người dùng chuyển sang tab `Department Assign`.
3. **Triển Khai Ghế Giám Sát `AUDITOR-DEPT-9.7` (`system_auditor.py`)**:
   - Thêm `Sheet Input Task (GID=1755404595)` và `Sheet BOD Assign (GID=1482565085)` vào `SHEET_CONNECTORS`.
   - Xây dựng hàm kiểm toán nghiệp vụ `audit_input_task_semantic()`: kiểm tra kết nối, tính toàn vẹn các cột, thống kê tổng task theo phòng ban và phát hiện số lượng task quá hạn (`Target Date complete < today`).
   - Bổ sung Ghế `AUDITOR-DEPT-9.7 (Giám sát Tiến độ Phòng Dep)` vào danh sách báo cáo chính thức của Sentinel.
4. **Bảo Vệ Khóa Thép & Cô Lập Repository**:
   - Tuyệt đối không đụng vào `tni-sitedown` để tuân thủ 100% Strict Repo Isolation Rule và Site Down Steel Lock Rule.
5. **Đúc Rule PM-105 vào `AGENTS.md` & `system_map.md`**:
   - Quy chuẩn hóa cơ chế kép (Dual-Layer Sync) và Sentinel Sentry cho toàn bộ phân hệ Phòng Dep.

---

## 3. Danh Sách Files Thay Đổi

| File | Thay Đổi |
|------|----------|
| `sync_wo_detail.py` | Thêm cào GID 1755404595, hàm `build_dept_assign_html`, cập nhật `update_html_file` |
| `system_auditor.py` | Thêm connectors GID 1755404595 & GID 1482565085, hàm `audit_input_task_semantic`, Ghế AUDITOR-DEPT-9.7 |
| `Task and WO/index.html` | Cập nhật 355 dòng Dept Assign live, hàm `refreshDeptAssignLive()`, `filterDeptTable()` |
| `Task and WO/executive_dashboard.html` | Cập nhật 355 dòng Dept Assign live, hàm `refreshDeptAssignLive()`, `filterDeptTable()` |
| `tni-search/index.html` | Đồng bộ 100% bản live từ `Task and WO` |
| `tni-search/executive_dashboard.html` | Đồng bộ 100% bản live từ `Task and WO` |
| `Task and WO/api/dept_assign_cache.json` | Cache JSON 355 dòng Dept Assign |
| `tni-search/api/dept_assign_cache.json` | Cache JSON 355 dòng Dept Assign |
| `system_map.md` (root, `Task and WO`, `tni-search`) | Cập nhật mô tả Ghế `BI-WO-SYNC` và `Ghế AUDITOR-DEPT-9.7` |
| `AGENTS.md` (root, `Task and WO`, `tni-search`) | Đúc thêm RULE PM-105 |

---

## 4. Bằng Chứng Live Verification

- **Live Fetch Test**: Cào thành công GID `1755404595` trả về 355 dòng dữ liệu sống của 6 phòng ban (CM: 21, Finance: 27, M&E: 166, Manager: 54, PM: 54, Transmission: 33).
- **Semantic Audit Test**: `audit_input_task_semantic()` trả về PASS trong 1.33s, phát hiện 321 đầu việc quá hạn.
- **HTML Parity**: Toàn bộ 6 files HTML đã được thay thế thành công bảng live 355 dòng và tích hợp script tương tác.
- **Repo Isolation**: `tni-sitedown` hoàn toàn sạch, không bị sync chéo bất kỳ file HTML nào.
