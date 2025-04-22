#  тут нужно 2 функции:
#  получение данных о замятясениях через апи кажду сенкунду

#     фунциконл полулючения нового бзера вбазу данны
#     он даоженг выбрать рарстони и отпавтт точку с кординатами 

# полу полчения резальтатов от апи змелятрей надо просйтиь спо всем юезрам и разослать алерты если они взоне трски 
import asyncio
import logging
import os
import string
import uuid
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
# import yookassa
# from yookassa import Configuration
# from yookassa import Payment
from ws_client import earthquake_listener

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
TOKEN = os.environ["TELEGRAM_TOKEN"]
BACK_URL = os.environ["BACK_URL"]

SHOP_ID = os.environ["SHOP_ID"]
PAY_KEY = os.environ["PAY_KEY"]

WEBHOOK_PATH = f"/bot/{TOKEN}"
WEBHOOK_URL = BACK_URL + WEBHOOK_PATH
PAY_BACK_URL = f"{BACK_URL}/p"

ALERT = f"Появилась запись, если вы уже зарегестроволись на сайте консульства то вам понадобиться Номер заявки и Защитный код, они есть у вас на почте.\nПрямая ссылка на запись для тех кто помнит\знает  Номер заявки и Защитный код -  https://gyumri.kdmid.ru/queue/OrderInfo.aspx\nЕсли вы их не пониматье то воспользуйтесь ссылкой которую вам выслало посольство напочту\nЕсли вы не регестровались на сайте то регеструйтесь - https://gyumri.kdmid.ru/"
# ALERT = "!!!!!!!!"
# ALERT = "Important message about alerts!"

# client = pymongo.MongoClient(MONGO_URL)
# db = client.gumry


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

# bot = Bot(token=TOKEN)
# dp = Dispatcher(bot)

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
    # asyncio.create_task(after_earthquake(8, [44.527378, 40.170776], "Место землетрясения"))
    
    # Создаем геоиндекс при запуске
    await create_geo_index()
    
    yield
    
    # Shutdown
    # await bot.get_session()
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


@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse(favicon_path)


@app.get("/")
async def root():
    return {"message": "Hello World"}


# @app.post("/p")
# async def reserve_pay(request: Request):
#     try:
#         json_data = await request.json()
#         print(json_data)

#         event_type = json_data.get('event')
#         if event_type == 'payment.succeeded':
#             object_data = json_data.get('object', {})
#             tg_id = object_data.get('description')

#             if tg_id:
#                 logger.info(tg_id)
#                 await enable_alerts(tg_id)
#                 await alert_me(tg_id)
#                 return {"message": "Payment processed successfully."}
#             else:
#                 raise HTTPException(status_code=400, detail="'description' key is missing in the 'object' data.")
#         elif event_type == 'payment.waiting_for_capture':
#             await alert_manager()
#             pass

#         else:
#             return {"message": "Event is not 'payment.succeeded'. No further action taken."}

#     except ValueError as ve:
#         raise HTTPException(status_code=400, detail="Invalid JSON data.")

#     except Exception as e:
#         raise HTTPException(status_code=500, detail="An error occurred while processing the payment.")



async def alert_user(tg_id, magnitude, renge, coords, flynn_region):
    message = f"сейчас в на сросстоняии {renge} км от вас произошло землятрсяение силой {magnitude} баллов"
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

