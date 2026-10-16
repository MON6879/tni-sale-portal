# ============================================================
# TẠO TELEGRAM SESSION MỚI (StringSession)
# ============================================================
import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

# Tự động đọc API_ID và API_HASH từ file .env
load_dotenv('Task and WO/.env')
load_dotenv('.env')

API_ID = int(os.environ.get('TELEGRAM_API_ID', 0))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')

print('=' * 60)
print('🔑 TOOL TẠO TELEGRAM SESSION MỚI CHO SITE DOWN & BÁO CÁO')
print('=' * 60)
print(f'API_ID  : {API_ID}')
print(f'API_HASH: {API_HASH[:4]}...{API_HASH[-4:]}')
print('-' * 60)

async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start()
    
    session_str = client.session.save()
    me = await client.get_me()
    
    print('\n' + '=' * 60)
    print(f'✅ ĐĂNG NHẬP THÀNH CÔNG: {me.first_name} (@{me.username}) | Phone: {me.phone}')
    print('=' * 60)
    print('\n👇 CHUỖI TELEGRAM_SESSION MỚI CỦA ANH:\n')
    print(session_str)
    print('\n' + '=' * 60)
    
    # Lưu ra file để anh dễ copy
    with open('new_telegram_session.txt', 'w', encoding='utf-8') as f:
        f.write(session_str.strip())
    print('📁 Đã lưu khóa vào file: new_telegram_session.txt')
    print('👉 Anh chỉ cần mở file new_telegram_session.txt, copy toàn bộ chuỗi')
    print('👉 Sau đó vào GitHub repo MON6879/tni-sitedown-relay -> Settings -> Secrets')
    print('👉 Cập nhật lại secret TELEGRAM_SESSION!')
    print('=' * 60)
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
