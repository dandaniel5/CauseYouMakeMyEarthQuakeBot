import asyncio
import json
import websockets
from typing import Callable

WS_URL = 'wss://www.seismicportal.eu/standing_order/websocket'


async def earthquake_listener(callback: Callable[[float, list], None]):
    async with websockets.connect(WS_URL, ping_interval=None) as websocket:
        print("✅ WebSocket подключён. Слушаем землетрясения...")
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
                
                print(f"🌍 Землетрясение M{magnitude} на {coords}")
                # asyncio.create_task(callback(magnitude, coords, flynn_region))
                asyncio.create_task(callback(10, coords, flynn_region))

            except Exception as e:
                print(f"⚠️ Ошибка: {e}")
                await asyncio.sleep(5)