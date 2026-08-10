"""
Sizning haqiqiy Telegram tarixingizdan (o'zingiz yozgan xabarlaringizdan) yozish
uslubidagi takrorlanuvchi naqshlarni (iboralar, salomlashish/xayrlashish odati va h.k.)
topib, persona.json fayliga qo'shib qo'yadi.

Ishga tushirish:
    python tools/scan_style_history.py

Eslatma: bu skript .env dagi TELEGRAM_SESSION_STRING orqali sizning jonli
Telegram sessiyangizga ulanadi va faqat SIZ shaxsan yozgan xabarlarni o'qiydi.
Hech qanday ma'lumot tashqariga (Gemini'dan boshqa) yuborilmaydi.
"""
import os
import json
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
import anthropic

load_dotenv()
api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_string = os.getenv("TELEGRAM_SESSION_STRING")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

PERSONA_PATH = os.path.join(os.path.dirname(__file__), "..", "persona.json")
MAKSIMAL_XABAR = 300
MAKSIMAL_CHAT = 40


async def main():
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    await client.start()
    print("Ulandi. Shaxsiy chatlardan o'zingiz yozgan xabarlar yig'ilmoqda...")

    yozgan_xabarlar = []
    async for dialog in client.iter_dialogs(limit=MAKSIMAL_CHAT):
        if not dialog.is_user:
            continue
        try:
            async for msg in client.iter_messages(dialog.id, from_user='me', limit=15):
                if msg.text and msg.text.strip():
                    yozgan_xabarlar.append(msg.text.strip())
                if len(yozgan_xabarlar) >= MAKSIMAL_XABAR:
                    break
        except Exception:
            continue
        if len(yozgan_xabarlar) >= MAKSIMAL_XABAR:
            break

    await client.disconnect()
    print(f"{len(yozgan_xabarlar)} ta xabar yig'ildi. Claude orqali tahlil qilinmoqda...")

    if not yozgan_xabarlar:
        print("Hech qanday xabar topilmadi. Chiqilmoqda.")
        return

    namuna = "\n".join(f"- {x}" for x in yozgan_xabarlar)
    tahlil_prompt = f"""Quyida bir odamning Telegramda shaxsan o'zi yozgan xabarlari ro'yxati berilgan.
Ushbu xabarlarni tahlil qilib, uning yozish uslubidagi TAKRORLANUVCHI naqshlarni top:
1. Tez-tez ishlatiladigan so'z/iboralar (masalan salomlashish, rozillik, xayrlashish so'zlari)
2. O'ziga xos qisqartmalar yoki imlo odatlari
3. Xarakterli gap boshlash/tugatish uslublari

Faqat quyidagi JSON formatida javob ber, boshqa hech narsa yozma (izoh, ```json belgisi kabi narsalarsiz):
{{"iboralar": ["...", "...", "..."], "izoh": "qisqa umumiy xulosa"}}

Xabarlar:
{namuna}"""

    try:
        response = claude_client.messages.create(
            model="claude-opus-5",
            max_tokens=2048,
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": tahlil_prompt}]
        )
        if response.stop_reason == "refusal":
            print("Claude tahlildan bosh tortdi (refusal).")
            return
        matn = next(b.text for b in response.content if b.type == "text").strip()
        if matn.startswith("```"):
            matn = matn.strip("`")
            if matn.lower().startswith("json"):
                matn = matn[4:]
        natija = json.loads(matn)
    except Exception as e:
        print(f"Tahlilda xatolik yuz berdi: {e}")
        return

    profil = {}
    if os.path.exists(PERSONA_PATH):
        with open(PERSONA_PATH, "r", encoding="utf-8") as f:
            profil = json.load(f)

    profil["avto_topilgan_iboralar"] = natija.get("iboralar", [])
    profil["avto_izoh"] = natija.get("izoh", "")

    with open(PERSONA_PATH, "w", encoding="utf-8") as f:
        json.dump(profil, f, ensure_ascii=False, indent=2)

    print("\npersona.json muvaffaqiyatli yangilandi:")
    print(json.dumps(natija, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
