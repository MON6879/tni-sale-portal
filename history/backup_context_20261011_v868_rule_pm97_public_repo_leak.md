# BACKUP CONTEXT: 2026-10-11 (v868) — PM-97: RÒ RỈ TOÀN KHO PUBLIC & ĐÍNH CHÍNH PM-96

(File này cố ý KHÔNG chứa giá trị secret nào — chỉ tên/đuôi che.)

## 1. Bằng chứng quét live (chỉ đọc)
- `MON6879/tni-sitedown-relay`: PUBLIC, 507 file ở HEAD (bản sao gần toàn bộ workspace).
- 12 loại secret trong HEAD public: 8 token bot còn sống (getMe=200), GitHub PAT (4 file), Telethon StringSession (2 file), mật khẩu Khóa Thép (6 file), api_hash, số điện thoại, Google API key.
- Token Attendance MỚI (đuôi `Z5U`) bị chính commit PM-96 `935b203` đẩy lên public (system_auditor.py) → coi như cháy.
- 13/14 handler `api/*.py` không kiểm `X-Telegram-Bot-Api-Secret-Token`; GAS Attendance không có allowlist chat/sender.
- `tni-sale-portal` public: 4 file HTML, không thấy secret. `Task and WO`, `tni-search`, `MON6879/tni-bot`: private (404 ẩn danh).
- `train_5min.yml` public: 0 token plaintext, không có `schedule:` (train được dispatch từ ngoài).

## 2. Đính chính
Câu "BỌC THÉP 100%" ở phiên PM-96 là SAI: chỉ làm sạch 1 workflow, chưa quét toàn repo public + lịch sử.

## 3. Việc Người Dùng phải làm (P0)
1. Telegram → Settings → Devices → Terminate all other sessions (Telethon session lộ).
2. BotFather Revoke: Clear Site, Refuel, Search, Construction, Asset Collector, Report Send, Site Down Relay, Cable, Attendance(mới).
3. GitHub → xóa 3 PAT lộ (đuôi `…mAi`, `…gQX`, `…03j`).
4. Đổi mật khẩu Khóa Thép; hạn chế Google API key; xoay Vercel env.

## 4. Việc AI (P1–P3) — xem Rule PM-97 trong AGENTS.md
P1 nạp secret mới + bỏ hardcode + secret_token/allowlist (cần token mới + UNLOCK STEEL cho site_down_v2.gs/botlookup_relay.py);
P2 repo runner public tối thiểu + repo code private; P3 pre-push hook + nâng cấp ghế 9.4/9.6.

## 5. Trạng thái repo
PM-97 đã commit vào `Task and WO` + `tni-search` (private) + root. KHÔNG đẩy vào repo public `tni-sitedown` (ngoại lệ parity theo R1).
