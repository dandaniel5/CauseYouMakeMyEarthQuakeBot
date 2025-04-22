import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from ws_client import earthquake_listener

@pytest.mark.asyncio
async def test_earthquake_listener_basic():
    # Создаем мок для websockets
    mock_websocket = AsyncMock()
    mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
    mock_websocket.__aexit__ = AsyncMock()
    
    # Создаем тестовые данные
    test_data = {
        "action": "create",
        "data": {
            "properties": {
                "mag": 5.5,
                "flynn_region": "Тестовый регион"
            },
            "geometry": {
                "coordinates": [40.0, 45.0]
            }
        }
    }
    
    # Настраиваем recv для возврата JSON строки
    mock_websocket.recv = AsyncMock(return_value=json.dumps(test_data))

    # Создаем мок для callback функции
    mock_callback = AsyncMock()

    # Патчим websockets.connect
    with patch('websockets.connect', return_value=mock_websocket):
        # Запускаем слушатель в фоновом режиме
        task = asyncio.create_task(earthquake_listener(mock_callback))
        
        # Даем время на обработку
        await asyncio.sleep(0.1)
        
        # Проверяем, что callback был вызван с правильными параметрами
        mock_callback.assert_called_once_with(5.5, [40.0, 45.0], "Тестовый регион")
        
        # Отменяем задачу
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

@pytest.mark.asyncio
async def test_earthquake_listener_invalid_data():
    # Тест с некорректными данными
    mock_websocket = AsyncMock()
    mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
    mock_websocket.__aexit__ = AsyncMock()
    
    test_data = {
        "action": "update",  # Неправильное действие
        "data": {}
    }
    
    mock_websocket.recv = AsyncMock(return_value=json.dumps(test_data))

    mock_callback = AsyncMock()

    with patch('websockets.connect', return_value=mock_websocket):
        task = asyncio.create_task(earthquake_listener(mock_callback))
        await asyncio.sleep(0.1)
        
        # Проверяем, что callback не был вызван
        mock_callback.assert_not_called()
        
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

@pytest.mark.asyncio
async def test_earthquake_listener_error_handling():
    # Тест обработки ошибок
    mock_websocket = AsyncMock()
    mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
    mock_websocket.__aexit__ = AsyncMock()
    
    mock_websocket.recv = AsyncMock(side_effect=Exception("Тестовая ошибка"))

    mock_callback = AsyncMock()

    with patch('websockets.connect', return_value=mock_websocket):
        task = asyncio.create_task(earthquake_listener(mock_callback))
        await asyncio.sleep(0.1)
        
        # Проверяем, что callback не был вызван
        mock_callback.assert_not_called()
        
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

@pytest.mark.asyncio
async def test_earthquake_listener_multiple_events():
    # Тест множественных событий
    mock_websocket = AsyncMock()
    mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
    mock_websocket.__aexit__ = AsyncMock()
    
    # Создаем список тестовых данных
    test_data_list = [
        {
            "action": "create",
            "data": {
                "properties": {
                    "mag": 5.5,
                    "flynn_region": "Регион 1"
                },
                "geometry": {
                    "coordinates": [40.0, 45.0]
                }
            }
        },
        {
            "action": "create",
            "data": {
                "properties": {
                    "mag": 6.0,
                    "flynn_region": "Регион 2"
                },
                "geometry": {
                    "coordinates": [41.0, 46.0]
                }
            }
        }
    ]
    
    # Преобразуем данные в JSON строки
    json_responses = [json.dumps(data) for data in test_data_list]
    
    # Настраиваем recv для возврата последовательности JSON строк
    mock_websocket.recv = AsyncMock(side_effect=json_responses)

    mock_callback = AsyncMock()

    with patch('websockets.connect', return_value=mock_websocket):
        task = asyncio.create_task(earthquake_listener(mock_callback))
        await asyncio.sleep(0.1)
        
        # Проверяем, что callback был вызван дважды с правильными параметрами
        assert mock_callback.call_count == 2
        mock_callback.assert_any_call(5.5, [40.0, 45.0], "Регион 1")
        mock_callback.assert_any_call(6.0, [41.0, 46.0], "Регион 2")
        
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass 