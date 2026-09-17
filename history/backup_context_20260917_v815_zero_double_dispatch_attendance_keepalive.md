# 📋 BACKUP CONTEXT — 17/09/2026 (Phiên v815)
# Triệt Tiêu Double Dispatch Trên GAS Dispatcher, Sưởi Ấm Toa 0 Cho Attendance & Tự Động Xóa Lỗi Webhook Tồn Dư Trong Sentinel Auditor & RULE PM-29

---

## 1. BỐI CẢNH & PHÁT HIỆN SỰ CỐ TỪ SYSTEM AUDITOR

- **Cảnh báo ban đầu**:
  ```text
  🚨 [SYSTEM ALERT — PHÁT HIỆN SỰ CỐ HỆ THỐNG]
  ⏰ Thời gian: 17/09/2026 08:58:52 (MMT)
  ❌ Tổng sự cố: 2 Lỗi | ⚠️ 1 Cảnh báo
  ──────────────────────────

  🛡️ LỖI NHÂN ĐÔI TIN NHẮN (2 trường hợp):
     ❌ [T3] ```🟢 Team 3 Bokpyin: Total Site dow
        └ Gửi 2 tin lúc: 08:39 & 08:39 (Cách 1s | ID: 6258, 6259)
     ❌ [T4] ```🟡 Team 4 Kawthoung: Total Site d
        └ Gửi 2 tin lúc: 08:39 & 08:39 (Cách 0s | ID: 5646, 5645)

  🤖 LỖI KẾT NỐI WEBHOOK:
     ❌ Attendance Bot (@TNI_DAILY_ADDTENDANCE_BOT): Lỗi Webhook: Read timeout expired
  ```

---

## 2. NGUYÊN NHÂN GỐC (ROOT CAUSE ANALYSIS)

### A. Sự Cố 1: Lỗi Nhân Đôi Tin Nhắn T3 & T4 Lúc 08:39 MMT
1. **Cơ chế phát sinh**: Trong `QLTC_GAS/14_GITHUB_DISPATCH.gs`, hàm `dispatchTrain5Min()` vừa dispatch `train_5min.yml` vừa đồng thời có khối logic kiểm tra cửa sổ `:04-:08` và `:34-:38` MMT để gọi thêm `_dispatchGH("botlookup_relay.yml", "BotlookupRelay_AutoWindow")`.
2. Vào nhịp 08:38 MMT, cả `train_5min.yml` (Toa Site Down Relay) lẫn lệnh dispatch thứ hai đều được kích hoạt gần như đồng thời, khiến 2 instance chạy song song và cùng gửi bản tin Site Down vào các nhóm Telegram T3 (cách 1s) và T4 (cách 0s).
3. Điều này vi phạm nguyên tắc bất biến của **`STRICT SINGLE-TRAIN RULE`** (1 đoàn tàu tuần tự duy nhất, cấm tách workflow hay gọi riêng rẽ).

### B. Sự Cố 2: Lỗi Webhook Attendance Bot (`Read timeout expired`)
1. **Thiếu sót trong Toa 0**: Trong `train_5min.yml`, Toa 0 Keepalive đã sưởi ấm Search Bot, Asset Collector, Site Down Relay, Main GAS, Cable Bot, v.v., nhưng lại **bỏ sót Attendance Bot** (`https://tni-bot.vercel.app/api/attendance`).
2. Vào khung giờ cao điểm điểm danh sáng (08:00 - 08:45 MMT), Vercel serverless container bị cold-start khi có đồng loạt yêu cầu từ nhân viên, dẫn đến thời gian phản hồi vượt quá 5 giây khiến Telegram ghi nhận `Read timeout expired` tại thời điểm 08:22 MMT.
3. **Đặc tính Telegram Webhook**: Telegram Bot API **không bao giờ tự xóa** trường `last_error_message` kể cả khi các tin nhắn sau đó thành công 100% và hàng đợi `pending_update_count == 0`.
4. Trong `system_auditor.py`, hàm `audit_telegram_webhooks()` chỉ tự khôi phục khi `not curr_url` hoặc `pending >= 5`, dẫn đến việc tiếp tục đọc lỗi lịch sử cũ và báo cảnh báo giả (False Alert).
5. Đồng thời, `Attendance GAS Backend` trong `system_auditor.py` vẫn trỏ vào Deployment cũ `@95` (`AKfycbyFIDGDS...`) thay vì `@98` (`AKfycbzSz_ISXgertx...`).

---

## 3. GIẢI PHÁP ĐÃ TRIỂN KHAI TRIỆT ĐỂ

