import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI

import aiohttp
from aiogram import Bot, Dispatcher, Router, types

from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorClient
from ws_client import earthquake_listener

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
TOKEN = os.environ["TELEGRAM_TOKEN"]
BACK_URL = os.environ["BACK_URL"]

SHOP_ID = os.environ["SHOP_ID"]
PAY_KEY = os.environ["PAY_KEY"]

WEBHOOK_PATH = f"/bot/{TOKEN}"
WEBHOOK_URL = BACK_URL + WEBHOOK_PATH
DATABASE_NAME = "Earthquake"

# Подключение к MongoDB
client = AsyncIOMotorClient(MONGO_URL)
db = client[DATABASE_NAME]

# Создаем геоиндекс для поля location
async def create_geo_index():
    try:
        await db.Users.create_index([("location", "2dsphere")])
        logger.info("Geo index created successfully")
    except Exception as e:
        logger.error(f"Error creating geo index: {str(e)}")


bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(
            url=WEBHOOK_URL
        )
    print("Webhook set")
    print(webhook_info)

    asyncio.create_task(earthquake_listener(after_earthquake))
    # Создаем геоиндекс при запуске

    await create_geo_index()
    
    yield
    
    await bot.session.close()
    logging.info("Bot stopped")

app = FastAPI(lifespan=lifespan)
origins = [
    "http://localhost:3000",
    "localhost:3000",
    f"{BACK_URL}"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

favicon_path = 'favicon.ico'
# Создаем логгер для FastAPI
logger = logging.getLogger("fastapi")

# Настраиваем обработчики логов
logging.basicConfig(
    level=logging.DEBUG,  # Уровень логирования
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",  # Формат сообщения
    datefmt="%Y-%m-%d %H:%M:%S"  # Формат даты и времени
)

logging.getLogger("pymongo").setLevel(logging.WARNING)

# Если используешь motor, тоже можно ограничить
logging.getLogger("motor").setLevel(logging.WARNING)

# Добавляем обработчик логов в консоль
logger.addHandler(logging.StreamHandler())


@app.get("/")
async def root():
    return {"message": "Hellow World"}


async def alert_user(tg_id, magnitude, renge, coords, flynn_region):
    message = f"Currently, an earthquake with a magnitude of {magnitude} occurred at a distance of {renge} km from you"
    await alert(tg_id, message, coords, flynn_region)


async def alert(tg_id, message, coords=None, flynn_region=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    if coords:
        url = f"https://api.telegram.org/bot{TOKEN}/sendVenue"
        params = {
            "chat_id": f"{tg_id}",
            "latitude": coords[1],  # Широта
            "longitude": coords[0],  # Долгота
            "title": f"{flynn_region}",
            "address": message
        }
    else:
        params = {
            "chat_id": f"{tg_id}",
            "text": f"{message}"
        }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                logger.info("Message sent successfully")
            else:
                logger.info(f"Failed to send message. Status code: {response.status}")


@app.post(WEBHOOK_PATH)
async def bot_webhook(update: dict):
    telegram_update = types.Update(**update)
    await dp.feed_update(bot=bot, update=telegram_update)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    tg_id = message.from_user.id
    await init_user(tg_id)
    await message.answer(
        "Welcome! To receive earthquake notifications, please send your geolocation. We will notify you about earthquakes you might experience, taking into account distance and magnitude \n \n To disable notifications, press /stop, to resume or change simply send new coordinates")


@router.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext) -> None:
    tg_id = message.from_user.id
    if await disable_alerts(tg_id):
        await message.answer("we will not send you notifications")
    else:
        await message.answer("you are not subscribed to notifications something went wrong")


@router.message(lambda message: message.location)
async def handle_location(message: Message):
    tg_id = message.from_user.id
    location = message.location
    latitude = float(location.latitude)
    longitude = float(location.longitude)
    
    logger.info(f"Received location from user {tg_id}: latitude={latitude}, longitude={longitude}")
    logger.info(f"Full location object: {location}")

    try:
        # Проверяем существование пользователя
        existing_user = await db.Users.find_one({"tg_id": tg_id})
        logger.info(f"Existing user data: {existing_user}")
        
        # Создаем объект для обновления
        update_data = {
            "location": {
                "type": "Point",
                "coordinates": [longitude, latitude]
            },
            "alerts_on": True
        }
        
        logger.info(f"Update data: {update_data}")
        
        # Обновляем данные
        update_result = await db.Users.update_one(
            {"tg_id": tg_id},
            {"$set": update_data},
            upsert=True  # Создаем документ, если он не существует
        )
        
        logger.info(f"Update result: {update_result.raw_result}")
        
        # Проверяем результат обновления
        updated_user = await db.Users.find_one({"tg_id": tg_id})
        logger.info(f"Updated user data: {updated_user}")
        
        await message.answer("Your coordinates have been successfully updated, you will receive notifications about earthquakes in this area")
    except Exception as e:
        logger.error(f"Error updating user location: {str(e)}")
        await message.answer("An error occurred while saving coordinates. Please try again later.")


async def init_user(tg_id):
    try:
        existing_user = await db.Users.find_one({"tg_id": f"{tg_id}"})
        if not existing_user:
            user_data = {
                "tg_id": f"{tg_id}", 
                "alerts_on": False, 
                "location": {
                    "type": "Point",
                    "coordinates": [0, 0]
                }
            }
            result = await db.Users.insert_one(user_data)
            logger.info(f"New user created with id: {result.inserted_id}")
            return True
        else:
            logger.info(f"User {tg_id} already exists")
            return False
    except Exception as e:
        logger.error(f"Error initializing user: {str(e)}")
        return False


async def disable_alerts(tg_id):
    try:
        await db.Users.update_one(
            {"tg_id": tg_id},
            {"$set": {"alerts_on": False}}
        )
        return True
    except Exception as e:
        print(e)
        return False


async def enable_alerts(tg_id):  # надо потсмреть еслти они не включены то включить
    try:
        await db.Users.update_one(
            {"tg_id": tg_id},
            {"$set": {"alerts_on": True}}
        )
    except Exception as e:
        print(e)



async def get_users_with_distance(coords, magnitude):
    logger.info(f"Поиск пользователей для землетрясения M{magnitude} на {coords}")
    
    if 2.5 <= magnitude < 3.5:
        range_km = 15
    elif 3.5 <= magnitude < 4.5:
        range_km = 50
    elif 4.5 <= magnitude < 5.5:
        range_km = 100
    elif 5.5 <= magnitude < 6.5:
        range_km = 250
    elif 6.5 <= magnitude < 7.5:
        range_km = 500
    elif 7.5 <= magnitude < 8.5:
        range_km = 1000
    elif 8.5 <= magnitude < 9.5:
        range_km = 2000
    elif magnitude >= 9.5 and magnitude < 15:
        range_km = 3000
    elif magnitude >= 50:
        range_km = 500000
    else:
        logger.info(f"Землетрясение слишком слабое (M{magnitude}), пропускаем")
        return []

    logger.info(f"Ищем пользователей в радиусе {range_km} км")

    # Агрегация с $geoNear
    pipeline = [
        {
            "$geoNear": {
                "near": {"type": "Point", "coordinates": coords},
                "distanceField": "dist.calculated",
                "maxDistance": range_km * 1000,  # в метрах
                "spherical": True,
                "query": {"alerts_on": True}
            }
        },
        {
            "$limit": 500  # ограничь если хочешь
        }
    ]

    cursor = db.Users.aggregate(pipeline, allowDiskUse=True)
    results = []
    async for doc in cursor:
        # можно округлять расстояние и добавлять в результаты
        dist_km = round(doc['dist']['calculated'] / 1000, 1)
        results.append({
            "tg_id": doc["tg_id"],
            "distance_km": dist_km,
            "username": doc.get("username"),
        })
    
    logger.info(f"Найдено {len(results)} пользователей в зоне землетрясения")
    return results


async def after_earthquake(magnitude, coords, flynn_region):
    users = await get_users_with_distance(coords, magnitude)
    for user in users:
        await alert_user(user["tg_id"], magnitude, user["distance_km"], coords, flynn_region)
  