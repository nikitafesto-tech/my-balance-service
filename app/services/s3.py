import boto3
import os
import uuid
import httpx

ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
SECRET_KEY = os.getenv("S3_SECRET_KEY")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
REGION_NAME = os.getenv("S3_REGION_NAME", "ru-1")

def get_s3_client():
    if not ACCESS_KEY or not SECRET_KEY: return None
    return boto3.client(
        's3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
        endpoint_url=ENDPOINT_URL, region_name=REGION_NAME
    )

async def upload_file_to_s3(file_bytes, filename: str, content_type: str) -> str:
    s3 = get_s3_client()
    if not s3: return None
    
    # === ИСПРАВЛЕНИЕ ОШИБКИ 400 ===
    # Мы полностью убираем оригинальное имя файла (где могут быть пробелы и скобки)
    # и оставляем только расширение.
    _, ext = os.path.splitext(filename)
    if not ext:
        # Пытаемся угадать расширение, если его нет
        if "jpeg" in content_type or "jpg" in content_type: ext = ".jpg"
        elif "png" in content_type: ext = ".png"
        elif "webp" in content_type: ext = ".webp"
        elif "mp4" in content_type: ext = ".mp4"
        else: ext = ".bin"
        
    unique_filename = f"{uuid.uuid4()}{ext}"
    # ==============================
    
    try:
        s3.put_object(Bucket=BUCKET_NAME, Key=unique_filename, Body=file_bytes, ContentType=content_type)
        return f"{ENDPOINT_URL}/{BUCKET_NAME}/{unique_filename}"
    except Exception as e:
        print(f"S3 Error: {e}")
        return None

async def upload_url_to_s3(url: str) -> str:
    """Скачивает файл по ссылке и заливает в S3 с чистым именем."""
    if not url: return None
    try:
        async with httpx.AsyncClient() as client:
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
        print(f"URL Upload Error: {e}")
        return None