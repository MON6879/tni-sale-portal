# Snapshot Context v824: Triển Khai Ghế Đồng Bộ Dữ Liệu Sống BOD Assign & WO Detail (Ghế BI-WO-SYNC & Client Live Fetch Engine - RULE PM-54)

- **Mục tiêu**: Khắc phục dứt điểm tình trạng tab "BOD Assign" trên TNI Operations BI Portal (`index.html` & `executive_dashboard.html`) bị hardcode dữ liệu tĩnh cũ từ tháng 06/2026 (481 dòng lỗi thời). Bổ sung cơ chế đồng bộ kép (Client-Side Live Fetch qua Google Sheet `gviz/tq` + Backend Batch Sync qua Ghế BI-WO-SYNC `sync_wo_detail.py`).
- **Nguyên nhân gốc (Root Cause)**:
  1. Tab `BOD Assign` được sinh tĩnh một lần bằng script scratch vào ngày 22/06/2026 mà không hề có hàm Live Fetch CSV tự động tải khi chuyển tab trên trình duyệt.
  2. Ghế `BI-WO-SYNC` (`sync_wo_detail.py`) trước đó chỉ xử lý 7 bảng của tab `Progress Team Task and WO+Oil` (GID 159298579) mà bỏ quên tab `BOD assign` (GID 1482565085).
- **Giải pháp bọc thép đã thực hiện**:
  1. **Tầng Client-Side Live Fetch**: Bổ sung hàm `window.refreshBodAssignLive()` kết nối trực tiếp endpoint Zero-CORS `gviz/tq?tqx=out:csv&gid=1482565085`, tự động tải và hiển thị 83 dòng nhiệm vụ sống khi người dùng mở tab "BOD Assign", kèm nút bấm làm tươi thủ công với spinner loading trên thanh tiêu đề.
  2. **Tầng Backend Pre-rendered Batch**: Nâng cấp `sync_wo_detail.py` (Ghế BI-WO-SYNC) tải đồng thời cả WO Detail và 83 dòng nhiệm vụ BOD Assign, tiêm trực tiếp vào toàn bộ 8 file HTML trên cả 3 repository, và xuất file cache `api/bod_assign_cache.json`.
  3. **Đúc Rule Phòng Ngừa**: Bổ sung **RULE PM-54** vào cả 4 file `AGENTS.md`. Cập nhật `system_map.md`.

---

## Danh Mục Ghế & Trạng Thái Hệ Thống

| Ghế | Vai trò | Trạng thái |
|---|---|---|
| `BI-WO-SYNC` | Toa WO Detail & BOD Assign Sync (`sync_wo_detail.py`) | ACTIVE ✅ (83 dòng BOD + 7 bảng WO) |
| `GAS-BI-5` | Backend BI Portal (`bi_backend.gs`) | STANDBY ✅ |
| `AUDITOR-9.1` | Giám sát chất lượng dữ liệu sống | ACTIVE ✅ |
