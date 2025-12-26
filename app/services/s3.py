import boto3
import os
import uuid
import httpx
import logging

logger = logging.getLogger(__name__)

ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
SECRET_KEY = os.getenv("S3_SECRET_KEY")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
REGION_NAME = os.getenv("S3_REGION_NAME", "ru-1")
# Читаем публичный домен из настроек
S3_PUBLIC_DOMAIN = os.getenv("S3_PUBLIC_DOMAIN")

def get_s3_client():
    if not ACCESS_KEY or not SECRET_KEY: return None
    return boto3.client(
        's3', 
        aws_access_key_id=ACCESS_KEY, 
        aws_secret_access_key=SECRET_KEY,
        endpoint_url=ENDPOINT_URL, 
        region_name=REGION_NAME
    )

async def upload_file_to_s3(file_bytes, filename: str, content_type: str) -> str:
    s3 = get_s3_client()
    if not s3: return None
    
    # Чистка расширения файла
    _, ext = os.path.splitext(filename)
    if not ext:
        if "jpeg" in content_type or "jpg" in content_type: ext = ".jpg"
        elif "png" in content_type: ext = ".png"
        elif "webp" in content_type: ext = ".webp"
        elif "mp4" in content_type: ext = ".mp4"
        else: ext = ".bin"
        
    unique_filename = f"{uuid.uuid4()}{ext}"
    
    try:
        # Для Selectel важно явно указать ContentType
        extra_args = {'ContentType': content_type}
        
        s3.put_object(
            Bucket=BUCKET_NAME, 
            Key=unique_filename, 
            Body=file_bytes, 
            **extra_args
        )
        
        # === ГЛАВНОЕ ИСПРАВЛЕНИЕ ===
        # Если есть публичный домен, используем его для ссылки
        if S3_PUBLIC_DOMAIN:
            clean_domain = S3_PUBLIC_DOMAIN.rstrip('/')
            return f"{clean_domain}/{unique_filename}"
        else:
            # Иначе старый вариант (который у тебя ломался)
            return f"{ENDPOINT_URL}/{BUCKET_NAME}/{unique_filename}"

    except Exception as e:
        logger.error(f"S3 Upload Error: {e}")
        return None

async def upload_url_to_s3(url: str) -> str:
    if not url: return None
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            resp = await client.get(url, timeout=60.0)
            if resp.status_code != 200: return None
            file_bytes = resp.content
            
            ctype = resp.headers.get("content-type", "")
            ext = ".png"
            if "video" in ctype or ".mp4" in url: 
                ext = ".mp4"
                ctype = "video/mp4"
            elif "jpeg" in ctype or ".jpg" in url: 
                ext = ".jpg"
            elif "webp" in ctype: 
                ext = ".webp"

        filename = f"ai-gen-{uuid.uuid4()}{ext}"
        return await upload_file_to_s3(file_bytes, filename, ctype or "application/octet-stream")
    except Exception as e:
        logger.error(f"URL Upload Error: {e}")
        return None