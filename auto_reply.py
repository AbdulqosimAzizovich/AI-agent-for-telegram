import os
import asyncio
import re
import random
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

# --- 1. MA'LUMOTLAR ---
api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_string = os.getenv("TELEGRAM_SESSION_STRING")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# LOG KANAL ID'sini olish (Agar .env da yo'q bo'lsa, me'ga jo'natadi)
log_env = os.getenv("LOG_CHAT_ID", "me")
try:
    LOG_CHAT_ID = int(log_env)
except ValueError:
    LOG_CHAT_ID = 'me'

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-flash-latest')
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
claude_client = AsyncAnthropic(api_key=CLAUDE_API_KEY)

client = TelegramClient(StringSession(session_string), api_id, api_hash)

oqilgan_xabarlar = {}
javob_berilgan_begonalar = set()
javob_berilgan_boshliqlar = set()
bloklangan_chatlar = set() 
suhbat_xotirasi = {}
bot_is_active = True

@client.on(events.MessageRead(inbox=True))
async def read_handler(event):
    oqilgan_xabarlar[event.chat_id] = event.max_id

def parse_ids(env_var_name):
    env_val = os.getenv(env_var_name, "")
    return [int(x.strip()) for x in env_val.split(",") if x.strip().isdigit()]

YAQIN_DOSTLAR = parse_ids("YAQIN_DOSTLAR")
DOSTLAR = parse_ids("DOSTLAR")
ISHXONA = parse_ids("ISHXONA")
BOSHLIQLAR = parse_ids("BOSHLIQLAR")

# --- 2. AI ZAXIRA MANTIG'I ---
async def get_ai_answer(yangi_xabar, sender_id, reply_matni):
    if sender_id in YAQIN_DOSTLAR:
        uslub = "Sen mening o'rnimda eng yaqin do'stim bilan yozishyapsan. Juda qisqa, erkin, doimiy ravishda SENSIRAB (sen deb) va hazilkash ohangda javob ber. Hech qachon o'zingni AI deb tanitma."
    elif sender_id in DOSTLAR:
        uslub = "Sen mening o'rnimda do'stim bilan yozishyapsan. Odatda unga SIZ deb hurmat bilan, lekin ochiq va do'stona murojaat qil. AMMO, agar suhbatda juda kuchli hazil yoki kulgi ketayotgan bo'lsa va 'siz'lash hazilning ta'mini buzadigan bo'lsa, o'sha vaziyatda SENSIRASHGA (sen deb yozishga) o'tgin. Hazil yumshaganda yana 'siz'lashga qayt. Qisqa va tabiiy yoz. O'zingni AI deb tanitma."
    elif sender_id in ISHXONA:
        uslub = "Sen mening o'rnimda hamkasbim bilan yozishyapsan. Jiddiy, rasmiy va faqat ish yuzasidan qisqa javob ber. SIZ deb murojaat qil. O'zingni AI deb tanitma."
    else:
        uslub = "Sen mening o'rnimda oddiy tanishim bilan yozishyapsan. Neytral, qisqa va aniq javob ber. O'zingni AI deb tanitma."

    tarix_matni = ""
    if sender_id in suhbat_xotirasi:
        for xabar in suhbat_xotirasi[sender_id]:
            tarix_matni += f"{xabar['kim']}: {xabar['matn']}\n"

    prompt = f"""{uslub}

QAT'IY QOIDALAR:
1. "Salom, qanday yordam bera olaman?" kabi gaplarni umuman yozma.
2. Xabar qaysi tilda bo'lsa, xuddi shu tilda javob ber.
3. Agar u shunchaki salomlashsa, faqat qisqa salom alik qil.
4. MOLIYA: Agar maktubda raqamlar, pullar, narx yoki qandaydir miqdor haqida gap ketsa, hech qachon "Ha" deb rozi bo'lma va tasdiqlama.

[Oxirgi xabarlar tarixi]:
{tarix_matni}
{reply_matni}

Foydalanuvchining YANGI xabari: {yangi_xabar}"""

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

