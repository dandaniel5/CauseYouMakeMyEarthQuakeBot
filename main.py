import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI

import aiohttp
from aiogram import Bot, Dispatcher, Router, types

from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorClient
from ws_client import earthquake_listener
from bson import ObjectId

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
TOKEN = os.environ["TELEGRAM_TOKEN"]
TOKEN_2 = os.environ["TELEGRAM_TOKEN_2"]
BACK_URL = os.environ["BACK_URL"]

MY_ID = os.environ["MY_ID"]

WEBHOOK_PATH = f"/bot/{TOKEN}"
WEBHOOK_PATH_2 = f"/bot/{TOKEN_2}"
WEBHOOK_URL = BACK_URL + WEBHOOK_PATH
WEBHOOK_URL_2 = BACK_URL + WEBHOOK_PATH_2
DATABASE_NAME = "Earthquake"
DATABASE_NAME_2 = "Utilities"

# Подключение к MongoDB
client = AsyncIOMotorClient(MONGO_URL)
db = client[DATABASE_NAME]
db_2 = client[DATABASE_NAME_2]

# Создаем геоиндекс для поля location
async def create_geo_index():
    try:
        await db.Users.create_index([("location", "2dsphere")])
        logger.info("Geo index created successfully")
    except Exception as e:
        logger.error(f"Error creating geo index: {str(e)}")


bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
bot_2 = Bot(TOKEN_2, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
dp_2 = Dispatcher()
router = Router()
router_2 = Router()
dp.include_router(router)
dp_2.include_router(router_2)

class BotStates(StatesGroup):
    waiting_for_bot_url = State()
    admin_waiting_for_bot_url = State()
    admin_waiting_for_description = State()
    admin_waiting_for_categories = State()
    admin_adding_category = State()

async def create_categories_collection():
    try:
        await db_2.create_collection("Categories")
        await db_2.Categories.create_index("name", unique=True)
        logger.info("Categories collection created successfully")
    except Exception as e:
        logger.error(f"Error creating categories collection: {str(e)}")

async def create_bots_collection():
    try:
        await db_2.create_collection("Bots")
        await db_2.Bots.create_index("username", unique=True)
        logger.info("Bots collection created successfully")
    except Exception as e:
        logger.error(f"Error creating bots collection: {str(e)}")

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

    webhook_info_2 = await bot_2.get_webhook_info()
    if webhook_info_2.url != WEBHOOK_URL_2:
        await bot_2.set_webhook(
            url=WEBHOOK_URL_2
        )
    print("Webhook set 2")
    print(webhook_info_2)

    asyncio.create_task(earthquake_listener(after_earthquake))
    await create_geo_index()
    await create_categories_collection()
    await create_bots_collection()
    
    yield
    
    await bot.session.close()
    await bot_2.session.close()
    logging.info("Bots stopped")

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

async def alert_2_me(message: str, reply_markup: InlineKeyboardMarkup = None):
    url = f"https://api.telegram.org/bot{TOKEN_2}/sendMessage"
    params = {
        "chat_id": f"{MY_ID}",
        "text": message,
        "parse_mode": "HTML"
    }
    if reply_markup:
        params["reply_markup"] = reply_markup.json()
    
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


@app.post(WEBHOOK_PATH_2)
async def bot_webhook_2(update: dict):
    telegram_update = types.Update(**update)
    await dp_2.feed_update(bot=bot_2, update=telegram_update)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    tg_id = message.from_user.id
    await init_user(tg_id)
    await message.answer(
        "Welcome! To receive earthquake notifications, please send your geolocation. We will notify you about earthquakes you might experience, taking into account distance and magnitude \n \n To disable notifications, press /stop, to resume or change simply send new coordinates")


@router_2.message(Command("start"))
async def cmd_start_2(message: Message, state: FSMContext) -> None:
    try:
        tg_id = message.from_user.id
        await init_user_2(tg_id)
        
        # Получаем только существующие категории
        categories = await db_2.Categories.find().to_list(length=None)
        logger.info(f"Found categories: {categories}")
        
        # Создаем клавиатуру с категориями
        keyboard = []
        
        if not categories:
            # Если категорий нет, показываем только кнопку добавления бота
            keyboard.append([InlineKeyboardButton(
                text="➕ Добавить бота",
                callback_data="add_bot"
            )])
            await message.answer(
                "Добро пожаловать! Начните с добавления бота:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
            return
        
        # Если категории есть, показываем их
        for category in categories:
            keyboard.append([InlineKeyboardButton(
                text=category["name"],
                callback_data=f"category_{category['_id']}"
            )])
        
        # Добавляем кнопку добавления бота для всех пользователей
        keyboard.append([InlineKeyboardButton(
            text="➕ Добавить бота",
            callback_data="add_bot"
        )])
        
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await message.answer(
            "Выберите категорию или добавьте нового бота:",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error in cmd_start_2: {str(e)}")
        await message.answer(
            "❌ Произошла ошибка при запуске бота.\n"
            "Попробуйте еще раз или обратитесь к администратору."
        )

@router.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext) -> None:
    tg_id = message.from_user.id
    if await disable_alerts(tg_id):
        await message.answer("we will not send you notifications")
    else:
        await message.answer("you are not subscribed to notifications something went wrong")


@router_2.message(Command("stop"))
async def cmd_stop_2(message: Message, state: FSMContext) -> None:
    tg_id = message.from_user.id
    if await disable_alerts_2(tg_id):
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

async def init_user_2(tg_id):
    try:
        existing_user = await db_2.Users.find_one({"tg_id": f"{tg_id}"})
        if not existing_user:
            user_data = {
                "tg_id": f"{tg_id}", 
                "alerts_on": False,
            }
            result = await db_2.Users.insert_one(user_data)
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

async def disable_alerts_2(tg_id):
    try:
        await db_2.Users.update_one(
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

async def enable_alerts_2(tg_id):  # надо потсмреть еслти они не включены то включить
    try:
        await db_2.Users.update_one(
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

async def get_categories_keyboard() -> InlineKeyboardMarkup:
    try:
        categories = await db_2.Categories.find().to_list(length=None)
        logger.info(f"Getting categories for keyboard: {categories}")
        
        keyboard = []
        
        if not categories:
            keyboard.append([InlineKeyboardButton(
                text="➕ Добавить новую категорию",
                callback_data="add_new_category"
            )])
        else:
            for category in categories:
                category_id = str(category['_id'])
                logger.info(f"Adding category to keyboard: {category['name']} with ID: {category_id}")
                keyboard.append([InlineKeyboardButton(
                    text=category["name"],
                    callback_data=f"category_{category_id}"
                )])
            keyboard.append([InlineKeyboardButton(
                text="➕ Добавить бота",
                callback_data="add_bot"
            )])
            
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    except Exception as e:
        logger.error(f"Error getting categories keyboard: {str(e)}")
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="❌ Ошибка загрузки категорий",
                callback_data="error"
            )]
        ])