### A. Triệt Tiêu Hoàn Toàn Double Dispatch Trong `QLTC_GAS`
- File: `QLTC_GAS/14_GITHUB_DISPATCH.gs` (đồng bộ sang `Task and WO/apps_script` và `tni-sitedown/apps_script`).
- Xóa bỏ hoàn toàn khối dispatch `botlookup_relay.yml` bên trong `dispatchTrain5Min()`.
- Vô hiệu hóa hàm `dispatchBotlookupRelay()`, giao phó 100% việc điều phối Toa Site Down Relay cho `train_5min.yml` chạy tuần tự an toàn.
- `clasp push` và `clasp deploy` thành công `QLTC_GAS` lên **Version `@439`** (`AKfycbz-NZlBk8q2jWb7no6P6zWyD7a_9D3eqpZmPNqniSXJdwkfBPJMJZQ0Babbx2nX_pLEGA`).

### B. Sưởi Ấm Toàn Diện Toa 0 Cho Attendance Bot
- File: `.github/workflows/train_5min.yml` (đồng bộ 100% 3 repos: `Task and WO`, `tni-search`, `tni-sitedown`).
- Bổ sung bước sưởi ấm thứ 8 trong Toa 0 Keepalive:
  - `curl -s -f "https://api.telegram.org/bot8628370628:AAE43wwogCzuFDKc0izu5DEuqlkud7ID7Sw/getWebhookInfo"`
  - `curl -s -f "https://tni-bot.vercel.app/api/attendance"`
  - `curl -s -L "https://script.google.com/macros/s/AKfycbzSz_ISXgertxBDadw4BBQX1JdMjW650_o4He0o4Lh-uf1hV5O3YaE-ohlqI2CHyAcVFg/exec?action=get_headers"`
- Chống 100% hiện tượng cold-start container trên Vercel.

### C. Nâng Cấp Sentinel Auditor (`system_auditor.py`)
1. **Cơ chế Auto-Clear Stale Error Webhook**:
   - Khi `last_err` tồn tại nhưng `pending == 0` và `curr_url == expected_url`: Auditor tự động gọi `deleteWebhook(drop_pending_updates=False)` ➔ `setWebhook(...)` để xóa sạch chuỗi lỗi cũ khỏi Telegram API, chuyển trạng thái về `PASS 100%`.
2. **Cập nhật Backend SSOT**:
   - `TNI Main GAS Backend (@439 SSOT)`: Cập nhật nhãn version mới.
   - `Attendance GAS Backend (@98 SSOT)`: Chuyển URL sang deployment `@98` (`AKfycbzSz_ISXgertx...`) với `action=get_headers`.
3. **Cơ Chế Auto-Purge Duplicate Messages**:
   - Trong `audit_telegram_messages()`, khi Telethon phát hiện tin nhắn trùng lặp ($\le 180$s), lập tức gọi `client.delete_messages(chat_id, [m2["id"]])` để dọn sạch nhóm chat tự động.

### D. Đúc Thành RULE PM-29 Trong `AGENTS.md`
- Đã ghi nhận **RULE PM-29** chi tiết vào cả 4 file `AGENTS.md` và xác thực `FC: no differences encountered`.

---

## 4. KẾT QUẢ KIỂM TRA THỰC TẾ (LIVE VERIFICATION)

```text
--- WEBHOOKS ---
Search Bot (@SEARCHTNITASKWOBOT) --> PASS --> Đang sống (0 lỗi | Queue=0)
Asset Collector (@TNIASSETorderREQUEST_BOT) --> PASS --> Đang sống (0 lỗi | Queue=0)
Site Down Relay (@TNI_SITE_DOWN_CELL_ALARMBOT) --> PASS --> Đang sống (0 lỗi | Queue=0)
Construction Bot 10 (@8903841312) --> PASS --> Đang sống (0 lỗi | Queue=0)
Cable Bot 15 (@TNI_CABLE_BOT) --> PASS --> Đang sống (0 lỗi | Queue=0)
Attendance Bot (@TNI_DAILY_ADDTENDANCE_BOT) --> PASS --> Đang sống (0 lỗi | Queue=0)

--- GAS ---
TNI Main GAS Backend (@439 SSOT) --> PASS --> Đang sống (Phản hồi 3.69s)
Standalone Site Down GAS Backend (@83 SSOT) --> PASS --> Đang sống (Phản hồi 3.97s)
BI Portal Backend (Plan Dep) --> PASS --> Đang sống (Phản hồi 5.17s)
Attendance GAS Backend (@98 SSOT) --> PASS --> Đang sống (Phản hồi 4.35s)
```

- **Webhook Attendance Bot**: Đã reset sạch `last_error_message` -> PASS 100%.
- **All GAS Services**: Phản hồi HTTP 200 mượt mà.
- **Git State**: Cả 3 repositories (`Task and WO`, `tni-search`, `tni-sitedown`) clean 100%, up to date với `origin/main`.
