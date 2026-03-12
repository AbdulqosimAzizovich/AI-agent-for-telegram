# 🤖 Telegram AI Yordamchi (Smart Userbot)

Bu loyiha sizning shaxsiy Telegram akkauntingizni aqlli, sun'iy intellektga asoslangan yordamchiga aylantiradi. U siz band bo'lganingizda xabarlarga o'zingizning uslubingizda javob beradi, muhim suhbatlarni eslab qoladi va begonalardan keladigan chalg'ituvchi xabarlarni filtrlashga yordam beradi.

## 🌟 Asosiy Imkoniyatlar

- **Uch Qavatli AI Zanjiri (Fallback):** Asosiy model sifatida Gemini ishlaydi. Agar u xato bersa ChatGPT, u ham ishlamasa Claude modeliga avtomatik o'tiladi.
- **Aqlli Kutish Tizimi (12 soniya):** Kimdir yozganda bot darhol javob bermaydi. Agar shu 12 soniya ichida siz xabarni o'qisangiz (Read qilsangiz) yoki o'zingiz javob yozsangiz, AI aralashmaydi va o'z ishini to'xtatadi.
- **Shaxsiy Uslublar (Yuzsiz AI):** Odamlarning ID raqamiga qarab har xil muomala qiladi:
  - _Do'stlar:_ Qisqa, hazilkash va erkin (senirab).
  - _Hamkasblar:_ Jiddiy, rasmiy va qisqa.
  - _Boshqalar:_ Neytral va aniq.
- **Ish Vaqti va Filtrlar:** Faqat 08:00 dan 20:00 gacha (Toshkent vaqti bilan) faol bo'ladi. Telegram botlarga umuman javob bermaydi. Media va ovozli xabarlarni o'tkazib yuboradi (skip).
- **Begonalar uchun Avto-javob:** Kontaktlarda yo'q odam yozsa, AI isrofgarchiligini oldini olish uchun ularga bir marta "Hozir bandman" degan shablon xabar yuboradi.
- **Suhbat Konteksti (Xotira):** Har bir foydalanuvchi bilan bo'lgan oxirgi 10 ta xabarni (Sliding Window) eslab qoladi. Shuningdek, qadimiy xabarlarga yozilgan "Reply" larni ham tushunadi.
- **Masofaviy Boshqaruv (DND):** Istalgan chatda `.uxla` deb yozsangiz bot uxlash rejimiga o'tadi, `.uygon` komandasi bilan qayta faollashadi (buyruqlar darhol chatdan o'chib, Saved Messages'ga hisobot boradi).

## 🛠 Texnologiyalar

- **Python 3.10+**
- **Telethon** (Telegram bilan ishlash uchun)
- **Google Generative AI** (Gemini)
- **OpenAI** (ChatGPT)
- **Anthropic** (Claude)
- **aiohttp** (Render.com uchun soxta web-server)

## ⚙️ O'rnatish va Ishga tushirish

### 1. Kutubxonalarni o'rnatish

Loyiha papkasida terminalni ochib, quyidagi buyruqni kiriting:

```bash
pip install -r requirements.txt
```

### .env ga misol

```bash
TELEGRAM_API_ID=sening_api_id
TELEGRAM_API_HASH=sening_api_hash
TELEGRAM_SESSION_STRING=sening_uzun_session_koding

GEMINI_API_KEY=sening_gemini_kaliting
OPENAI_API_KEY=sening_openai_kaliting
CLAUDE_API_KEY=sening_claude_kaliting

# ID raqamlarni vergul bilan ajratib yozing
DOSTLAR=111111, 222222
ISHXONA=333333, 444444
```