@router_2.callback_query(lambda c: c.data == "no_bots")
async def handle_no_bots(callback_query: types.CallbackQuery):
    await callback_query.answer("В этой категории пока нет ботов")

@router_2.callback_query(lambda c: c.data == "back_to_categories")
async def back_to_categories(callback_query: types.CallbackQuery):
    try:
        # Получаем все категории
        categories = await db_2.Categories.find().to_list(length=None)
        
        # Создаем клавиатуру с категориями
        keyboard = []
        for category in categories:
            keyboard.append([InlineKeyboardButton(
                text=category["name"],
                callback_data=f"category_{category['_id']}"
            )])
        
        # Добавляем кнопку добавления бота для всех пользователей
        keyboard.append([InlineKeyboardButton(
            text="➕ Добавить бота",
            callback_data="add_bot"
        )])
        
        await callback_query.message.edit_text(
            "Выберите категорию или добавьте нового бота:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        logger.error(f"Error in back_to_categories: {str(e)}")
        await callback_query.answer("❌ Произошла ошибка при возврате к категориям")

@router_2.callback_query(lambda c: c.data.startswith("category_"))
async def show_category_bots(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        # Проверяем, находимся ли мы в процессе добавления бота
        current_state = await state.get_state()
        if current_state == BotStates.admin_waiting_for_categories:
            # Если мы добавляем бота, обрабатываем выбор категории
            category_id = callback_query.data.split("_")[1]
            try:
                category = await db_2.Categories.find_one({"_id": ObjectId(category_id)})
                if not category:
                    await callback_query.answer("❌ Категория не найдена!")
                    return
                
                # Переключаем состояние выбора категории
                new_selected_state = not category.get('selected', False)
                await db_2.Categories.update_one(
                    {"_id": ObjectId(category_id)},
                    {"$set": {"selected": new_selected_state}}
                )
                
                # Обновляем клавиатуру
                keyboard = await get_categories_for_selection()
                await callback_query.message.edit_reply_markup(reply_markup=keyboard)
                
                # Показываем уведомление о выборе
                if new_selected_state:
                    await callback_query.answer("✅ Категория выбрана")
                else:
                    await callback_query.answer("❌ Категория отменена")
                return
                
            except Exception as e:
                logger.error(f"Error selecting category: {str(e)}")
                await callback_query.answer("❌ Ошибка при выборе категории")
                return
        
        # Если мы не добавляем бота, показываем ботов в категории
        category_id = callback_query.data.split("_")[1]
        logger.info(f"Showing bots for category ID: {category_id}")
        
        try:
            category = await db_2.Categories.find_one({"_id": ObjectId(category_id)})
            logger.info(f"Found category: {category}")
        except Exception as e:
            logger.error(f"Error finding category: {str(e)}")
            await callback_query.answer("❌ Ошибка при поиске категории")
            return
        
        if not category:
            await callback_query.answer("❌ Категория не найдена!")
            return
            
        # Получаем только подтвержденных ботов в категории
        bots = await db_2.Bots.find({
            "categories": ObjectId(category_id),
            "is_approved": True
        }).to_list(length=None)
        
        keyboard = []
        
        if not bots:
            keyboard.append([InlineKeyboardButton(
                text="Нет ботов в этой категории",
                callback_data="no_bots"
            )])
        else:
            for bot in bots:
                keyboard.append([InlineKeyboardButton(
                    text=bot["name"],
                    url=bot["url"]
                )])
                
        keyboard.append([InlineKeyboardButton(
            text="◀️ Назад",
            callback_data="back_to_categories"
        )])
        
        await callback_query.message.edit_text(
            f"Боты в категории {category['name']}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        logger.error(f"Error showing category bots: {str(e)}")
        await callback_query.answer("❌ Произошла ошибка при загрузке категории")

@router_2.callback_query(lambda c: c.data.startswith("select_category_"))
async def select_category(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        category_id = callback_query.data.replace("select_category_", "")
        logger.info(f"Selecting category with ID: {category_id}")
        
        try:
            category = await db_2.Categories.find_one({"_id": ObjectId(category_id)})
            logger.info(f"Found category: {category}")
        except Exception as e:
            logger.error(f"Error finding category: {str(e)}")
            await callback_query.answer("❌ Ошибка при поиске категории")
            return
        
        if not category:
            await callback_query.answer("❌ Категория не найдена!")
            return
        
        try:
            # Переключаем состояние выбора категории
            new_selected_state = not category.get('selected', False)
            await db_2.Categories.update_one(
                {"_id": ObjectId(category_id)},
                {"$set": {"selected": new_selected_state}}
            )
            
            # Обновляем клавиатуру
            keyboard = await get_categories_for_selection()
            await callback_query.message.edit_reply_markup(reply_markup=keyboard)
            
            # Показываем уведомление о выборе
            if new_selected_state:
                await callback_query.answer("✅ Категория выбрана")
            else:
                await callback_query.answer("❌ Категория отменена")
                
        except Exception as e:
            logger.error(f"Error updating category selection: {str(e)}")
            await callback_query.answer("❌ Ошибка при выборе категории")
            
    except Exception as e:
        logger.error(f"Error in select_category: {str(e)}")
        await callback_query.answer("❌ Произошла ошибка")

@router_2.callback_query(lambda c: c.data == "add_new_category")
async def add_new_category_start(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if not await is_admin(callback_query.from_user.id):
            await callback_query.message.edit_text(
                "❌ У вас нет прав для выполнения этой команды.\n"
                "Нажмите /start для возврата в главное меню"
            )
            return
            
        # Сохраняем текущее состояние, если мы добавляем бота
        current_state = await state.get_state()
        if current_state == BotStates.admin_waiting_for_categories:
            await state.update_data(return_to_bot_adding=True)
            
        await state.set_state(BotStates.admin_adding_category)
        await callback_query.message.edit_text(
            "Введите название новой категории:\n\n"
            "Нажмите /cancel для отмены"
        )
    except Exception as e:
        logger.error(f"Error in add_new_category_start: {str(e)}")
        await callback_query.message.edit_text(
            "❌ Произошла ошибка.\n"
            "Нажмите /start для возврата в главное меню"
        )

@router_2.message(BotStates.admin_adding_category)
async def process_new_category(message: Message, state: FSMContext):
    try:
        if not await is_admin(message.from_user.id):
            await message.answer(
                "❌ У вас нет прав для выполнения этой команды.\n"
                "Нажмите /start для возврата в главное меню"
            )
            await state.clear()
            return
            
        category_name = message.text.strip()
        if len(category_name) < 2:
            await message.answer(
                "❌ Название категории слишком короткое. Минимум 2 символа.\n"
                "Попробуйте еще раз или нажмите /cancel для отмены"
            )
            return
            
        try:
            # Проверяем, не существует ли уже такая категория
            existing_category = await db_2.Categories.find_one({"name": category_name})
            if existing_category:
                await message.answer(
                    f"❌ Категория '{category_name}' уже существует!\n"
                    "Попробуйте другое название или нажмите /cancel для отмены"
                )
                return
                
            result = await db_2.Categories.insert_one({
                "name": category_name,
                "selected": False
            })
            
            # Проверяем, нужно ли вернуться к добавлению бота
            data = await state.get_data()
            if data.get('return_to_bot_adding'):
                # Возвращаемся к выбору категорий для бота
                await state.set_state(BotStates.admin_waiting_for_categories)
                keyboard = await get_categories_for_selection()
                await message.answer(
                    f"✅ Категория '{category_name}' добавлена!\n\n"
                    "Выберите категории для бота:\n"
                    "⬜️ - категория не выбрана\n"
                    "☑️ - категория выбрана\n\n"
                    "Нажмите на категорию, чтобы выбрать или отменить выбор.\n"
                    "После выбора всех нужных категорий нажмите '✅ Готово'\n\n"
                    "Нажмите /cancel для отмены",
                    reply_markup=keyboard
                )
                await state.update_data(return_to_bot_adding=False)
                return
            
            # Если мы не добавляем бота, показываем обновленный список категорий
            categories = await db_2.Categories.find().to_list(length=None)
            keyboard = []
            for category in categories:
                keyboard.append([InlineKeyboardButton(
                    text=category["name"],
                    callback_data=f"category_{category['_id']}"
                )])
            
            keyboard.append([InlineKeyboardButton(
                text="➕ Добавить бота",
                callback_data="add_bot"
            )])
            
            await message.answer(
                f"✅ Категория '{category_name}' добавлена!\n\n"
                "Выберите категорию:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error adding new category: {str(e)}")
            await message.answer(
                f"❌ Ошибка при добавлении категории: {str(e)}\n"
                "Попробуйте еще раз или нажмите /cancel для отмены"
            )
    except Exception as e:
        logger.error(f"Error in process_new_category: {str(e)}")
        await message.answer(
            "❌ Произошла ошибка.\n"
            "Нажмите /start для возврата в главное меню"
        )
        await state.clear()

@router_2.message(Command("cancel"))
async def cancel_state(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer(
            "❌ Операция отменена.\n\n"
            "Используйте /start для начала работы."
        )
    else:
        await message.answer("Нет активных операций для отмены.")

@router_2.callback_query(lambda c: c.data == "finish_categories")
async def finish_categories_selection(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        # Получаем все сохраненные данные
        data = await state.get_data()
        logger.info(f"State data: {data}")
        
        if 'bot_url' not in data or 'description' not in data:
            logger.error("Missing required data in state")
            await callback_query.message.edit_text(
                "❌ Ошибка: не найдены данные о боте.\n"
                "Начните сначала с команды /start"
            )
            await state.clear()
            return
        
        selected_categories = await db_2.Categories.find({"selected": True}).to_list(length=None)
        
        if not selected_categories:
            await callback_query.message.edit_text(
                "❌ Выберите хотя бы одну категорию!\n"
                "Нажмите /cancel для отмены"
            )
            return
        
        bot_url = data['bot_url']
        description = data['description']
        category_ids = [cat['_id'] for cat in selected_categories]
        
        username = bot_url.replace("@", "").replace("https://t.me/", "")
        bot_data = {
            "username": username,
            "name": description,
            "url": f"https://t.me/{username}",
            "categories": category_ids,
            "is_approved": False,  # Бот ожидает подтверждения
            "added_by": callback_query.from_user.id  # Сохраняем ID пользователя, который добавил бота
        }
        
        # Добавляем бота
        result = await db_2.Bots.insert_one(bot_data)
        logger.info(f"Bot added successfully: {result.inserted_id}")
        
        # Сбрасываем флаги выбора категорий
        await db_2.Categories.update_many(
            {"selected": True},
            {"$set": {"selected": False}}
        )
        
        # Формируем сообщение с информацией о добавленном боте
        success_message = (
            f"✅ Бот добавлен и ожидает подтверждения!\n\n"
            f"🔗 URL: {bot_url}\n"
            f"📝 Описание: {description}\n"
            f"📂 Категории:\n"
        )
        for cat in selected_categories:
            success_message += f"  • {cat['name']}\n"
        
        # Создаем клавиатуру для пользователя
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="◀️ Вернуться в главное меню",
                callback_data="back_to_categories"
            )]
        ])
        
        # Отправляем сообщение пользователю
        await callback_query.message.edit_text(success_message, reply_markup=keyboard)
        
        # Отправляем уведомление администратору
        admin_message = (
            f"🆕 Новый бот добавлен и ожидает подтверждения!\n\n"
            f"🔗 URL: {bot_url}\n"
            f"📝 Описание: {description}\n"
            f"📂 Категории:\n"
        )
        for cat in selected_categories:
            admin_message += f"  • {cat['name']}\n"
        
        # Создаем клавиатуру для админа
        admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"approve_bot_{result.inserted_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject_bot_{result.inserted_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить описание",
                    callback_data=f"edit_bot_name_{result.inserted_id}"
                ),
                InlineKeyboardButton(
                    text="📂 Изменить категории",
                    callback_data=f"edit_bot_categories_{result.inserted_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Проверить бота",
                    url=f"https://t.me/{username}"
                )
            ]
        ])
        
        # Отправляем уведомление админу через bot_2
        try:
            await bot_2.send_message(
                chat_id=MY_ID,
                text=admin_message,
                reply_markup=admin_keyboard,
                parse_mode="HTML"
            )
            logger.info("Admin notification sent successfully")
        except Exception as e:
            logger.error(f"Error sending admin notification: {str(e)}")
            # Пробуем отправить через alert_2_me как запасной вариант
            await alert_2_me(admin_message, reply_markup=admin_keyboard)
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error adding bot: {str(e)}")
        error_message = f"❌ Ошибка при добавлении бота: {str(e)}"
        await callback_query.message.edit_text(error_message)
        await alert_2_me(f"❌ Ошибка при добавлении бота {bot_url}: {str(e)}")
        await state.clear()

