# BACKUP CONTEXT: 2026-10-11 (v869) — PM-97 P1: XOAY 9 TOKEN BOT, BỎ HARDCODE, WEBHOOK secret_token

(Không chứa giá trị secret nào.)

## Đã làm
| Hạng mục | Kết quả |
|---|---|
| Token mới | 9/9 `getMe`=200, đúng bot, không trùng token đã lộ; token cũ 10/10 = 401 |
| Vercel env (`tni-bot`) | 10 biến OK; build `tni-hhuxo0aob` Ready |
| Handler Vercel | 6 file bỏ hardcode + kiểm `X-Telegram-Bot-Api-Secret-Token` fail-closed (POST giả = 403) |
| Webhook | Search, Cable, Asset, Refuel, Attendance, Report Send, Construction = đặt lại kèm secret_token, pending=0 |
| GAS Attendance | `@142` Primary / `@143` Secondary — token trong ScriptProperties, xóa `refresh_token` |
| GAS QLTC_GAS Hub | `@492` — 8 file hết literal, `SD_BOT_TOKEN` + `SEND_BOT_TOKEN` được tự động đổi |
| GAS Clear Site | `@54` — `BOT_TOKEN` trong ScriptProperties |
| Python/yaml | 8 script + `render.yaml` + mirror `apps_script/` hết literal; `system_auditor.py` không re-hook khi thiếu secret |
| Leak-check | 18 secret mới × 5 thư mục = 0 hit |

## Chưa xong (cần Người Dùng / UNLOCK STEEL)
1. GitHub Secrets repo train (SEND_BOT_TOKEN, REPORT_TASK_BOT_TOKEN, CABLE_BOT_TOKEN, REFUEL_BOT_TOKEN, SEARCH_BOT_TOKEN, COLLECTOR_BOT_TOKEN, SITEDOWN_BOT_TOKEN, CONSTRUCTION_BOT_TOKEN, ATTENDANCE_BOT_TOKEN, WH_*).
2. Telethon session mới (`TELEGRAM_SESSION`).
3. Xóa 3 GitHub PAT lộ; mật khẩu Khóa Thép mới.
4. Site Down (steel): `site_down_v2.gs`, `botlookup_relay.py`, `api/site_down_relay.py`, webhook `@TNI_SITE_DOWN_CELL_ALARMBOT`.
5. P2: repo runner public tối thiểu; khóa chia sẻ proxy→GAS; allowlist chat_id; `/setjoingroups` Disable.
