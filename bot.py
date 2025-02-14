from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from datetime import datetime
import asyncio
import json
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Получение токенов из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

if not BOT_TOKEN or not WEATHER_API_KEY:
    raise ValueError("Пиши .env")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
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

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ['Узнать погоду', 'Установить избранный город']
    keyboard.add(*buttons)
    
    await message.answer(
        "Выбери действие:",
        reply_markup=keyboard
    )

@dp.message_handler(text='Узнать погоду')
async def weather_command(message: types.Message):
    await UserStates.waiting_for_city.set()
    await message.reply("Введи название города:")

@dp.message_handler(text='Установить избранный город')
async def set_favorite_city(message: types.Message):
    await UserStates.waiting_for_city.set()
    await message.reply("Введи название города для ежедневных уведомлений:")

@dp.message_handler(state=UserStates.waiting_for_city)
async def process_city(message: types.Message, state: FSMContext):
    city = message.text
    weather = get_weather(city)
    
    if "Ошибка" not in weather and "не найден" not in weather:
        user_id = str(message.from_user.id)
        favorite_cities[user_id] = city
        save_favorite_cities(favorite_cities)
        await message.answer(f"Город {city} установлен как избранный!\n\n{weather}")
    else:
        await message.answer(weather)
    
    await state.finish()

async def send_daily_weather():
    for user_id, city in favorite_cities.items():
        weather = get_weather(city)
        try:
            await bot.send_message(int(user_id), f"Погода на сегодня:\n\n{weather}")
        except Exception as e:
            print(f"Ошибка отправки сообщения пользователю {user_id}: {e}")

def schedule_jobs():
    scheduler.add_job(send_daily_weather, 'cron', hour=8, minute=0)

if __name__ == '__main__':
    scheduler.start()
    schedule_jobs()
    executor.start_polling(dp, skip_updates=True) 