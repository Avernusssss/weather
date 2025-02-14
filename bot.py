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

# Загрузка избранных городов пользователей
def load_favorite_cities():
    try:
        with open('favorite_cities.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

# Сохранение избранных городов пользователей
def save_favorite_cities(cities):
    with open('favorite_cities.json', 'w') as file:
        json.dump(cities, file)

favorite_cities = load_favorite_cities()

def get_weather(city):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city},RU&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        response = requests.get(url)
        data = response.json()
        
        if response.status_code == 200:
            weather_desc = data['weather'][0]['description']
            temp = data['main']['temp']
            feels_like = data['main']['feels_like']
            humidity = data['main']['humidity']
            wind_speed = data['wind']['speed']
            
            return (f"Погода в городе {city}:\n"
                   f"🌡 Температура: {temp}°C\n"
                   f"🌡 Ощущается как: {feels_like}°C\n"
                   f"💧 Влажность: {humidity}%\n"
                   f"💨 Скорость ветра: {wind_speed} м/с\n"
                   f"☁️ {weather_desc.capitalize()}")
        else:
            return "Город не найден"
    except Exception as e:
        return "Ошибка при получении погоды"

@router.message(Command("start"))
async def start_command(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="Узнать погоду"),
            KeyboardButton(text="Установить избранный город")
        ]],
        resize_keyboard=True
    )
    
    await message.answer("Выбери действие:", reply_markup=keyboard)

@router.message(F.text == "Узнать погоду")
async def weather_command(message: Message, state: FSMContext):
    await state.set_state(UserStates.waiting_for_city)
    await message.reply("Введи название города:")

@router.message(F.text == "Установить избранный город")
async def set_favorite_city(message: Message, state: FSMContext):
    await state.set_state(UserStates.waiting_for_city)
    await message.reply("Введи название города для ежедневных уведомлений:")

@router.message(UserStates.waiting_for_city)
async def process_city(message: Message, state: FSMContext):
    city = message.text
    weather = get_weather(city)
    
    if "Ошибка" not in weather and "не найден" not in weather:
        user_id = str(message.from_user.id)
        favorite_cities[user_id] = city
        save_favorite_cities(favorite_cities)
        await message.answer(f"Город {city} установлен как избранный!\n\n{weather}")
    else:
        await message.answer(weather)
    
    await state.clear()

async def send_daily_weather():
    for user_id, city in favorite_cities.items():
        weather = get_weather(city)
        try:
            await bot.send_message(int(user_id), f"Погода на сегодня:\n\n{weather}")
        except Exception as e:
            print(f"Ошибка отправки сообщения пользователю {user_id}: {e}")

def schedule_jobs():
    scheduler.add_job(send_daily_weather, 'cron', hour=8, minute=0)

async def main():
    scheduler.start()
    schedule_jobs()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main()) 