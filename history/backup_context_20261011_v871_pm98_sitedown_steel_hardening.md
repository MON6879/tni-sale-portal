# Backup v871 — PM-98 Site Down hardening (Steel session 2026-10-11)
- Steel mở bằng mật khẩu mới (SHA-256 `1da0713d494c2a6dfab9fd37f4ca23373c8aa9c742e7238f725d5338b09a5235`), đã đóng lại.
- GAS Site Down @113 sạch; Vercel tni-sitedown redeploy tối giản (endpoint cũ 404); webhook Site Down có secret_token.
- Properties: SD_BOT_TOKEN/GITHUB_PAT thay mới; SD_RELAY_KEY, SD_ADMIN_KEY thêm.
- Gán nhầm secret SEND/REPORT_TASK đã sửa theo .env. TECHDEP report bot (@TNITECHINICALDEPREPORT_BOT) cần /revoke (lộ trong lịch sử public).
- Mở: TDEPREPORT token mới, setjoingroups, P2 tách repo public.
