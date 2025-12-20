import boto3
import os
import uuid
import httpx

# Получаем настройки из переменных окружения
ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
SECRET_KEY = os.getenv("S3_SECRET_KEY")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
REGION_NAME = os.getenv("S3_REGION_NAME", "ru-1")

def get_s3_client():
    if not ACCESS_KEY or not SECRET_KEY:
        return None
    return boto3.client(
        's3',
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        endpoint_url=ENDPOINT_URL,
        region_name=REGION_NAME
    )

async def upload_file_to_s3(file_bytes, filename: str, content_type: str) -> str:
    """Загружает файл в Selectel S3 и возвращает публичную ссылку."""
    s3 = get_s3_client()
    if not s3: return None
    
    unique_filename = f"{uuid.uuid4()}-{filename}"
    
    try:
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=unique_filename,
            Body=file_bytes,
            ContentType=content_type
        )
        return f"{ENDPOINT_URL}/{BUCKET_NAME}/{unique_filename}"
    except Exception as e:
        print(f"S3 Upload Error: {e}")
        return None

async def upload_url_to_s3(image_url: str) -> str:
    """Скачивает картинку по ссылке (от нейросети) и заливает в наш S3."""
    if not image_url: return None
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(image_url, timeout=30.0)
            if resp.status_code != 200:
                print(f"Ошибка скачивания URL: {resp.status_code}")
                return None
            file_bytes = resp.content

        filename = f"ai-gen-{uuid.uuid4()}.png"
        return await upload_file_to_s3(file_bytes, filename, "image/png")
        
    except Exception as e:
        print(f"Ошибка перезаливки URL в S3: {e}")
        return None