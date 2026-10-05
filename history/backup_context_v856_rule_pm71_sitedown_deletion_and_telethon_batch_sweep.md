# Backup Context v856: Bọc Thép Phân Hệ Site Down & Cơ Chế Quét Dọn Tin Mồ Côi Theo Batch-Window (Rule PM-71)
**Thời gian**: 05/10/2026 ~17:40 Myanmar Time (MMT)  
**Tác vụ**: Giải quyết triệt để lỗi không xóa tin nhắn cũ Site Down Alarm trong nhóm Telegram (`TNI TEAM 1 PLAN - ALARM`, `T2`, `T3`, `T4`).  
**Mật khẩu mở khóa thép**: `UNLOCK STEEL: Phucat@7979`  

---

## 1. Nguyên Nhân Gốc (Root Cause Forensic)
1. **Rogue GAS Trigger Collision**:
   - Trên Google Apps Script (`apps_script_sitedown`, Script ID `1fgIR_frjlOHBt4o3STTjGmHYaKfuiSb3zAtp7IrO__uLSIuRQGJ2Oc6X`), có một time-driven trigger `checkAndSend_1min` đang chạy ngầm mỗi 1 phút trên cloud mà không nằm trong Single Train.
   - Khi webhook `botlookup_relay.py` gọi `doPost` (`store_site_down`), `doPost` xóa khóa `TS_KEY_A1` và ngủ 5 giây chờ Google Sheets đồng bộ công thức. Trong 5 giây đó, `checkAndSend_1min` kích hoạt song song và thấy `TS_KEY_A1` rỗng nên lập tức gửi Tin 1 (`ID 11812, 11813` lúc 10:09:25).
   - 2 giây sau, `doPost` thức dậy và tiếp tục gửi Tin 1 (`ID 11814, 11815` lúc 10:09:27), đè mất `SD_MSGID_TIN1_T1` trong PropertiesService.
   - Hậu quả: Hai đợt tin trùng lặp phát cách nhau 2 giây, và đợt tin đầu tiên bị bỏ rơi thành tin mồ côi vĩnh viễn trong nhóm.

2. **Unconditional Key Wipe on Failure in GAS**:
   - Trong `site_down_v2.gs`, hàm `deleteOldMessages_` đặt lệnh xóa `PropertiesService.deleteProperty("SD_MSGID_" + msgKey)` trong khối `finally`.
   - Nếu Telegram Bot API gặp lỗi rate limit 429, nghẽn mạng hoặc socket timeout khi gọi `deleteTelegramMsgBot_`, ID tin cũ vẫn bị xóa sạch khỏi ScriptProperties.
   - Khi ID bị xóa khỏi ScriptProperties, GAS không còn lưu ID đó nữa, dẫn đến tin nhắn đó không bao giờ được xóa bởi Bot API trong các chu kỳ tiếp theo.

3. **Broken Fallback Payload in GAS**:
   - Trong `sendTelegramPreCollectIds_`, khi gửi định dạng `<pre>` bị lỗi, nhánh fallback gọi UrlFetchApp với toàn bộ biến `plainContent` thô thay vì `chunk` con hiện tại, làm tràn giới hạn 4096 ký tự của Telegram khi danh sách trạm dài.

4. **Telethon Sweep Blindness & Chunk Truncation**:
   - Script `sweep_orphan_eta.py` (chạy tài khoản Telethon có quyền `revoke=True` xóa mọi tin) không kiểm tra bot ID chính thức `8647102342`, bỏ sót tên bot khi có dấu chấm (`5. TNI`) hoặc khoảng trắng.
   - Quan trọng nhất: Logic cũ giả định sai lầm rằng Site Down chỉ phát 1 tin đơn lẻ (`newest_sd = site_down_ids[0]; orphan_sd = site_down_ids[1:]`). Đối với Team 1 có nhiều trạm chia thành 2 phần (Part 1 Header và Part 2 T1 S1), logic cũ nếu chạy sẽ xóa mất Part 1 (`ID 11820`) và chỉ giữ lại Part 2 (`ID 11821`), làm mất nửa thông tin cảnh báo!

5. **Cross-Repo Pollution**:
   - File `sale_summary_report.py` vô tình tồn tại trong repo `MON6879/tni-sitedown-relay`, vi phạm Strict Repo Isolation Rule.

