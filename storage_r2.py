"""
Módulo de almacenamiento de imágenes en Cloudflare R2.
Sube archivos y devuelve URLs públicas, en vez de guardar base64 en la base de datos.
"""
import os
import re
import base64
import uuid
import boto3
from botocore.client import Config

R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "riai-fotos")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "")  # opcional: dominio público custom

_client = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _client


def upload_base64_image(img_b64, prefix="img"):
    """
    Recibe una imagen en base64 (data:image/...;base64,XXXX) y la sube a R2.
    Devuelve la URL pública, o None si falla o si img_b64 está vacío.
    """
    if not img_b64 or len(img_b64) < 20:
        return None

    match = re.search(r'base64,(.*)', img_b64)
    raw_b64 = match.group(1) if match else img_b64

    ext = "jpg"
    if "image/png" in img_b64[:30]:
        ext = "png"
    elif "image/webp" in img_b64[:30]:
        ext = "webp"

    try:
        img_bytes = base64.b64decode(raw_b64)
    except Exception:
        return None

    key = f"{prefix}/{uuid.uuid4().hex}.{ext}"
    content_type = f"image/{ext if ext != 'jpg' else 'jpeg'}"

    client = get_client()
    client.put_object(
        Bucket=R2_BUCKET,
        Key=key,
        Body=img_bytes,
        ContentType=content_type,
    )

    if R2_PUBLIC_URL:
        return f"{R2_PUBLIC_URL.rstrip('/')}/{key}"
    # URL firmada de larga duración como fallback si no hay dominio público configurado
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": R2_BUCKET, "Key": key},
        ExpiresIn=60 * 60 * 24 * 365 * 5,  # ~5 años
    )


def delete_image(url):
    """Borra una imagen de R2 a partir de su URL (best-effort, no lanza excepción si falla)."""
    if not url or R2_BUCKET not in url and not R2_PUBLIC_URL:
        return
    try:
        # Extraer la key desde la URL
        key = url.split(f"{R2_BUCKET}/")[-1].split("?")[0]
        client = get_client()
        client.delete_object(Bucket=R2_BUCKET, Key=key)
    except Exception as e:
        print(f"No se pudo borrar imagen de R2: {e}", flush=True)
