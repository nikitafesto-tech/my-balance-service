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
    unique_filename = f"{uuid.uuid4()}-{filename}"
    try:
        s3.put_object(Bucket=BUCKET_NAME, Key=unique_filename, Body=file_bytes, ContentType=content_type)
        return f"{ENDPOINT_URL}/{BUCKET_NAME}/{unique_filename}"
    except Exception as e:
        print(f"S3 Error: {e}")
        return None

async def upload_url_to_s3(url: str) -> str:
    """Умная загрузка: определяет картинка это или видео"""
    if not url: return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=60.0) # Увеличенный таймаут для видео
            if resp.status_code != 200: return None
            file_bytes = resp.content
            
            # Определяем тип контента
            ctype = resp.headers.get("content-type", "")
            ext = ".png"
            if "video" in ctype: ext = ".mp4"
            elif "jpeg" in ctype: ext = ".jpg"
            elif "webp" in ctype: ext = ".webp"

        filename = f"ai-gen-{uuid.uuid4()}{ext}"
        return await upload_file_to_s3(file_bytes, filename, ctype or "application/octet-stream")
    except Exception as e:
        print(f"URL Upload Error: {e}")
        return None