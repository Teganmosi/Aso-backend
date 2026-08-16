import logging
import os
import uuid
from typing import Dict, Any
from django.conf import settings
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'video/mp4': 'mp4'
}

MAX_FILE_SIZES = {
    'image/jpeg': 10 * 1024 * 1024,   # 10 MB
    'image/png': 10 * 1024 * 1024,    # 10 MB
    'image/webp': 10 * 1024 * 1024,   # 10 MB
    'video/mp4': 50 * 1024 * 1024,    # 50 MB
}


def generate_presigned_upload_url(
    filename: str,
    file_type: str,
    vendor_id: str,
    product_id: str = None
) -> Dict[str, Any]:
    """
    Generates a presigned S3 / Cloudflare R2 upload URL for a vendor product asset.
    Validates MIME type against whitelist and applies vendor-scoped object key boundary.
    """
    if file_type not in ALLOWED_MIME_TYPES:
        allowed_str = ", ".join(ALLOWED_MIME_TYPES.keys())
        raise ValidationError({
            "file_type": f"Unsupported file type '{file_type}'. Allowed MIME types: {allowed_str}."
        })

    ext = ALLOWED_MIME_TYPES[file_type]
    unique_id = str(uuid.uuid4())

    if product_id:
        object_key = f"vendors/{vendor_id}/products/{product_id}/{unique_id}.{ext}"
    else:
        object_key = f"vendors/{vendor_id}/products/{unique_id}.{ext}"

    bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME') or os.getenv('AWS_S3_BUCKET_NAME') or 'aso-marketplace-media'
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    endpoint_url = os.getenv('AWS_S3_ENDPOINT_URL')  # Used for Cloudflare R2 or MinIO
    custom_domain = os.getenv('AWS_S3_CUSTOM_DOMAIN')

    if custom_domain:
        public_url = f"https://{custom_domain}/{object_key}"
    else:
        storage_base = getattr(settings, 'ASO_STORAGE_PUBLIC_BASE', 'https://cdn.aso.ng')
        public_url = f"{storage_base.rstrip('/')}/{object_key}"

    # Use boto3 if AWS credentials are configured
    if aws_access_key and aws_secret_key:
        try:
            import boto3
            from botocore.config import Config

            s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                endpoint_url=endpoint_url,
                config=Config(signature_version='s3v4')
            )

            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': object_key,
                    'ContentType': file_type
                },
                ExpiresIn=3600
            )

            return {
                "upload_url": presigned_url,
                "public_url": public_url,
                "object_key": object_key,
                "file_type": file_type,
                "max_size_bytes": MAX_FILE_SIZES.get(file_type, 10485760),
                "expires_in": 3600
            }
        except ImportError:
            # boto3 not installed -> fall back to the structured mock URL below
            logger.warning("boto3 is not installed; returning mock presigned upload URL for key '%s'", object_key)

    # Development / Testing mock presigned URL fallback
    mock_upload_url = f"https://storage.aso.ng/{bucket_name}/{object_key}?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=MOCKKEY%2F20260812%2Faso%2Fs3%2Faws4_request&X-Amz-Date=20260812T000000Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=mock_signature"

    return {
        "upload_url": mock_upload_url,
        "public_url": public_url,
        "object_key": object_key,
        "file_type": file_type,
        "max_size_bytes": MAX_FILE_SIZES.get(file_type, 10485760),
        "expires_in": 3600
    }
