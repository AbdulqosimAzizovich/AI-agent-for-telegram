import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()
api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")

print("Telegramga ulanilmoqda...")
with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\n✅ BU SIZNING MATNLI SESSIYANGIZ (Hech kimga ko'rsatmang!):\n")
    print(client.session.save())
    print("\nShu uzun kodni nusxalab oling!")