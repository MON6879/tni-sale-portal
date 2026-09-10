# BACKUP CONTEXT: CHUẨN HÓA REPORT 5A, REPORT 5B & ZERO TRACEBACK IN TELEGRAM
- **Thời gian**: 10/09/2026 07:10 (MMT)
- **Phiên bản**: Bot 3D v4.5 | Report 5 Pipeline v2.0
- **Phân hệ**: Report 5 (Daily Plan & Results), Webhook API (`search_bot.py`), Train Cron Pipeline (`train_5min.yml`)

## 1. Yêu Cầu Người Dùng
1. Chuẩn hóa tiêu đề và bố cục Report 5:
   - Report 5A: `📋 5A. Plan daily ({date_str}) — {team_name}`
     Bố cục chuẩn Hình 3: Header -> Plans for {date} -> Plan Content -> Submission History (3Day/7Day/Month) -> 3-Day Completion Rate -> Plan tomorrow.
   - Report 5B: `📋 5B. Plan today compare Result ({date_str}) — {team_name}`
     Bố cục chuẩn Hình 2: Header -> Stats -> Plan vs Actual -> FT Plan & Actual Summary -> Plan Tomorrow.
2. Quy tắc phân luồng gửi tin:
   - Gửi đồng nhất giữa 4 nhóm Team (T1, T2, T3, T4).
   - KHÔNG gửi Report 5B vào nhóm CONTROL vì quá dài.
   - Nhóm CONTROL CHỈ nhận DUY NHẤT 1 tin Report 5A Summary ngắn gọn cả 4 Team xem hôm nay Team nào đã nộp, Team nào chưa nộp.
3. Khắc phục lỗi Bot 3D ở Hình 5:
   - Xóa bỏ hoàn toàn việc gửi Python traceback `tb` ra nhóm chat trong `api/search_bot.py` khi có lỗi xử lý webhook (`do_POST`).

## 2. Thay Đổi Kỹ Thuật
1. `Task and WO/daily_plan_report.py` & `tni-search/daily_plan_report.py`:
   - Lọc chặt chẽ `GROUPS = {k: v for k, v in TELEGRAM_GROUPS.items() if k in ("T1", "T2", "T3", "T4")}` để không gửi nhầm sang REFUEL hay MDG.
   - `run_morning()`: Chuyển toàn bộ tiêu đề sang `📋 5A. Plan daily`, cập nhật khối `Plan Tomorrow ({tomorrow_str})`, dọn sạch tin cũ bằng `tg_delete_by_title("📋 5A. Plan daily")` và `tg_delete_by_title("📋 5.1 Report")`.
   - Báo cáo CONTROL trong 5A: Rút gọn chỉ báo danh sách 4 Team đã nộp hay chưa nộp, thống kê nộp và tỷ lệ hoàn thành 3 ngày, TUYỆT ĐỐI KHÔNG dump raw content.
   - `run_eod_or_update()`: Chuyển toàn bộ tiêu đề sang `📋 5B. Plan today compare Result ({date_str}) — {team_name}`.
   - Chặn gửi 5B sang CONTROL; chỉ xóa tin 5B/5. Report cũ trong CONTROL nếu có.
   - Bổ sung `5a. plan`, `5b. plan` vào danh sách blacklist từ khóa bot output trong `is_daily_plan_msg()` và `clean_plan_content()`.
2. `Task and WO/api/search_bot.py` & `tni-search/api/search_bot.py`:
   - Gỡ bỏ dòng `tg_send(chat_id, f"⚠️ <b>Error:</b>\n<pre>{html.escape(tb[:2000])}</pre>")` trong `do_POST`. Thay bằng ghi log kỹ thuật `logger.error(f"handle() traceback:\n{tb}")`.
   - Bump `BOT_VERSION = "v4.5"`.
   - Bổ sung blacklist `5a. plan daily`, `5b. plan today` trong `is_daily_plan()`.
3. `Task and WO/.github/workflows/train_5min.yml`:
   - Cập nhật tên các bước:
     + Toa 3: `Report 5B — Plan compare Result (EOD)` (`--mode eod`)
     + Toa 4: `Report 5B — Plan compare Result (Update)` (`--mode update`)
     + Toa 5: `Report 5A — Plan Daily (Morning/Evening)` (`--mode morning`)
   - Thêm các tùy chọn tương ứng vào `workflow_dispatch` đảm bảo tương thích ngược 100%.
4. Đúc kết RULE PM-18 và tiêm vào toàn bộ 4 file `AGENTS.md`.

## 3. Kết Quả Kiểm Thử Dry-Run
- Đã chạy `test_dry_run_generate.py` với 100% dữ liệu sống từ Google Sheet SSOT (185 plans, GID 853981745, GID 133591305):
  + [5A] Tạo thành công 4 tin 5A cho 4 nhóm Team (T1, T2, T3, T4) + 1 tin 5A Summary cho CONTROL.
  + [5B] Tạo thành công 4 tin 5B cho 4 nhóm Team (T1, T2, T3, T4). ZERO tin gửi tới CONTROL.
