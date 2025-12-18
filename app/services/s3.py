import boto3
import boto3
import os
import uuid

# Получаем настройки из переменных окружения (которые в .env)
ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
SECRET_KEY = os.getenv("S3_SECRET_KEY")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
REGION_NAME = os.getenv("S3_REGION_NAME", "ru-1")

def get_s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        endpoint_url=ENDPOINT_URL,
        region_name=REGION_NAME
    )

async def upload_file_to_s3(file_bytes, filename: str, content_type: str) -> str:
    """
    Загружает файл в Selectel S3 и возвращает публичную ссылку.
    """
    if not ACCESS_KEY or not SECRET_KEY:
        print("Ошибка: Нет ключей S3 в .env")
        return None

    s3 = get_s3_client()
    
    # Генерируем уникальное имя файла, чтобы не затереть другие (uuid)
    unique_filename = f"{uuid.uuid4()}-{filename}"
    
    try:
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=unique_filename,
            Body=file_bytes,
            ContentType=content_type
        )
        
        # Формируем прямую ссылку на файл
        url = f"{ENDPOINT_URL}/{BUCKET_NAME}/{unique_filename}"
        return url
        
    except Exception as e:
        print(f"S3 Upload Error: {e}")
        return None