@router_2.callback_query(lambda c: c.data.startswith("approve_bot_"))
async def approve_bot(callback_query: types.CallbackQuery):
    try:
        if not await is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ У вас нет прав для выполнения этой команды.")
            return
            
        bot_id = callback_query.data.replace("approve_bot_", "")
        bot = await db_2.Bots.find_one({"_id": ObjectId(bot_id)})
        
        if not bot:
            await callback_query.answer("❌ Бот не найден!")
            return
            
        await db_2.Bots.update_one(
            {"_id": ObjectId(bot_id)},
            {"$set": {"is_approved": True}}
        )
        
        # Создаем клавиатуру для возврата в главное меню
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="◀️ Вернуться в главное меню",
                callback_data="back_to_categories"
            )]
        ])
        
        await callback_query.message.edit_text(
            f"✅ Бот {bot['name']} подтвержден и добавлен в каталог!",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error approving bot: {str(e)}")
        await callback_query.answer("❌ Произошла ошибка при подтверждении бота")

@router_2.callback_query(lambda c: c.data.startswith("reject_bot_"))
async def reject_bot(callback_query: types.CallbackQuery):
    try:
        if not await is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ У вас нет прав для выполнения этой команды.")
            return
            
        bot_id = callback_query.data.replace("reject_bot_", "")
        bot = await db_2.Bots.find_one({"_id": ObjectId(bot_id)})
        
        if not bot:
            await callback_query.answer("❌ Бот не найден!")
            return
            
        await db_2.Bots.delete_one({"_id": ObjectId(bot_id)})
        
        # Создаем клавиатуру для возврата в главное меню
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="◀️ Вернуться в главное меню",
                callback_data="back_to_categories"
            )]
        ])
        
        await callback_query.message.edit_text(
            f"❌ Бот {bot['name']} отклонен и удален из базы данных.",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error rejecting bot: {str(e)}")
        await callback_query.answer("❌ Произошла ошибка при отклонении бота")

@router_2.callback_query(lambda c: c.data.startswith("edit_bot_name_"))
async def edit_bot_name(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if not await is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ У вас нет прав для выполнения этой команды.")
            return
            
        bot_id = callback_query.data.replace("edit_bot_name_", "")
        bot = await db_2.Bots.find_one({"_id": ObjectId(bot_id)})
        
        if not bot:
            await callback_query.answer("❌ Бот не найден!")
            return
            
        # Сохраняем ID бота в состоянии
        await state.set_state(BotStates.admin_waiting_for_description)
        await state.update_data(editing_bot_id=bot_id)
        
        await callback_query.message.edit_text(
            f"Введите новое описание для бота:\n\n"
            f"Текущее описание: {bot['name']}\n\n"
            "Нажмите /cancel для отмены"
        )
        
    except Exception as e:
        logger.error(f"Error starting bot name edit: {str(e)}")
        await callback_query.answer("❌ Произошла ошибка при редактировании бота")

@router_2.message(BotStates.admin_waiting_for_description)
async def process_bot_description(message: Message, state: FSMContext):
    try:
        logger.info(f"Processing bot description from user {message.from_user.id}")
        
        # Получаем сохраненные данные
        data = await state.get_data()
        if 'bot_url' not in data:
            logger.error("Bot URL not found in state")
            await message.answer(
                "❌ Ошибка: URL бота не найден.\n"
                "Начните сначала с команды /start"
            )
            await state.clear()
            return
        
        description = message.text.strip()
        if len(description) < 3:
            await message.answer(
                "❌ Описание слишком короткое. Минимум 3 символа.\n"
                "Попробуйте еще раз или нажмите /cancel для отмены"
            )
            return
        
        # Обновляем данные в состоянии
        await state.update_data(description=description)
        logger.info(f"Saved bot description in state: {description}")
        
        # Переходим к выбору категорий
        await state.set_state(BotStates.admin_waiting_for_categories)
        keyboard = await get_categories_for_selection()
        await message.answer(
            "✅ Описание принято!\n\n"
            "Выберите категории для бота:\n"
            "⬜️ - категория не выбрана\n"
            "☑️ - категория выбрана\n\n"
            "Нажмите на категорию, чтобы выбрать или отменить выбор.\n"
            "После выбора всех нужных категорий нажмите '✅ Готово'\n\n"
            "Нажмите /cancel для отмены",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in process_bot_description: {str(e)}")
        await message.answer(
            "❌ Произошла ошибка при обработке описания бота.\n"
            "Нажмите /start для возврата в главное меню"
        )
        await state.clear()

@router_2.callback_query(lambda c: c.data.startswith("edit_bot_categories_"))
async def edit_bot_categories(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if not await is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ У вас нет прав для выполнения этой команды.")
            return
            
        bot_id = callback_query.data.replace("edit_bot_categories_", "")
        bot = await db_2.Bots.find_one({"_id": ObjectId(bot_id)})
        
        if not bot:
            await callback_query.answer("❌ Бот не найден!")
            return
            
        # Сбрасываем все выбранные категории
        await db_2.Categories.update_many(
            {"selected": True},
            {"$set": {"selected": False}}
        )
        
        # Выбираем текущие категории бота
        await db_2.Categories.update_many(
            {"_id": {"$in": bot["categories"]}},
            {"$set": {"selected": True}}
        )
        
        await state.set_state(BotStates.admin_waiting_for_categories)
        await state.update_data(editing_bot_id=bot_id)
        
        keyboard = await get_categories_for_selection()
        await callback_query.message.edit_text(
            f"Выберите новые категории для бота {bot['name']}:\n\n"
            "Нажмите на категорию, чтобы выбрать или отменить выбор.\n"
            "После выбора нажмите '✅ Готово'\n\n"
            "Нажмите /cancel для отмены",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error starting bot categories edit: {str(e)}")
        await callback_query.answer("❌ Произошла ошибка при редактировании категорий")

async def get_categories_for_selection() -> InlineKeyboardMarkup:
    try:
        categories = await db_2.Categories.find().to_list(length=None)
        if not categories:
            return InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="➕ Добавить новую категорию",
                    callback_data="add_new_category"
                )]
            ])
        
        keyboard = []
        for category in categories:
            # Добавляем эмодзи для выбранных категорий
            prefix = "☑️ " if category.get('selected', False) else "⬜️ "
            keyboard.append([InlineKeyboardButton(
                text=f"{prefix} {category['name']}",
                callback_data=f"select_category_{category['_id']}"
            )])
            
        keyboard.append([InlineKeyboardButton(
            text="➕ Добавить новую категорию",
            callback_data="add_new_category"
        )])
        keyboard.append([InlineKeyboardButton(
            text="✅ Готово",
            callback_data="finish_categories"
        )])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    except Exception as e:
        logger.error(f"Error getting categories for selection: {str(e)}")
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="❌ Ошибка загрузки категорий",
                callback_data="error"
            )]
        ])

