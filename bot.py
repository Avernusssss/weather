import asyncio
import json
import os
from datetime import datetime

import requests
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
import aiosqlite

# Загрузка переменных окружения
load_dotenv()

# Получение токенов из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

if not BOT_TOKEN or not WEATHER_API_KEY:
    raise ValueError("Пиши .env")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

scheduler = AsyncIOScheduler()

class UserStates(StatesGroup):
    waiting_for_city = State()

# После инициализации бота добавим:
async def init_db():
    async with aiosqlite.connect('weather_bot.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS favorite_cities
            (user_id TEXT PRIMARY KEY, city TEXT)
        ''')
        await db.commit()

async def get_favorite_city(user_id: str) -> str | None:
    async with aiosqlite.connect('weather_bot.db') as db:
        async with db.execute('SELECT city FROM favorite_cities WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else None

async def save_favorite_city(user_id: str, city: str):
    async with aiosqlite.connect('weather_bot.db') as db:
        await db.execute('''
            INSERT OR REPLACE INTO favorite_cities (user_id, city) VALUES (?, ?)
        ''', (user_id, city))
        await db.commit()

async def get_all_favorites() -> list:
    async with aiosqlite.connect('weather_bot.db') as db:
        async with db.execute('SELECT user_id, city FROM favorite_cities') as cursor:
            return await cursor.fetchall()

def get_weather(city):
    try:
        # Текущая погода
        current_url = f"http://api.openweathermap.org/data/2.5/weather?q={city},RU&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        # Прогноз
        forecast_url = f"http://api.openweathermap.org/data/2.5/forecast?q={city},RU&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        
        current_response = requests.get(current_url)
        forecast_response = requests.get(forecast_url)
        
        if current_response.status_code == 200 and forecast_response.status_code == 200:
            current_data = current_response.json()
            forecast_data = forecast_response.json()
            
            # Текущая погода
            current_weather = (
                f"🌡 Сейчас в городе {city}:\n"
                f"Температура: {current_data['main']['temp']}°C\n"
                f"Ощущается как: {current_data['main']['feels_like']}°C\n"
                f"💧 Влажность: {current_data['main']['humidity']}%\n"
                f"💨 Ветер: {current_data['wind']['speed']} м/с\n"
                f"☁️ {current_data['weather'][0]['description'].capitalize()}\n\n"
            )
            
            # Прогноз на следующие 24 часа с интервалом 4 часа
            forecast_weather = "📅 Прогноз на ближайшие 24 часа:\n\n"
            for forecast in forecast_data['list'][:6]:  # Берем первые 6 точек (24 часа)
                date = datetime.fromtimestamp(forecast['dt'])
                if date.hour % 4 == 0:  # Только каждые 4 часа
                    forecast_weather += (
                        f"🕐 {date.strftime('%H:%M')}:\n"
                        f"🌡 {forecast['main']['temp']}°C\n"
                        f"💨 {forecast['wind']['speed']} м/с\n"
                        f"☁️ {forecast['weather'][0]['description']}\n\n"
                    )
            
            return current_weather + forecast_weather
        else:
            return "Город не найден, далпаеп"
    except Exception as e:
        return f"Ошибка при получении погоды: {str(e)}"

@router.message(Command("start"))
async def start_command(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="🌍 Узнать погоду"),
            KeyboardButton(text="🔖 Установить избранный город")
        ]],
        resize_keyboard=True
    )
    
    await message.answer("Выбери действие:", reply_markup=keyboard)

@router.message(F.text == "🌍 Узнать погоду")
async def weather_command(message: Message, state: FSMContext):
    await state.set_state(UserStates.waiting_for_city)
    await message.reply("Введи название города:")

@router.message(F.text == "🔖 Установить избранный город")
async def set_favorite_city(message: Message, state: FSMContext):
    await state.set_state(UserStates.waiting_for_city)
    await message.reply("Введи название города для ежедневных уведомлений:")

@router.message(UserStates.waiting_for_city)
async def process_city(message: Message, state: FSMContext):
    city = message.text
    weather = get_weather(city)
    
    if "Ошибка" not in weather and "не найден" not in weather:
        user_id = str(message.from_user.id)
        await save_favorite_city(user_id, city)
        await message.answer(f"Город {city} установлен как избранный!\n\n{weather}")
    else:
        await message.answer(weather)
    
    await state.clear()

async def send_daily_weather():
    favorites = await get_all_favorites()
    for user_id, city in favorites:
        weather = get_weather(city)
        try:
            await bot.send_message(int(user_id), f"Погода на сегодня:\n\n{weather}")
        except Exception as e:
            print(f"Ошибка отправки сообщения пользователю {user_id}: {e}")

def schedule_jobs():
    scheduler.add_job(send_daily_weather, 'cron', hour=8, minute=0)

async def main():
    await init_db()  # Инициализация базы данных
    scheduler.start()
    schedule_jobs()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main()) 