# 🚂 BÁO CÁO BẢO VỆ HỆ THỐNG V872 (PM-99) — TÁCH RUNNER CÔNG KHAI & NGUỒN CODE BẢO MẬT
**Thời gian:** 2026-10-11 23:55 MMT
**Người thực hiện:** Antigravity AI
**Phiên:** Steel Lock kết thúc an toàn, khóa thép tự động đóng lại

## 1. MỤC TIÊU VÀ BỐI CẢNH
- Giải quyết triệt để rủi ro rò rỉ mã nguồn, cấu trúc dữ liệu và secrets lịch sử từ repo công khai MON6879/tni-sitedown-relay.
- Duy trì 100% khả năng chạy tự động định kỳ của đoàn tàu (Single Train Engine) tận dụng tài nguyên Actions miễn phí trên repo công khai mà không phải hy sinh tính bảo mật.

## 2. KẾT QUẢ TRIỂN KHAI CHI TIẾT
1. **Runner Công Khai Tối Giản (MON6879/tni-sitedown-relay)**:
   - Thay thế toàn bộ 507 files và 200+ commit lịch sử cũ bằng duy nhất 1 orphan commit: \25970c\.
   - Xóa bỏ branch \master\ cũ trên remote.
   - Hiện tại chỉ chứa 2 files: \.github/workflows/train_5min.yml\ và \README.md\.
   - Quét mã độc/secrets: 0 token, 0 API keys, 0 mã nguồn nội bộ.
2. **Kho Lưu Trữ Mã Nguồn Riêng Tư (MON6879/tni-bot - Private)**:
   - Bản sao hoàn chỉnh của \Task and WO\.
   - Kết nối với runner công khai qua Deploy Key chỉ-đọc (\CODE_DEPLOY_KEY\).
3. **Cấu Hình Secrets Hoàn Chỉnh (28 Secrets)**:
   - Rotate token bot Sale \@TNI_solution_bulding_bot\ (id: 8737134521) qua @BotFather, xác thực getMe HTTP 200.
   - Nạp \ADMIN_CHAT_ID: 6859790680\.
   - Toàn bộ 28 secrets phục vụ keepalive, các bot và webhook tokens đã được nạp đầy đủ trên repo runner.
4. **Phúc Tra Live**:
   - Workflow run \38158669680\ trên commit \25970c\ đã chạy và kết thúc với trạng thái: **completed success**.
   - Bước checkout code từ private repo qua deploy key thành công 100%.
   - Toa Sweep ETA thực thi thành công từ mã nguồn private.
5. **Cập Nhật System Map & Tài Liệu**:
   - Đã xóa sạch các token/hash/API_ID tĩnh trong \system_map.md\.
   - Đồng bộ 4 bản \AGENTS.md\ đạt chuẩn hash parity 100%.

## 3. KHÓA THÉP SITE DOWN
- Khóa thép đã đóng lại hoàn toàn. Hash SHA-256 xác thực: \1da0713d494c2a6dfab9fd37f4ca23373c8aa9c742e7238f725d5338b09a5235\.