---

## 2. Các Thay Đổi Đã Thực Hiện
1. **Google Apps Script (`apps_script_sitedown/site_down_v2.gs`)**:
   - **Xóa vĩnh viễn Trigger ngầm**: Hàm `teardownGasTrain1min()` và `admin_audit_sitedown` đã dọn sạch trigger `checkAndSend_1min`. Hiện tại `remaining_triggers: []`.
   - **Harden `deleteOldMessages_`**: Chỉ xóa ID khỏi `PropertiesService` khi API trả về thành công (hoặc tin không tồn tại / >48h). Nếu xóa thất bại, giữ lại ID trong mảng lưu trữ để retry.
   - **Merge ID trong `sendOrEditTelegramPre` & `sendOrEditTelegram`**: Khi lưu ID mới, tự động merge với các ID cũ chưa xóa được (`Set([...unremoved, ...newIds])`).
   - **Fix Fallback Chunk**: Nhánh fallback đổi từ `text: plainContent` sang `text: chunk`.
   - **Deploy GAS**: Đã deploy thành công version `@107` cho Deployment ID `AKfycbyCibIj4QN7oG5BZc_ju1iS-DUmd9nNdrMn9UN-WD8qf6jVoU_OKOf2yfbi10qGMFF-`.

2. **Telethon Sweep Engine (`sweep_orphan_eta.py`)**:
   - Nhận diện Bot 5T qua 3 tầng: `sender_id == 8647102342` (ID gốc bất biến), username (`tni_site_down_cell_alarmbot`), tiêu đề (`BOT_5T_NAMES`) và nội dung (`Total Site down`, `Dont Forget`, `HUB site TNI`, `SUMMARY — Team`). Loại trừ tuyệt đối ID cá nhân Admin (`6859790680`).
   - Gom cụm theo **Batch Window 120 giây**: Toàn bộ tin Site Down phát trong vòng 120s kể từ tin mới nhất được bảo toàn trọn vẹn (cả Part 1, Part 2 và Tin 2). Chỉ các tin cũ hơn 120s mới bị coi là tin mồ côi và bị xóa sạch (`revoke=True`).
   - Tự động khử trùng lặp (dedup) nếu có hai chunk giống hệt nhau trong cùng một batch window.
   - Tăng giới hạn quét từ 100 lên 150 tin nhắn để quét sạch toàn bộ lịch sử backlog.
   - Đã chạy live và xóa sạch tổng cộng **257 tin nhắn cũ mồ côi** trên toàn bộ 4 nhóm (T1: 122 tin, T2: 39 tin, T3: 48 tin, T4: 48 tin), trả lại sự sạch sẽ 100% cho các nhóm vận hành.

3. **Dọn dẹp Repo Isolation**:
   - Đã xóa `sale_summary_report.py` khỏi repo `tni-sitedown`.
   - Đã đồng bộ `site_down_v2.gs` và `sweep_orphan_eta.py` trên cả 3 repository.

4. **Attendance GAS**:
   - Đã deploy bản sửa lỗi chuỗi message ID `[object Object]` cho `apps_script_attendance` (`AKfycbzSz_ISXgertxBDadw4BBQX1JdMjW650_o4He0o4Lh-uf1hV5O3YaE-ohlqI2CHyAcVFg @125`).

5. **Quy Tắc Phòng Ngừa**:
   - Đã đúc kết và ghi **Rule PM-71** vào `AGENTS.md` và đồng bộ trên cả 4 file `AGENTS.md`.

---

## 3. Phúc Tra Live
- **GAS Live Probe**: `admin_audit_sitedown` trả về `{"ok":true, "deleted_legacy_triggers":["checkAndSend_1min"], "remaining_triggers":[]}`.
- **Telethon Live Sweep**: Lần 1 xóa 240 tin, Lần 2 xóa vét 17 tin sâu hơn. Cả 4 nhóm hiện chỉ còn duy nhất 1 đợt tin Site Down mới nhất (T1 giữ nguyên vẹn 2 tin Part 1 & Part 2: ID 11820 & ID 11821).
- **Parity Check**: So sánh `Compare-Object` giữa các repo đạt 0 diff.
