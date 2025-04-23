import asyncio
import json
import websockets
from typing import Callable
import logging

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

WS_URL = 'wss://www.seismicportal.eu/standing_order/websocket'
RECONNECT_DELAY = 5  # Задержка перед повторным подключением в секундах

async def earthquake_listener(callback: Callable[[float, list, str], None]):
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=30, ping_timeout=10) as websocket:
                logger.info("✅ WebSocket подключён. Слушаем землетрясения...")
                
                while True:
                    try:
                        message = await websocket.recv()
                        data = json.loads(message)

                        if data.get("action") != "create":
                            continue

                        props = data["data"]["properties"]
                        coords = data["data"]["geometry"]["coordinates"]
                        magnitude = props.get("mag")
                        flynn_region = props.get("flynn_region")
                        
                        logger.info(f"🌍 Землетрясение M{magnitude} на {coords}")
                        await callback(magnitude, coords, flynn_region)

                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("⚠️ Соединение закрыто, пытаемся переподключиться...")
                        break
                    except json.JSONDecodeError as e:
                        logger.error(f"⚠️ Ошибка декодирования JSON: {e}")
                        continue
                    except Exception as e:
                        logger.error(f"⚠️ Ошибка при обработке сообщения: {e}")
                        continue

        except Exception as e:
            logger.error(f"⚠️ Ошибка подключения: {e}")
            logger.info(f"⏳ Ожидание {RECONNECT_DELAY} секунд перед повторным подключением...")
            await asyncio.sleep(RECONNECT_DELAY)