# --- 3. TELEGRAM HODISALAR ---
@client.on(events.NewMessage(func=lambda e: e.is_private))
async def handler(event):
    global bot_is_active
    chat_id = event.chat_id
    xabar_id = event.id
    sender = await event.get_sender()
    sender_id = event.sender_id
    
    chat_info = await event.get_chat()
    ism = getattr(chat_info, 'first_name', '') or ''
    familiya = getattr(chat_info, 'last_name', '') or ''
    toya_ism = f"{ism} {familiya}".strip() or "Noma'lum foydalanuvchi"

    # --- KOMANDALAR VA BOSHQARUV ---
    if event.out:
        matn = event.text.lower().strip()
        
        if matn == '.uxla':
            bot_is_active = False
            await event.delete()
            await client.send_message(LOG_CHAT_ID, "💤 **Bot uxlash rejimiga o'tdi.** Barcha chatlarda AI to'xtatildi.")
            return
        elif matn == '.uygon':
            bot_is_active = True
            await event.delete()
            await client.send_message(LOG_CHAT_ID, "🚀 **Bot uyg'ondi!** Tizim yana faol.")
            return
        elif matn == '.ai_on':
            if chat_id in bloklangan_chatlar:
                bloklangan_chatlar.remove(chat_id)
            await event.delete()
            await client.send_message(LOG_CHAT_ID, f"🟢 **AI YOQILDI:** {toya_ism} (ID: {chat_id}) bilan suhbatda AI ishlashga ruxsat oldi.")
            return
        elif matn == '.ai_off':
            bloklangan_chatlar.add(chat_id)
            await event.delete()
            await client.send_message(LOG_CHAT_ID, f"🔴 **AI O'CHIRILDI:** {toya_ism} (ID: {chat_id}) bilan suhbat AI uchun majburiy bloklandi.")
            return
        # Diqqat: Oddiy javob yozganingizda endi avtomatik blokdan chiqib ketmaydi!
        return

    if not bot_is_active or chat_id in bloklangan_chatlar:
        return

    if getattr(event.message, 'media', None):
        return

    if getattr(sender, 'bot', False):
        return 

    if sender_id in BOSHLIQLAR:
        if sender_id not in javob_berilgan_boshliqlar:
            await event.reply("Assalomu alaykum. Xabaringizni qabul qildim. Hozir biroz ish jarayonida edim, tez orada o'zim siz bilan bog'lanaman. Hurmat bilan!")
            javob_berilgan_boshliqlar.add(sender_id)
            await client.send_message(LOG_CHAT_ID, f"👔 **Rahbariyat:** {toya_ism} (ID: {sender_id}) ga muloyim avto-javob yuborildi.")
        return

    if not getattr(sender, 'contact', False):
        if sender_id not in javob_berilgan_begonalar:
            await event.reply("Assalomu alaykum. Xabaringizni ko'rdim. Bo'shashim bilan o'zim aloqaga chiqaman.")
            javob_berilgan_begonalar.add(sender_id)
            await client.send_message(LOG_CHAT_ID, f"👤 **Begona:** {toya_ism} (ID: {sender_id}) ga standart avto-javob yuborildi.")
        return

    # --- MOLIYAVIY XAVFSIZLIK ---
    moliyaviy_sozlar = ["pul", "qarz", "dollar", "so'm", "som", "kredit", "plastik", "karta", "payme", "click", "narx", "summa", "hisob", "avans", "oylik", "ming"]
    xabar_matni = event.text.lower()
    is_finance = any(soz in xabar_matni for soz in moliyaviy_sozlar) or bool(re.search(r'\d+\s*k\b', xabar_matni))

    if is_finance:
        await asyncio.sleep(20)
        
        if oqilgan_xabarlar.get(chat_id, 0) >= xabar_id:
            return
            
        try:
            history = await client.get_messages(chat_id, limit=1)
            if history and history[0].out:
                return
        except Exception:
            pass
            
        blok_javoblari = [
            "🤖 [Avto-javob]: Assalomu alaykum. Men u kishining virtual yordamchisiman (shu paytgacha men bilan yozishganingiz uchun xabarlaringiz 'o'qilmagan' ko'rinishida turibdi). Moliyaviy va hisob-kitob masalalarini faqat o'zlari hal qiladilar. Shuni ma'lum qilamanki, men hozir blok rejimiga o'tdim va keyingi xabarlaringizga javob bera olmayman. Barcha ma'lumotlarni yozib oldim, bo'shashlari bilan o'zlari sizga aloqaga chiqadilar. 🤝",
            "🤖 [Avto-javob]: Assalomu alaykum. Siz u kishining shaxsiy sun'iy intellekt yordamchisi bilan suhbatlashyapsiz (xabarlaringiz o'qilmagan bo'lib turishining sababi ham shu). Moliyaviy masalalarga aralashish huquqim yo'q. Dastur qoidasiga ko'ra, ushbu chatda ishlashni to'xtatdim va boshqa savollarga javob qaytarmayman. Xabaringiz o'zlariga yetkazildi, tez orada o'zlari bog'lanadilar. 🤝"
        ]
        
        tanlangan_javob = random.choice(blok_javoblari)
        await event.reply(tanlangan_javob)
        bloklangan_chatlar.add(chat_id)
        
        await client.send_message(LOG_CHAT_ID, f"🚫 **MOLIYAVIY BLOK:** {toya_ism} (ID: {sender_id}) pul haqida yozdi. Chat bloklandi. Blokni yechish uchun suhbat ichida `.ai_on` deb yozing.")
        return

    # --- ODDIY AI SUHBAT ---
    hozirgi_vaqt = datetime.now(ZoneInfo("Asia/Tashkent"))
    if not (8 <= hozirgi_vaqt.hour < 20):
        return 

    await asyncio.sleep(12)
    if oqilgan_xabarlar.get(chat_id, 0) >= xabar_id: return

    try:
        history = await client.get_messages(chat_id, limit=1)
        if history and history[0].out: return
    except Exception: pass

    reply_matni = ""
    if event.is_reply:
        eski_xabar = await event.get_reply_message()
        if eski_xabar and eski_xabar.text:
            reply_matni = f"\n[DIQQAT! Foydalanuvchi sizning mana bu eskirgan xabaringizga javob qaytaryapti: '{eski_xabar.text}']\n"

    yangi_matn = event.text
    javob = await get_ai_answer(yangi_matn, sender_id, reply_matni)
    
    await event.reply(javob)

    if sender_id not in suhbat_xotirasi:
        suhbat_xotirasi[sender_id] = []
    suhbat_xotirasi[sender_id].append({"kim": "Foydalanuvchi", "matn": yangi_matn})
    suhbat_xotirasi[sender_id].append({"kim": "AI (Siz)", "matn": javob})
    if len(suhbat_xotirasi[sender_id]) > 20: 
        suhbat_xotirasi[sender_id] = suhbat_xotirasi[sender_id][-20:]

# --- 4. RENDER SERVER ---
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
    print(f"🌐 Web-server {port}-portda ishga tushdi.")

    await client.start()
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())