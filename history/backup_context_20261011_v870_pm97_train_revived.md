# Backup v870 — PM-97 Tàu hồi sinh (2026-10-11 20:40 MMT)
- GitHub Secrets repo runner: token bot mới (SEND=SiteDown, REPORT_TASK=Report, CABLE, REFUEL, COLLECTOR=Asset) + TELEGRAM_SESSION mới (authorized).
- PAT điều phối cũ đã bị GitHub thu hồi (401) → tàu dừng 13:13Z. PAT mới fine-grained 90 ngày, 1 repo, Actions RW. Thay vào QLTC_GAS bằng hook nonce, deploy sạch @494. Run tự động 14:08Z success.
- Hook tạm đã gỡ; 0 dấu vết __patOnce_ trong QLTC_GAS; nonce file đã xóa.
- Còn mở: xóa PAT cũ sót, TECHNICAL_DEP bot, setjoingroups, Steel password mới + sửa Site Down, tách repo public (P2), Vercel GH_PAT_TOKEN (repo phonghdpxd-cmd).
- Nhắc: đổi PAT trước 2027-01-09.