async def alert_me(tg_id):
    AL = "платеж получен, вы получите уведомление"

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {
        "chat_id": f"{tg_id}",
        "text": f"{AL}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                logger.info("Message sent successfully")
            else:
                logger.info(f"Failed to send message. Status code: {response.status}")


# async def alert_me(tg_id):
#     AL = "платеж прошел успешно, вы получите уведомление"

#     url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
#     params = {
#         "chat_id": f"{tg_id}",
#         "text": f"{AL}"
#     }

#     async with aiohttp.ClientSession() as session:
#         async with session.get(url, params=params) as response:
#             if response.status == 200:
#                 logger.info("Message sent successfully")
#             else:
#                 logger.info(f"Failed to send message. Status code: {response.status}")


async def alert_manager():
    AL = "ктото оплаьтл, платеж получен, пара его подтвердить\nhttps://yookassa.ru/my/payments"

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {
        "chat_id": f"{219045984}",
        "text": f"{AL}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                logger.info("Message sent successfully")
            else:
                logger.info(f"Failed to send message. Status code: {response.status}")


# async def has_only_printable_ascii(text):
#     """
#     Check if the string contains only printable ASCII characters.

#     Parameters:
#         text (str): The string to be checked.

#     Returns:
#         bool: True if all characters are printable ASCII characters, False otherwise.
#     """
#     return all(await asyncio.to_thread(lambda char: char in string.printable, char) for char in text)


# @app.get("/go")
# async def go():
#     # logger = logging.getLogger(__name__)
#     logger.info("hello0w")
#     tg_ids = await get_white_list(logger)
#     logger.info(tg_ids)
#     await send_alerts_to_white_list(tg_ids, logger)


# async def send_alerts_to_white_list(tg_ids, logger):
#     tasks = []
#     async with aiohttp.ClientSession() as session:
#         for tg_id in tg_ids:
#             print(tg_id)
#             logger.info(tg_id)
#             task = session.get(
#                 url=f"https://api.telegram.org/bot{TOKEN}/sendMessage",
#                 params={
#                     "chat_id": tg_id,
#                     "text": ALERT
#                 }
#             )
#             tasks.append(task)
#         responses = await asyncio.gather(*tasks)
#         for response in responses:
#             response_text = await response.text()
#             logger.info(response_text)


# async def get_white_list(logger):
#     result = []
#     try:
#         async for user_doc in db.Users.find({'anlerts_on': True}, {'_id': 0, 'anlerts_on': 0}):
#             result.append(user_doc['tg_id'])
#     except Exception as e:
#         logger.error(e)
#     return result




# @app.post(WEBHOOK_PATH)
# async def bot_webhook(update: dict):
#     telegram_update = types.Update(**update)
#     Dispatcher.set_current(dp)
#     Bot.set_current(bot)
#     await dp.process_update(telegram_update)


@app.post(WEBHOOK_PATH)
async def bot_webhook(update: dict):
    telegram_update = types.Update(**update)
    await dp.feed_update(bot=bot, update=telegram_update)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:

    # logging.info("Dummy Info")
    tg_id = message.from_user.id
    await init_user(tg_id)
    await message.answer(
        "добро поажловать, чтобы получить уведомления о землятрсяениях пришлите гелокауию. Мы сообщаем о землятрсяениях которые вы поучаствйте, уситывая растоние и мошьность \n \n Чтобы выключить уведомления нажмите нажмите /stop, чтобы возобновить или изменить просто отправте новые кориднаты")


@router.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext) -> None:
    tg_id = message.from_user.id
    if await disable_alerts(tg_id):
        await message.answer("мы не будем присылать вам уведомления")
    else:
        await message.answer("вы не подписаны на уведомления чтото пошло не так")


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
        
        await message.answer("Ваши координаты успешно обновлены, вы получите уведомления о землятрсяениях в этой зоне")
    except Exception as e:
        logger.error(f"Error updating user location: {str(e)}")
        await message.answer("Произошла ошибка при сохранении координат. Пожалуйста, попробуйте позже.")


# @router.message(Command("stop"))
# async def cmd_pay(message: Message, state: FSMContext) -> None:
#     tg_id = message.from_user.id
#     pay_url = create_pay_url(tg_id)
#     text = 'Чтобы полуить уведолмление оплатитье взнос на оплату серверов и кибаб для разработчика 500.\nподтверждение платежа происходит в ручном режиме и занимет до 24х часов.'
#     keyboard = types.InlineKeyboardMarkup()
#     keyboard.add(types.InlineKeyboardButton('Ввша ссылка на оплату', url=pay_url))
#     # await bot.send_message(message.chat.id, text, reply_markup=keyboard)
#     if await is_user_anlerts_on(tg_id):
#         await message.answer(f"Ваша подписка уже оплачена, вы получите уведомление, ")
#     else:
#         await bot.send_message(message.chat.id, text, reply_markup=keyboard)



# # def create_pay_url(tg_id):
#     # Set up YooKassa configuration with your SHOP_ID and PAY_KEY
#     Configuration.account_id = SHOP_ID
#     Configuration.secret_key = PAY_KEY

#     # Create a payment request using the YooKassa API
#     payment = Payment.create({
#         "amount": {
#             "value": "500.00",
#             "currency": "RUB"
#         },
#         "payment_method_data": {
#             "type": "bank_card"
#         },
#         "confirmation": {
#             "type": "redirect",
#             "return_url": "https://t.me/gumri_notify_bot"
#         },
#         "description": f"{tg_id}",
#         "metadata": {"tg_id": f"{tg_id}"}
#     }, uuid.uuid4())

#     # Get the confirmation URL from the payment response
#     # payment_url = payment.confirmation.confirmation_url

#     return payment.confirmation.confirmation_url


# async def is_user_in_db_USERS(tg_id):
#     if await db.Users.find_one({"tg_id": f"{tg_id}"}):
#         return True
#     else:
#         False


# async def is_user_anlerts_on(tg_id):
#     if await db.Users.find_one({"tg_id": f"{tg_id}", "anlerts_on": True}):
#         return True
#     else:
#         return False


# async def add_user_to_db_USERS(tg_id):
#     try:
#         await db.Users.insert_one({"tg_id": f"{tg_id}", "anlerts_on": False})
#     except Exception as e:
#         print(e)


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
        # if db.Users.find_one({"tg_id": f"{tg_id}"}):
        #     db.Users.find_one({"tg_id": f"{tg_id}"}, {"$set": {"anlerts_on": True}})
    except Exception as e:
        print(e)



async def get_users_with_distance(coords, magnitude):
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
    elif magnitude >= 9.5:
        range_km = 3000
    else:
        return []

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
    return results


async def after_earthquake(magnitude, coords, flynn_region):
    users = await get_users_with_distance(coords, magnitude)
    for user in users:
        await alert_user(user["tg_id"], magnitude, user["distance_km"], coords, flynn_region)
      
 