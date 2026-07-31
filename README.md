# TNI Search Bot — Standalone Project

Vercel project riêng cho **Search Bot** (`@SEARCHTNITASKWOBOT`).  
Tách hoàn toàn khỏi `tni-bot` để deploy độc lập, không ảnh hưởng các service khác.

## Endpoints
- `GET/POST /api/search_bot` — Telegram webhook handler

## Environment Variables (cần set trong Vercel)
- `TELEGRAM_TOKEN` — Bot token của @SEARCHTNITASKWOBOT
- `APPS_SCRIPT_URL` — GAS URL (log search, daily submit)
- `DAILY_APPS_SCRIPT_URL` — GAS URL (daily report fields)

## Deploy
Push lên `main` → Vercel tự deploy (GitHub Integration).

## Webhook
```
https://api.telegram.org/bot{TOKEN}/setWebhook?url=https://tni-search.vercel.app/api/search_bot
```