@router_2.callback_query(lambda c: c.data == "error")
async def handle_error(callback_query: types.CallbackQuery):
    await callback_query.answer("Произошла ошибка. Попробуйте позже.")

@router_2.callback_query(lambda c: c.data == "add_bot")
async def add_bot_start(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        await state.set_state(BotStates.waiting_for_bot_url)
        await callback_query.message.edit_text(
            "🤖 Добавление нового бота\n\n"
            "Пожалуйста, отправьте URL бота, которого хотите добавить.\n"
            "Формат: @username или https://t.me/username\n\n"
            "Нажмите /cancel для отмены"
        )
    except Exception as e:
        logger.error(f"Error in add_bot_start: {str(e)}")
        await callback_query.message.edit_text(
            "❌ Произошла ошибка.\n"
            "Нажмите /start для возврата в главное меню"
        )

@router_2.message(BotStates.waiting_for_bot_url)
async def process_bot_url(message: Message, state: FSMContext):
    try:
        logger.info(f"Processing bot URL from user {message.from_user.id}")
        bot_url = message.text.strip()
        
        # Проверяем формат URL
        if not (bot_url.startswith("@") or bot_url.startswith("https://t.me/")):
            await message.answer(
                "❌ Неверный формат URL. Используйте формат:\n"
                "@username или https://t.me/username\n\n"
                "Попробуйте еще раз или нажмите /cancel для отмены"
            )
            return
        
        # Проверяем, не существует ли уже такой бот
        username = bot_url.replace("@", "").replace("https://t.me/", "")
        existing_bot = await db_2.Bots.find_one({"username": username})
        if existing_bot:
            await message.answer(
                f"❌ Бот {bot_url} уже существует в базе данных!\n"
                "Попробуйте добавить другого бота или нажмите /cancel для отмены"
            )
            return
        
        # Сохраняем URL бота в состоянии
        await state.update_data(bot_url=bot_url)
        logger.info(f"Saved bot URL in state: {bot_url}")
        
        # Переходим к вводу описания
        await state.set_state(BotStates.admin_waiting_for_description)
        await message.answer(
            f"✅ URL бота принят: {bot_url}\n\n"
            f"Теперь введите описание для бота.\n"
            f"Это будет название, которое увидят пользователи.\n\n"
            f"Нажмите /cancel для отмены"
        )
    except Exception as e:
        logger.error(f"Error in process_bot_url: {str(e)}")
        await message.answer(
            "❌ Произошла ошибка при обработке URL бота.\n"
            "Нажмите /start для возврата в главное меню"
        )
        await state.clear()

@router_2.message(BotStates.admin_waiting_for_description)
async def process_bot_description(message: Message, state: FSMContext):
    try:
        logger.info(f"Processing bot description from user {message.from_user.id}")
        
        # Получаем сохраненные данные
        data = await state.get_data()
        if 'bot_url' not in data:
            logger.error("Bot URL not found in state")
            await message.answer(
                "❌ Ошибка: URL бота не найден.\n"
                "Начните сначала с команды /start"
            )
            await state.clear()
            return
        
        description = message.text.strip()
        if len(description) < 3:
            await message.answer(
                "❌ Описание слишком короткое. Минимум 3 символа.\n"
                "Попробуйте еще раз или нажмите /cancel для отмены"
            )
            return
        
        # Обновляем данные в состоянии
        await state.update_data(description=description)
        logger.info(f"Saved bot description in state: {description}")
        
        # Переходим к выбору категорий
        await state.set_state(BotStates.admin_waiting_for_categories)
        keyboard = await get_categories_for_selection()
        await message.answer(
            "✅ Описание принято!\n\n"
            "Выберите категории для бота:\n"
            "⬜️ - категория не выбрана\n"
            "☑️ - категория выбрана\n\n"
            "Нажмите на категорию, чтобы выбрать или отменить выбор.\n"
            "После выбора всех нужных категорий нажмите '✅ Готово'\n\n"
            "Нажмите /cancel для отмены",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in process_bot_description: {str(e)}")
        await message.answer(
            "❌ Произошла ошибка при обработке описания бота.\n"
            "Нажмите /start для возврата в главное меню"
        )
        await state.clear()

async def is_admin(user_id: int) -> bool:
    is_admin_user = str(user_id) == MY_ID
    logger.info(f"Checking admin rights for user {user_id}. MY_ID: {MY_ID}. Is admin: {is_admin_user}")
    return is_admin_user

@router_2.callback_query(lambda c: c.data == "add_bot")
async def add_bot_start(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        await state.set_state(BotStates.waiting_for_bot_url)
        await callback_query.message.edit_text(
            "🤖 Добавление нового бота\n\n"
            "Пожалуйста, отправьте URL бота, которого хотите добавить.\n"
            "Формат: @username или https://t.me/username\n\n"
            "Нажмите /cancel для отмены"
        )
    except Exception as e:
        logger.error(f"Error in add_bot_start: {str(e)}")
        await callback_query.message.edit_text(
            "❌ Произошла ошибка.\n"
            "Нажмите /start для возврата в главное меню"
        )

@router_2.message(BotStates.waiting_for_bot_url)
async def process_bot_url(message: Message, state: FSMContext):
    try:
        logger.info(f"Processing bot URL from user {message.from_user.id}")
        bot_url = message.text.strip()
        
        # Проверяем формат URL
        if not (bot_url.startswith("@") or bot_url.startswith("https://t.me/")):
            await message.answer(
                "❌ Неверный формат URL. Используйте формат:\n"
                "@username или https://t.me/username\n\n"
                "Попробуйте еще раз или нажмите /cancel для отмены"
            )
            return
        
        # Проверяем, не существует ли уже такой бот
        username = bot_url.replace("@", "").replace("https://t.me/", "")
        existing_bot = await db_2.Bots.find_one({"username": username})
        if existing_bot:
            await message.answer(
                f"❌ Бот {bot_url} уже существует в базе данных!\n"
                "Попробуйте добавить другого бота или нажмите /cancel для отмены"
            )
            return
        
        # Сохраняем URL бота в состоянии
        await state.update_data(bot_url=bot_url)
        logger.info(f"Saved bot URL in state: {bot_url}")
        
        # Переходим к вводу описания
        await state.set_state(BotStates.admin_waiting_for_description)
        await message.answer(
            f"✅ URL бота принят: {bot_url}\n\n"
            f"Теперь введите описание для бота.\n"
            f"Это будет название, которое увидят пользователи.\n\n"
            f"Нажмите /cancel для отмены"
        )
    except Exception as e:
        logger.error(f"Error in process_bot_url: {str(e)}")
        await message.answer(
            "❌ Произошла ошибка при обработке URL бота.\n"
            "Нажмите /start для возврата в главное меню"
        )
        await state.clear()

@router_2.message(BotStates.admin_waiting_for_description)
async def process_bot_description(message: Message, state: FSMContext):
    try:
        logger.info(f"Processing bot description from user {message.from_user.id}")
        
        # Получаем сохраненные данные
        data = await state.get_data()
        if 'bot_url' not in data:
            logger.error("Bot URL not found in state")
            await message.answer(
                "❌ Ошибка: URL бота не найден.\n"
                "Начните сначала с команды /start"
            )
            await state.clear()
            return
        
        description = message.text.strip()
        if len(description) < 3:
            await message.answer(
                "❌ Описание слишком короткое. Минимум 3 символа.\n"
                "Попробуйте еще раз или нажмите /cancel для отмены"
            )
            return
        
        # Обновляем данные в состоянии
        await state.update_data(description=description)
        logger.info(f"Saved bot description in state: {description}")
        
        # Переходим к выбору категорий
        await state.set_state(BotStates.admin_waiting_for_categories)
        keyboard = await get_categories_for_selection()
        await message.answer(
            "✅ Описание принято!\n\n"
            "Выберите категории для бота:\n"
            "⬜️ - категория не выбрана\n"
            "☑️ - категория выбрана\n\n"
            "Нажмите на категорию, чтобы выбрать или отменить выбор.\n"
            "После выбора всех нужных категорий нажмите '✅ Готово'\n\n"
            "Нажмите /cancel для отмены",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in process_bot_description: {str(e)}")
        await message.answer(
            "❌ Произошла ошибка при обработке описания бота.\n"
            "Нажмите /start для возврата в главное меню"
        )
        await state.clear()

@router_2.callback_query(lambda c: c.data == "finish_categories")
async def finish_categories_selection(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        # Получаем все сохраненные данные
        data = await state.get_data()
        logger.info(f"State data: {data}")
        
        if 'bot_url' not in data or 'description' not in data:
            logger.error("Missing required data in state")
            await callback_query.message.edit_text(
                "❌ Ошибка: не найдены данные о боте.\n"
                "Начните сначала с команды /start"
            )
            await state.clear()
            return
        
        selected_categories = await db_2.Categories.find({"selected": True}).to_list(length=None)
        
        if not selected_categories:
            await callback_query.message.edit_text(
                "❌ Выберите хотя бы одну категорию!\n"
                "Нажмите /cancel для отмены"
            )
            return
        
        bot_url = data['bot_url']
        description = data['description']
        category_ids = [cat['_id'] for cat in selected_categories]
        
        username = bot_url.replace("@", "").replace("https://t.me/", "")
        bot_data = {
            "username": username,
            "name": description,
            "url": f"https://t.me/{username}",
            "categories": category_ids,
            "is_approved": False,  # Бот ожидает подтверждения
            "added_by": callback_query.from_user.id  # Сохраняем ID пользователя, который добавил бота
        }
        
        # Добавляем бота
        result = await db_2.Bots.insert_one(bot_data)
        logger.info(f"Bot added successfully: {result.inserted_id}")
        
        # Сбрасываем флаги выбора категорий
        await db_2.Categories.update_many(
            {"selected": True},
            {"$set": {"selected": False}}
        )
        
        # Формируем сообщение с информацией о добавленном боте
        success_message = (
            f"✅ Бот добавлен и ожидает подтверждения!\n\n"
            f"🔗 URL: {bot_url}\n"
            f"📝 Описание: {description}\n"
            f"📂 Категории:\n"
        )
        for cat in selected_categories:
            success_message += f"  • {cat['name']}\n"
        
        # Создаем клавиатуру для пользователя
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="◀️ Вернуться в главное меню",
                callback_data="back_to_categories"
            )]
        ])
        
        # Отправляем сообщение пользователю
        await callback_query.message.edit_text(success_message, reply_markup=keyboard)
        
        # Отправляем уведомление администратору
        admin_message = (
            f"🆕 Новый бот добавлен и ожидает подтверждения!\n\n"
            f"🔗 URL: {bot_url}\n"
            f"📝 Описание: {description}\n"
            f"📂 Категории:\n"
        )
        for cat in selected_categories:
            admin_message += f"  • {cat['name']}\n"
        
        # Создаем клавиатуру для админа
        admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"approve_bot_{result.inserted_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject_bot_{result.inserted_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить описание",
                    callback_data=f"edit_bot_name_{result.inserted_id}"
                ),
                InlineKeyboardButton(
                    text="📂 Изменить категории",
                    callback_data=f"edit_bot_categories_{result.inserted_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Проверить бота",
                    url=f"https://t.me/{username}"
                )
            ]
        ])
        
        # Отправляем уведомление админу через bot_2
        try:
            await bot_2.send_message(
                chat_id=MY_ID,
                text=admin_message,
                reply_markup=admin_keyboard,
                parse_mode="HTML"
            )
            logger.info("Admin notification sent successfully")
        except Exception as e:
            logger.error(f"Error sending admin notification: {str(e)}")
            # Пробуем отправить через alert_2_me как запасной вариант
            await alert_2_me(admin_message, reply_markup=admin_keyboard)
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error adding bot: {str(e)}")
        error_message = f"❌ Ошибка при добавлении бота: {str(e)}"
        await callback_query.message.edit_text(error_message)
        await alert_2_me(f"❌ Ошибка при добавлении бота {bot_url}: {str(e)}")
        await state.clear()

