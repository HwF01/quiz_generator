from pathlib import Path

from app.core.config import settings


def _upload_root() -> Path:
    return settings.data_dir / "uploads"


def _use_local() -> bool:
    return settings.is_local_stack


def ensure_bucket() -> None:
    if _use_local():
        _upload_root().mkdir(parents=True, exist_ok=True)
        return
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError

    client = boto3.client(
        "s3",
        endpoint_url=f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )
    try:
        client.head_bucket(Bucket=settings.minio_bucket)
    except ClientError:
        client.create_bucket(Bucket=settings.minio_bucket)


def upload_bytes(key: str, data: bytes, content_type: str) -> str:
    if _use_local():
        path = _upload_root() / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key
    ensure_bucket()
    import boto3
    from botocore.config import Config

    boto3.client(
        "s3",
        endpoint_url=f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    ).put_object(
        Bucket=settings.minio_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return key


def download_bytes(key: str) -> bytes:
    local = _upload_root() / key
    if local.exists():
        return local.read_bytes()
    import boto3
    from botocore.config import Config

    resp = boto3.client(
        "s3",
        endpoint_url=f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    ).get_object(Bucket=settings.minio_bucket, Key=key)
    return resp["Body"].read()
