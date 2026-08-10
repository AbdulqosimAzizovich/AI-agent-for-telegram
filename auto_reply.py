import os
import asyncio
import json
import re
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from aiohttp import web
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import google.generativeai as genai
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

load_dotenv()

# --- 1. MA'LUMOTLAR VA SOZLAMALAR ---
api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_string = os.getenv("TELEGRAM_SESSION_STRING")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

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
scheduler = AsyncIOScheduler()

# --- STATUS O'ZGARUVCHILARI ---
oqilgan_xabarlar = {}
javob_berilgan_begonalar = set()
javob_berilgan_boshliqlar = set()
bloklangan_chatlar = set() 
bot_is_active = True
mood_waiting = False
current_mood = "Odatiy ish kayfiyatida" # Default holat
pending_timers = {} # 1 soatlik taymerlar uchun

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

# --- RAQAMLI MEN: PERSONA PROFILINI YUKLASH ---
PERSONA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona.json")

def _persona_yukla():
    try:
        with open(PERSONA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _persona_matni_qur(persona):
    if not persona:
        return ""
    qismlar = []
    au = persona.get("asosiy_uslub", {})
    if au:
        qismlar.append(
            f"- Xabar uzunligi: {au.get('xabar_uzunligi', '')}\n"
            f"- Emoji: {au.get('emoji', '')}\n"
            f"- Imlo/tinish belgilari: {au.get('imlo', '')}"
        )
    hq = persona.get("holatlarga_qarab", {})
    if hq:
        qismlar.append(
            f"- Band bo'lganda: {hq.get('band', '')}\n"
            f"- Kayfiyati zo'r bo'lganda: {hq.get('kayfiyat_zor', '')}\n"
            f"- Charchagan/asabiy bo'lganda: {hq.get('charchagan_yoki_asabiy', '')}\n"
            f"- Jiddiy masala bo'lganda: {hq.get('jiddiy_masala', '')}"
        )
    sg = persona.get("stiker_va_gif", {})
    if sg:
        qismlar.append(
            f"- Stiker/gif qachon: {sg.get('qachon_ishlatiladi', '')} ({sg.get('kimlarga', '')})"
        )
    iboralar = persona.get("avto_topilgan_iboralar", [])
    if iboralar:
        qismlar.append("- Tez-tez ishlatadigan iboralar: " + ", ".join(iboralar))
    return "\n".join(qismlar)

PERSONA = _persona_yukla()
PERSONA_MATNI = _persona_matni_qur(PERSONA)

# --- 2. AI MIYASI VA YORDAMCHI PERSONASI ---
async def get_ai_answer(yangi_xabar, sender_id, tarix_matni):
    if sender_id in YAQIN_DOSTLAR:
        toifa_matni = "Eng yaqin do'st. USLUB: SENSIRAB (sen deb) murojaat qil. Qisqa, londa."
    elif sender_id in DOSTLAR:
        toifa_matni = "Yaxshi do'st. USLUB: SIZ deb hurmat bilan, do'stona va tabiiy."
    elif sender_id in ISHXONA:
        toifa_matni = "Hamkasb. USLUB: Rasmiy, sipo va faqat ish yuzasidan."
    else:
        toifa_matni = "Oddiy tanish. USLUB: Neytral, sipo, qisqa."

    persona_qismi = f"\n[SENING (ABDULQOSIMNING) YOZISH USLUBI VA XARAKTERING]:\n{PERSONA_MATNI}\n" if PERSONA_MATNI else ""

    prompt = f"""Sen Abdulqosimning Telegramdagi shaxsiy virtual yordamchisisan.
Hozirgi paytda u: {current_mood}.
Suhbatlashayotgan odam toifasi: {toifa_matni}
{persona_qismi}
QAT'IY QOIDALAR (Buzish taqiqlanadi):
1. Birinchi marta yozayotganlarga xabaringni IKKI QISMDAN tuz: (a) avval bir necha so'zda o'zingni 'Abdulqosimning yordamchisi' deb tanishtir, (b) SHUNDAN SO'NG, XUDDI SHU XABARNING ICHIDA suhbatdoshning savoliga/salomiga ham tabiiy javob ber (masalan "qandaysiz" desa — javob qaytar). Faqat tanishtiruv bilan to'xtab qolma, suhbat davom etishi kerak.
2. Tanishtiruvdan keyingi barcha xabarlarda, suhbatni Abdulqosimning o'rniga (birinchi shaxsda) davom ettir, uning joriy holatiga (bandlik/kayfiyat) va yuqoridagi yozish uslubiga moslash!
3. Agar suhbatdosh shubhalanib seni haqiqiy ekanligini (yani seni egang) tasdiqlovchi savollar so'rashsa, darhol yordamchi ekaningni ayt va shunday tushuntir: "Men yordamchiman. Abdulqosim o'zi kirib o'qiganini xabardagi ikkita ptichka (read status) orqali bilib olasiz. Hozircha faqat bitta ptichka turibdi."
4. Suhbatni qisqa va tabiiy ushlab tur, lekin savolga to'liq javob bermay qisqartirib yubormaslik kerak - tabiiylik muhimroq.
5. Moliyaviy savol bo'lsa darhol uzr so'rab, xabarni Abdulqosimga yetkazishingni ayt. Hech qanday va'da berma.
6. ZAXIRA QOIDA: Aniq sana, vaqt, joy, summa yoki har qanday majburiyatni O'Z NOMIDAN HECH QACHON tasdiqlama va va'da berma — hatto yuqoridagi filtr bu xabarni "oddiy suhbat" deb hisoblagan bo'lsa ham. Bunday holatda "buni Abdulqosimning o'zi hal qiladi, tez orada aloqaga chiqadi" deb qisqa javob ber.

[OXIRGI SUHBAT TARIXI (Telegramdan)]:
{tarix_matni}

Suhbatdoshning oxirgi xabari: {yangi_xabar}
Sening qisqa va tabiiy javobing (faqat matn):"""

    # 1) ASOSIY: Claude
    try:
        response = await claude_client.messages.create(
            model="claude-opus-5",
            max_tokens=1024,
            output_config={"effort": "low"},  # oddiy, qisqa suhbat javobi - chuqur fikrlash shart emas
            messages=[{"role": "user", "content": prompt}]
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude javob berishdan bosh tortdi")
        return next(b.text for b in response.content if b.type == "text")
    except Exception: pass

    # 2) ZAXIRA: Gemini
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception: pass

    # 3) ZAXIRA: OpenAI
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception:
        return "Tarmoqda uzilish bo'ldi, birozdan so'ng yozing..."

# --- QAROR ANIQLAGICH: moliya, uchrashuv, va'da kabi "meni o'rnimda qaror qabul qilib bo'lmaydigan" xabarlarni topadi ---
TEZKOR_QAROR_SOZLARI = re.compile(
    r"\b(pul|qarz|dollar|so'm|som|kredit|plastik|karta|payme|click|narx|summa|"
    r"to'lov|to'la|avans|hisob\s*raqam|valyuta|foiz|procent|chek)\w*",
    re.IGNORECASE
)
TEZKOR_MIQDOR_REGEX = re.compile(r'\d+\s*(k|ming|mln|million)\b', re.IGNORECASE)

async def xabar_qaror_talab_qiladimi(matn, kontekst=""):
    if not matn:
        return False

    # 1-bosqich: aniq va shubhasiz kalit so'zlar/summalar - AI chaqirmasdan darhol aniqlanadi
    if TEZKOR_QAROR_SOZLARI.search(matn) or TEZKOR_MIQDOR_REGEX.search(matn):
        return True

    # 2-bosqich: kalit so'zga tushmaydigan holatlar uchun (masalan "ertaga uchrashamizmi?",
    # "shu yerga borasizmi?") - AI orqali xabarning ma'nosini tushunib tekshiramiz.
    # Suhbat tarixi ham beriladi - shunda "Bandmisiz ertaga?" -> "Yo'q" -> "Unda soat 5da"
    # kabi bosqichma-bosqich kelishuvlar ham kontekst orqali aniqlanadi.
    kontekst_qismi = f"\n[Oldingi suhbat]:\n{kontekst}\n" if kontekst else ""
    tekshiruv_prompt = f"""Quyidagi Telegram xabarini (va agar berilgan bo'lsa, undan oldingi suhbatni) tahlil qil.
Suhbatdosh oxirgi xabarida (avvalgi xabarlar bilan birgalikda o'qilganda) quyidagilardan birortasini
so'rayaptimi, taklif qilyaptimi yoki kelishib olyaptimi:
- pul/moliyaviy kelishuv (qarz, to'lov, narx, hisob-kitob)
- uchrashuv, joyga borish yoki vaqt/sana belgilash bo'yicha qaror
- har qanday va'da, tasdiq yoki majburiyat talab qiladigan so'rov
{kontekst_qismi}
Oddiy salomlashish, hazil yoki umumiy suhbat BU TOIFAGA KIRMAYDI.

Faqat bitta so'z bilan javob ber: "HA" yoki "YOQ".

Oxirgi xabar: "{matn}" """

    try:
        response = await claude_client.messages.create(
            model="claude-opus-5",
            max_tokens=200,
            output_config={"effort": "low"},  # sodda HA/YOQ klassifikatsiyasi
            messages=[{"role": "user", "content": tekshiruv_prompt}]
        )
        if response.stop_reason == "refusal":
            return False
        natija = next(b.text for b in response.content if b.type == "text").strip().upper()
        return natija.startswith("HA")
    except Exception:
        # AI tekshiruvi ishlamay qolsa, botni to'xtatib qo'ymaslik uchun oddiy suhbat deb hisoblaymiz
        # (1-bosqichdagi tezkor filtr eng xavfli holatlarni allaqachon ushlab qoladi,
        # asosiy AI promptidagi zaxira qoida esa ikkinchi himoya qatlami bo'lib xizmat qiladi)
        return False

# --- KUNLIK HOLAT TEKSHIRUVI (09:30) ---
async def daily_mood_check():
    global bot_is_active, mood_waiting
    bot_is_active = False # AIni bloklaymiz
    mood_waiting = True   # Javob kutish rejimini yoqamiz
    await client.send_message(
        LOG_CHAT_ID, 
        "🤖 Xayrli tong! Soat 09:30 bo'ldi. Bugungi holatingiz qanday?\n"
        "(Masalan: 'Ishda bandman', 'Kayfiyat zo'r', 'Asabiyroqman')\n"
        "Javob yozmaguningizcha AI barcha chatlarda bloklangan holatda turadi! Javobni shu kanalga yozing."
    )

# --- 1 SOATLIK ESLATMA FUNKSIYASI ---
async def reminder_to_turn_on_ai(chat_id):
    if chat_id in bloklangan_chatlar:
        await client.send_message(
            LOG_CHAT_ID, 
            f"⚠️ Diqqat! Siz chatda (ID: {chat_id}) xabar yozdingiz, lekin 1 soat o'tsa ham AIni yoqmadingiz.\n"
            f"O'sha chatga kirib `.ai_on` deb yozish esingizdan chiqmasin."
        )

# --- 3. TELEGRAM HODISALAR ---
# FILTR O'ZGARDI: Faqat shaxsiy chatlar Yoki sizning kanalingiz (LOG_CHAT_ID)
@client.on(events.NewMessage(func=lambda e: e.is_private or e.chat_id == LOG_CHAT_ID))
async def handler(event):
    global bot_is_active, mood_waiting, current_mood
    chat_id = event.chat_id
    xabar_id = event.id
    
    # Agar xabar kanaldan kelgan bo'lsa, uni yuboruvchi (sender) bo'lmasligi mumkin
    sender = await event.get_sender() if event.is_private else None
    sender_id = event.sender_id if event.is_private else None
    
    chat_info = await event.get_chat()
    ism = getattr(chat_info, 'first_name', '') or getattr(chat_info, 'title', '')
    familiya = getattr(chat_info, 'last_name', '') or ''
    toya_ism = f"{ism} {familiya}".strip() or "Noma'lum"

    # --- O'ZINGIZ YOZADIGAN KOMANDALAR VA XABARLAR (Shu jumladan kanaldagi) ---
    # event.out shaxsiy chatlarda siz yozganingizni bildiradi. 
    # Kanalda esa siz admin sifatida yozsangiz ham eventni qayta ishlashimiz kerak.
    is_my_message = event.out or (chat_id == LOG_CHAT_ID)

    if is_my_message:
        matn = event.text.lower().strip() if event.text else ""
        
        # 1. Ertalabki holatni qabul qilish (Kanal orqali)
        if chat_id == LOG_CHAT_ID and mood_waiting and not matn.startswith("."):
            current_mood = event.text
            mood_waiting = False
            bot_is_active = True
            await client.send_message(LOG_CHAT_ID, f"✅ Holat qabul qilindi: '{current_mood}'. AI ishga tushdi.")
            return

        # 2. Buyruqlar
        if matn == '.uxla':
            bot_is_active = False
            if chat_id != LOG_CHAT_ID: await event.delete()
            await client.send_message(LOG_CHAT_ID, "💤 **Bot uxlash rejimiga o'tdi.**")
            return
        elif matn == '.uygon':
            bot_is_active = True
            if chat_id != LOG_CHAT_ID: await event.delete()
            await client.send_message(LOG_CHAT_ID, "🚀 **Bot uyg'ondi!**")
            return
        elif matn == '.ai_on':
            if chat_id in bloklangan_chatlar:
                bloklangan_chatlar.remove(chat_id)
            if chat_id in pending_timers:
                pending_timers[chat_id].cancel() # Taymerni bekor qilamiz
            await event.delete()
            await client.send_message(LOG_CHAT_ID, f"🟢 **AI YOQILDI:** {toya_ism} bilan suhbatda ruxsat etildi.")
            return
        elif matn == '.ai_off':
            bloklangan_chatlar.add(chat_id)
            await event.delete()
            await client.send_message(LOG_CHAT_ID, f"🔴 **AI O'CHIRILDI:** {toya_ism} bilan suhbat bloklandi.")
            return

        # 3. Agar AI o'chiq bo'lsa-yu, siz o'zingiz kimgadir javob yozyotgan bo'lsangiz (1 soatlik taymerni yoqish)
        if chat_id in bloklangan_chatlar and chat_id != LOG_CHAT_ID and not matn.startswith("."):
            if chat_id in pending_timers:
                pending_timers[chat_id].cancel()
            
            task = client.loop.create_task(asyncio.sleep(3600)) # 3600 soniya = 1 soat
            task.add_done_callback(lambda t: client.loop.create_task(reminder_to_turn_on_ai(chat_id)))
            pending_timers[chat_id] = task

        return

    # --- BOSHQALAR YOZGAN XABARLAR (Faqat shaxsiy chatlarda ishlaydi) ---
    if chat_id == LOG_CHAT_ID: 
        return # Kanalga kelgan boshqa xabarlarni ignor qilish

    if not bot_is_active or chat_id in bloklangan_chatlar:
        return

    if getattr(event.message, 'media', None): return
    if getattr(sender, 'bot', False): return 

    # Boshliqlar javobi
    if sender_id in BOSHLIQLAR and sender_id not in javob_berilgan_boshliqlar:
        await event.reply("Assalomu alaykum. Xabaringizni qabul qildim. Hozir biroz ish jarayonida edim, tez orada o'zim siz bilan bog'lanaman. Hurmat bilan!")
        javob_berilgan_boshliqlar.add(sender_id)
        return

    # QAROR / MAJBURIYAT TEKSHIRUVI (moliya, uchrashuv, va'da va h.k. - bularni AI hal qilmasligi kerak)
    # Bosqichma-bosqich kelishuvlarni ("Bandmisiz?" -> "Yo'q" -> "Unda soat 5da") aniqlash uchun
    # oldingi qisqa suhbat tarixi ham klassifikatorga beriladi.
    qisqa_kontekst = ""
    try:
        oxirgi_ozgina = await client.get_messages(chat_id, limit=4)
        for x in reversed(oxirgi_ozgina):
            if x.text:
                kim = "Men" if x.out else "Suhbatdosh"
                qisqa_kontekst += f"{kim}: {x.text}\n"
    except Exception: pass

    qaror_kerakmi = await xabar_qaror_talab_qiladimi(event.text or "", qisqa_kontekst)

    if qaror_kerakmi:
        await asyncio.sleep(5)
        if oqilgan_xabarlar.get(chat_id, 0) >= xabar_id: return

        javob = "Assalomu alaykum. Bu masalani albatta o'zim shaxsan hal qilishim kerak. Xabaringizni ko'rdim, imkoni bo'lishi bilan tez orada o'zim sizga aloqaga chiqaman."
        await event.reply(javob)
        # E'tibor bering: chat bloklanmaydi, faqat shu bitta xabarga AI javob bermaydi. Suhbat davom etadi.
        await client.send_message(LOG_CHAT_ID, f"⚠️ **SHAXSAN JAVOB KERAK:** {toya_ism} qaror/moliya talab qiladigan xabar yubordi:\n\"{event.text}\"\n\nAI bu xabarga javob bermadi — o'zingiz shaxsan bog'laning.")
        return

    # ODDIY AI SUHBAT
    hozirgi_vaqt = datetime.now(ZoneInfo("Asia/Tashkent"))
    if not (8 <= hozirgi_vaqt.hour < 20): return 

    await asyncio.sleep(8)
    if oqilgan_xabarlar.get(chat_id, 0) >= xabar_id: return

    try:
        history = await client.get_messages(chat_id, limit=1)
        if history and history[0].out: return
    except Exception: pass

    # HAQIQIY TARIXNI OLISH
    tarix_matni = ""
    try:
        oxirgi_xabarlar = await client.get_messages(chat_id, limit=6)
        for x in reversed(oxirgi_xabarlar):
            if x.text:
                kim = "Men (Abdulqosim/Yordamchi)" if x.out else "Suhbatdosh"
                tarix_matni += f"{kim}: {x.text}\n"
    except Exception: pass

    yangi_matn = event.text
    javob = await get_ai_answer(yangi_matn, sender_id, tarix_matni)
    
    await event.reply(javob)

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

    # Cron taymerini ishga tushirish (Har kuni soat 09:30)
    scheduler.add_job(daily_mood_check, 'cron', hour=9, minute=30, timezone="Asia/Tashkent")
    scheduler.start()

    await client.start()
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())