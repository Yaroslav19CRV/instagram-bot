import asyncio
import aiosqlite
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery
import instaloader

TOKEN = '8270962231:AAEvTQSrzRuXYviR_LlgTKaBzoIZy9cyvrk'

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Имитация мобильного браузера + задержки
L = instaloader.Instaloader()
L.context._session.headers.update({
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
})

DB_NAME = 'users.db'
SUBSCRIPTION_PRICE = 50

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                trial_used BOOLEAN DEFAULT FALSE,
                trial_end TEXT,
                subscription_end TEXT
            )
        ''')
        await db.commit()

async def get_user_status(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT trial_used, trial_end, subscription_end FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            now = datetime.now()
            if row:
                trial_used, trial_end_str, sub_end_str = row
                if sub_end_str and datetime.fromisoformat(sub_end_str) > now:
                    return 'premium'
                if trial_end_str and datetime.fromisoformat(trial_end_str) > now:
                    return 'trial'
        trial_end = (datetime.now() + timedelta(days=1)).isoformat()
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute('INSERT OR REPLACE INTO users (user_id, trial_used, trial_end) VALUES (?, ?, ?)',
                             (user_id, True, trial_end))
            await db.commit()
        return 'trial'

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "🔥 Привет! Я анонимный просмотрщик публичных аккаунтов Instagram\n\n"
        "Отправь никнейм (например: nasa)\n"
        "Покажу последние посты.\n\n"
        "Первый день бесплатно! 🌟\n"
        "/subscribe — премиум-подписка"
    )

@dp.message(Command("subscribe"))
async def subscribe(message: types.Message):
    prices = [LabeledPrice(label="Премиум 30 дней", amount=SUBSCRIPTION_PRICE)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Премиум-доступ",
        description="Неограниченный просмотр публичных постов Instagram",
        payload="premium_month",
        provider_token="",
        currency="XTR",
        prices=prices
    )

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(lambda msg: msg.successful_payment is not None)
async def payment_success(message: types.Message):
    user_id = message.from_user.id
    end_date = (datetime.now() + timedelta(days=30)).isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE users SET subscription_end = ? WHERE user_id = ?', (end_date, user_id))
        await db.commit()
    await message.answer("✅ Оплата прошла! Премиум на 30 дней активирован.")

@dp.message()
async def handle_username(message: types.Message):
    status = await get_user_status(message.from_user.id)
    if status not in ['premium', 'trial']:
        await message.answer("⛔ Доступ закончился. Купи подписку: /subscribe")
        return

    username = message.text.strip().lstrip('@').lower()
    loading = await message.answer(f"🔍 Ищу @{username}... Пожалуйста, подожди 10–20 сек")

    try:
        # Задержка перед запросом
        await asyncio.sleep(random.uniform(3, 7))
        
        profile = instaloader.Profile.from_username(L.context, username)
        
        count = 0
        for post in profile.get_posts():
            if count >= 5:
                break
            await asyncio.sleep(random.uniform(2, 4))  # Задержка между постами
            if post.is_video:
                await bot.send_video(message.chat.id, post.video_url, caption=f"@{username} • {post.caption[:100] if post.caption else ''}")
            else:
                await bot.send_photo(message.chat.id, post.url, caption=f"@{username} • {post.caption[:100] if post.caption else ''}")
            count += 1
        
        if count == 0:
            await loading.edit_text("😔 Нет постов или аккаунт приватный")
        else:
            await loading.edit_text(f"✅ Отправил {count} последних постов от @{username}!")
        
        if status == 'trial':
            await message.answer("🌟 У тебя trial на сегодня. Завтра потребуется подписка.")

    except instaloader.exceptions.ConnectionException:
        await loading.edit_text("🌐 Проблема с соединением Instagram. Попробуй через 5–10 минут или другой ник.")
    except instaloader.exceptions.PrivateProfileNotFollowedException:
        await loading.edit_text("🔒 Аккаунт приватный — работает только с публичными.")
    except instaloader.exceptions.ProfileNotExistsException:
        await loading.edit_text("❌ Аккаунт не найден.")
    except Exception:
        await loading.edit_text("🚫 Временная ошибка. Попробуй позже.")

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
