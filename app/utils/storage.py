import boto3
from botocore.client import Config
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from flask import current_app
import uuid
import os

def get_s3_client():
    """Initializes and returns a boto3 client configured for Cloudflare R2."""
    try:
        account_id = current_app.config['R2_ACCOUNT_ID']
        access_key_id = current_app.config['R2_ACCESS_KEY_ID']
        secret_access_key = current_app.config['R2_SECRET_ACCESS_KEY']

        if not all([account_id, access_key_id, secret_access_key]):
            current_app.logger.error("R2 storage credentials are not fully configured.")
            return None

        endpoint_url = f'https://{account_id}.r2.cloudflarestorage.com'

        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(signature_version='s3v4')
        )
        return s3_client
    except (NoCredentialsError, PartialCredentialsError) as e:
        current_app.logger.error(f"Error initializing S3 client due to credentials issue: {e}")
        return None
    except Exception as e:
        current_app.logger.error(f"An unexpected error occurred while initializing S3 client: {e}")
        return None

def upload_file_to_r2(file_storage, folder='feedback'):
    """
    Uploads a file to the configured Cloudflare R2 bucket.

    :param file_storage: The FileStorage object from Flask's request.
    :param folder: The subfolder within the bucket to upload the file to.
    :return: The public URL of the uploaded file, or None if upload fails.
    """
    s3_client = get_s3_client()
    bucket_name = current_app.config.get('R2_BUCKET_NAME')
    public_url_base = current_app.config.get('R2_PUBLIC_URL_BASE')

    if not s3_client or not bucket_name or not public_url_base:
        current_app.logger.error("S3 client, bucket name, or public URL base is not configured. Cannot upload file.")
        return None

    # Generate a unique filename to prevent overwrites
    file_ext = os.path.splitext(file_storage.filename)[1]
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    object_name = f"{folder}/{unique_filename}"
    
    try:
        s3_client.upload_fileobj(
            file_storage,
            bucket_name,
            object_name,
            ExtraArgs={'ContentType': file_storage.content_type}
        )
        
        # Ensure the base URL doesn't have a trailing slash
        if public_url_base.endswith('/'):
            public_url_base = public_url_base[:-1]

        file_url = f"{public_url_base}/{object_name}"
        current_app.logger.info(f"Successfully uploaded {file_storage.filename} to {file_url}")
        return file_url

    except Exception as e:
        current_app.logger.error(f"Failed to upload {file_storage.filename} to R2. Error: {e}")
        return None
