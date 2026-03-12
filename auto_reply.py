import os
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from aiohttp import web
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from dotenv import load_dotenv

import google.generativeai as genai
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

load_dotenv()

# --- 1. MA'LUMOTLARNI .ENV DAN OLISH ---
api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_string = os.getenv("TELEGRAM_SESSION_STRING")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-flash-latest')
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
claude_client = AsyncAnthropic(api_key=CLAUDE_API_KEY)

client = TelegramClient(StringSession(session_string), api_id, api_hash)
oqilgan_xabarlar = {}

# BEGONALAR UCHUN XOTIRA (Qayta-qayta javob yozmaslik uchun)
javob_berilgan_begonalar = set()

@client.on(events.MessageRead(inbox=True))
async def read_handler(event):
    oqilgan_xabarlar[event.chat_id] = event.max_id

def parse_ids(env_var_name):
    env_val = os.getenv(env_var_name, "")
    return [int(x.strip()) for x in env_val.split(",") if x.strip().isdigit()]

DOSTLAR = parse_ids("DOSTLAR")
ISHXONA = parse_ids("ISHXONA")

# --- 2. AI ZAXIRA MANTIG'I (Faqat kontaktlar uchun) ---
async def get_ai_answer(text, sender_id):
    if sender_id in DOSTLAR:
        uslub = "Sen mening o'rnimda do'stim bilan yozishyapsan. Juda qisqa, hazilkash va erkin (senirab) javob ber. Hech qachon o'zingni AI deb tanitma."
    elif sender_id in ISHXONA:
        uslub = "Sen mening o'rnimda hamkasbim bilan yozishyapsan. Jiddiy, rasmiy va faqat ish yuzasidan qisqa javob ber. O'zingni AI deb tanitma."
    else:
        uslub = "Sen mening o'rnimda oddiy tanishim bilan yozishyapsan. Neytral, qisqa va aniq javob ber. O'zingni AI deb tanitma."

    prompt = f"""{uslub}
QAT'IY QOIDALAR:
1. Hech qachon "Salom, qanday yordam bera olaman?" kabi gaplarni yozma.
2. Xabar qaysi tilda bo'lsa, xuddi shu tilda javob ber.
3. Agar u shunchaki salomlashsa, faqat qisqa salom alik qil.
4. Agar savol bersa, to'g'ridan-to'g'ri qisqa javob ber.

Foydalanuvchi xabari: {text}"""

    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception:
        pass

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception:
        pass

    try:
        response = await claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception:
        return "Tarmoqda nosozlik."

# --- 3. TELEGRAM HODISALAR VA FILTRLAR ---
@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def handler(event):
    hozirgi_vaqt = datetime.now(ZoneInfo("Asia/Tashkent"))
    sender = await event.get_sender()
    sender_id = event.sender_id
    chat_id = event.chat_id
    xabar_id = event.id

    # 1. BOTLARNI TEKSHIRISH
    if sender.bot:
        print("🤖 Botdan xabar keldi. AI aralashmaydi.")
        return 
        
    # 2. BEGONALARNI TEKSHIRISH (Kontaktda yo'qlar)
    if not sender.contact:
        if sender_id not in javob_berilgan_begonalar:
            print(f"🚫 Kontaktda yo'q odamdan xabar (ID: {sender_id}). Odatiy avto-javob yuborilmoqda...")
            await event.reply("Assalomu alaykum! Men hozir biroz bandman. Iltimos, xabaringizni yozib qoldiring, bo'shashim bilan o'zim sizga aloqaga chiqaman. 🤝")
            javob_berilgan_begonalar.add(sender_id) # Odamni xotiraga qo'shamiz
        else:
            print(f"⏳ Begona odam (ID: {sender_id}) yana yozdi. Qayta avto-javob yuborilmadi (spam himoyasi).")
        return 

    # 3. VAQTNI TEKSHIRISH (Faqat kontaktlar uchun AI ish vaqti)
    if not (8 <= hozirgi_vaqt.hour < 20):
        print("🌙 Ish vaqti emas (08:00 - 20:00). Xabar e'tiborsiz qoldirildi.")
        return 

    # 4. ASOSIY AI JARAYONI (Kontaktlar uchun)
    print(f"\n📨 Yangi xabar keldi (Kontakt). ID: {sender_id}")
    await asyncio.sleep(12)

    if oqilgan_xabarlar.get(chat_id, 0) >= xabar_id:
        print("👁️ O'zingiz xabarni o'qidingiz! AI bezovta qilmaydi.")
        return

    try:
        history = await client.get_messages(chat_id, limit=1)
        if history and history[0].out:
            print("🛑 O'zingiz javob yozdingiz. AI to'xtadi.")
            return
    except Exception:
        pass

    print("🤖 AI javob yozmoqda...")
    javob = await get_ai_answer(event.text, sender_id)
    await event.reply(javob)
    print("✅ AI javob yubordi!")

# --- 4. RENDER UCHUN SOXTA WEB-SERVER VA ASOSIY FUNKSIYA ---
async def health_check(request):
    return web.Response(text="Bot muvaffaqiyatli ishlayapti!")

async def main():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Web-server {port}-portda ishga tushdi (Render uchun).")

    print("🚀 Telegram Userbot ishga tushmoqda...")
    await client.start()
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())