async def get_bots_in_category(category_id: str) -> InlineKeyboardMarkup:
    try:
        # Проверяем существование категории
        try:
            category = await db_2.Categories.find_one({"_id": ObjectId(category_id)})
            logger.info(f"Getting bots for category: {category}")
        except Exception as e:
            logger.error(f"Error finding category: {str(e)}")
            return InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back_to_categories"
                )]
            ])
        
        if not category:
            return InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back_to_categories"
                )]
            ])
            
        # Получаем только подтвержденных ботов
        bots = await db_2.Bots.find({
            "categories": category_id,
            "is_approved": True
        }).to_list(length=None)
        logger.info(f"Found bots: {bots}")
        
        keyboard = []
        
        if not bots:
            keyboard.append([InlineKeyboardButton(
                text="Нет ботов в этой категории",
                callback_data="no_bots"
            )])
        else:
            for bot in bots:
                keyboard.append([InlineKeyboardButton(
                    text=bot["name"],
                    url=bot["url"]
                )])
                
        keyboard.append([InlineKeyboardButton(
            text="◀️ Назад",
            callback_data="back_to_categories"
        )])
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    except Exception as e:
        logger.error(f"Error getting bots in category: {str(e)}")
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="❌ Ошибка загрузки ботов",
                callback_data="error"
            )],
            [InlineKeyboardButton(
                text="◀️ Назад",
                callback_data="back_to_categories"
            )]
        ])  