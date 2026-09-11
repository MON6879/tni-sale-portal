# BACKUP CONTEXT: GỘP SITE DOWN VÀO ĐOÀN TÀU THỜI GIAN TUẦN TỰ DUY NHẤT & KHÓA RULE THÉP
**Thời gian**: 12/09/2026 06:00 MMT
**Phiên**: v793
**Tác giả**: Antigravity & Người Dùng

---

## 1. YÊU CẦU NGƯỜI DÙNG
1. Khóa Telegram mới đã tạo thành công và cập nhật vào GitHub Secrets TELEGRAM_SESSION.
2. Gộp Site Down quay trở về làm 1 Toa trong Đoàn Tàu Thời Gian 5-Min Train (	rain_5min.yml) chạy TUẦN TỰ duy nhất trên 1 máy ảo.
3. Đưa vào Rule thép trong AGENTS.md: TUYỆT ĐỐI KHÔNG ĐƯỢC tự ý tách ra workflow / cron khác.

---

## 2. NGUYÊN NHÂN GỐC (ROOT CAUSE)
- Trước đó, Site Down bị tách thành workflow riêng otlookup_relay.yml với cron riêng 3,33 * * * *.
- Cùng lúc đó, 	rain_5min.yml chạy cron 1/5 * * * * (nhịp :06, :36).
- Lúc 20:08 MMT ngày 11/09/2026, 2 máy ảo runner GitHub Actions độc lập cùng lúc kết nối MTProto tới Telegram với cùng 1 TELEGRAM_SESSION từ 2 IP khác nhau.
- Telegram phát hiện xung đột IP đồng thời ➔ tự động khóa và thu hồi Auth Key (AuthKeyDuplicatedError).

---

## 3. GIẢI PHÁP BỌC THÉP ĐÃ THỰC THI
1. **Đoàn Tàu Tuần Tự Duy Nhất**:
   - Thêm Toa 🚨 Toa Site Down — Site Down Relay (:06 / :36 MMT) vào 	rain_5min.yml.
   - Tại nhịp :06 và :36 MMT, Toa Site Down chạy python botlookup_relay.py.
   - Mọi toa chạy tuần tự trước sau trên CÙNG 1 RUNNER (cùng máy ảo, cùng 1 IP), không bao giờ có 2 kết nối song song.
   - Vĩnh viễn triệt tiêu nguy cơ AuthKeyDuplicatedError mà chỉ cần 1 tài khoản Telegram duy nhất.

2. **Vô Hiệu Hóa Workflow Độc Lập**:
   - Tắt hoàn toàn schedule: cron trong otlookup_relay.yml ở tất cả repositories.
   - Disable workflow otlookup_relay.yml trên GitHub Actions qua API.
   - Disable workflow 	rain_5min.yml trùng lặp trên MON6879/TNI-DONE để chỉ duy nhất 1 đầu tàu chạy trên MON6879/tni-sitedown-relay.

3. **Ban Hành Rule Thép**:
   - Thêm STRICT SINGLE-TRAIN RULE: 1 ĐOÀN TÀU THỜI GIAN TUẦN TỰ DUY NHẤT — TUYỆT ĐỐI CẤM TỰ Ý TÁCH WORKFLOW / TÁCH CRON RIÊNG vào AGENTS.md.
   - Đồng bộ 100% sang cả 5 file AGENTS.md trong hệ sinh thái.

4. **Bảo Mật Session**:
   - Cập nhật .gitignore loại bỏ 
ew_telegram_session.txt, *.session*, generate_session.py, CHAY_TAO_KEY_TELEGRAM.bat.
