import os
import httpx
import logging
import json

# Настраиваем логгер
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CASDOOR_CLIENT_ID = os.getenv("CASDOOR_CLIENT_ID")
CASDOOR_CLIENT_SECRET = os.getenv("CASDOOR_CLIENT_SECRET")
# Внутри Docker сети используем имя сервиса
CASDOOR_INTERNAL_URL = "http://casdoor:8000"

# Важно: проверь в админке Casdoor, как называется твоя организация.
# По умолчанию это "built-in", но в коде у тебя стоит "users".
CASDOOR_ORGANIZATION = "users" 

async def sync_user_to_casdoor(user_data, provider_prefix):
    """Синхронизирует пользователя с Casdoor при входе через соцсети"""
    user_id = str(user_data.get("id"))
    full_name = user_data.get("name") or f"User {user_id}"
    casdoor_username = f"{provider_prefix}_{user_id}"
    
    # Формируем объект пользователя
    casdoor_user = {
        "owner": CASDOOR_ORGANIZATION, 
        "name": casdoor_username, 
        "displayName": full_name,
        "avatar": user_data.get("avatar", ""), 
        "email": user_data.get("email", ""),
        "phone": user_data.get("phone", ""), 
        "id": user_id, 
        "type": "normal-user",
        "properties": {"oauth_Source": provider_prefix}, 
        "signupApplication": "Myservice"
    }
    
    api_url_add = f"{CASDOOR_INTERNAL_URL}/api/add-user"
    api_url_update = f"{CASDOOR_INTERNAL_URL}/api/update-user"
    
    async with httpx.AsyncClient() as client:
        try:
            auth = (CASDOOR_CLIENT_ID, CASDOOR_CLIENT_SECRET)
            
            # 1. Попытка создать пользователя
            logger.info(f"Casdoor: Попытка создать пользователя {casdoor_username} в организации {CASDOOR_ORGANIZATION}")
            resp = await client.post(api_url_add, json=casdoor_user, auth=auth)
            
            resp_data = resp.json()
            logger.info(f"Casdoor Add Response: Code={resp.status_code}, Body={resp_data}")

            # Если статус не 'ok', значит что-то пошло не так (например, юзер уже есть)
            if resp.status_code != 200 or resp_data.get('status') != 'ok':
                logger.warning(f"Casdoor: Не удалось создать (возможно существует). Пробуем обновить. Причина: {resp_data.get('msg')}")
                
                # 2. Попытка обновить пользователя
                resp_upd = await client.post(api_url_update, json=casdoor_user, auth=auth)
                logger.info(f"Casdoor Update Response: Code={resp_upd.status_code}, Body={resp_upd.text}")
                
        except Exception as e:
            logger.error(f"Casdoor Sync Critical Error: {e}", exc_info=True)
            
    return casdoor_username

async def update_casdoor_balance(user_id, new_balance):
    """Обновляет баланс пользователя в Casdoor"""
    full_id = f"{CASDOOR_ORGANIZATION}/{user_id}"
    auth = (CASDOOR_CLIENT_ID, CASDOOR_CLIENT_SECRET)
    
    async with httpx.AsyncClient() as client:
        try:
            # Сначала получаем текущего юзера
            resp = await client.get(f"{CASDOOR_INTERNAL_URL}/api/get-user?id={full_id}", auth=auth)
            if resp.status_code != 200:
                logger.error(f"Casdoor Balance: Не найден юзер {full_id}")
                return
            
            user_data = resp.json().get('data')
            if not user_data: return
            
            user_data['balance'] = float(new_balance)
            user_data['balanceCurrency'] = "RUB"
            
            await client.post(f"{CASDOOR_INTERNAL_URL}/api/update-user?id={full_id}", json=user_data, auth=auth)
        except Exception as e:
            logger.error(f"Casdoor Balance Update Error: {e}")