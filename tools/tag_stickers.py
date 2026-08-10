"""
Sizning tez-tez ishlatiladigan stikerlaringiz va saqlangan gif'laringizni Telegramdan
olib, ularni kayfiyat-tegi bilan belgilab, sticker_library.json fayliga yozadi.

Eslatma (dizayn tanlovi): stikerlarning ko'pchiligi animatsion (.tgs, Lottie format)
bo'ladi va rasm sifatida ochib bo'lmaydi, shuning uchun Gemini vision orqali
tasvirni "ko'rish" o'rniga - Telegram har bir stikerga biriktirilgan haqiqiy
emoji (masalan har bir stiker "kulgu" uchun ekan, unga 😂 emoji biriktirilgan
bo'ladi) ma'lumotidan foydalanamiz. Bu ancha ishonchli va tezkor usul.
GIF'lar uchun bunday signal yo'q, shuning uchun ular umumiy "kulgu/reaksiya"
tegiga qo'yiladi (odatda gif'lar shunday ishlatiladi).

Ishga tushirish:
    python tools/tag_stickers.py
"""
import os
import json
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetRecentStickersRequest, GetSavedGifsRequest
from telethon.tl.types import DocumentAttributeSticker
from dotenv import load_dotenv

load_dotenv()
api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_string = os.getenv("TELEGRAM_SESSION_STRING")

LIB_PATH = os.path.join(os.path.dirname(__file__), "..", "sticker_library.json")

# Emoji -> bizning ichki teglarimiz (auto_reply.py shu teglar orqali tanlaydi)
EMOJI_TEG_XARITASI = {
    "kulgu": set("😂🤣😆😁😅😄🙃😜😝🥳😹"),
    "rozi": set("👍✅👌🙌💪🫡🤝☺️"),
    "rad": set("👎❌🙅🚫😑"),
    "salom": set("👋🙋😊👀"),
    "rahmat": set("🙏❤️😍🥰💯"),
    "xafa": set("😢😭💔😞😔🙁😿"),
}


def emoji_dan_teg_top(emoji_char):
    for teg, toplam in EMOJI_TEG_XARITASI.items():
        if emoji_char in toplam:
            return teg
    return "boshqa"


async def main():
    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    await client.start()
    print("Ulandi. Stiker/gif ro'yxatlari olinmoqda...")

    kutubxona = []

    try:
        stickers = await client(GetRecentStickersRequest(hash=0))
        stiker_docs = getattr(stickers, "stickers", [])
    except Exception as e:
        print(f"Stikerlarni olishda xatolik: {e}")
        stiker_docs = []

    for doc in stiker_docs:
        alt = ""
        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeSticker):
                alt = attr.alt or ""
                break
        teg = emoji_dan_teg_top(alt[:1]) if alt else "boshqa"
        kutubxona.append({"id": doc.id, "kind": "sticker", "tag": teg, "alt": alt})
        print(f"  stiker {doc.id} (emoji={alt}) -> {teg}")

    try:
        gifs = await client(GetSavedGifsRequest(hash=0))
        gif_docs = getattr(gifs, "gifs", [])
    except Exception as e:
        print(f"Gif larni olishda xatolik: {e}")
        gif_docs = []

    for doc in gif_docs:
        kutubxona.append({"id": doc.id, "kind": "gif", "tag": "kulgu", "alt": ""})
        print(f"  gif {doc.id} -> kulgu (standart)")

    await client.disconnect()

    with open(LIB_PATH, "w", encoding="utf-8") as f:
        json.dump(kutubxona, f, ensure_ascii=False, indent=2)

    print(f"\nTayyor. {len(kutubxona)} ta element sticker_library.json ga yozildi "
          f"({len(stiker_docs)} stiker, {len(gif_docs)} gif).")


if __name__ == "__main__":
    asyncio.run(main())
