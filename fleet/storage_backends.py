from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage

class PublicMediaStorage(S3Boto3Storage):
    """
    Custom S3 storage backend for public media files.
    django-storages automatically uses AWS_STORAGE_BUCKET_NAME and AWS_S3_REGION_NAME from settings.
    """
    # ACL settings - files will be publicly readable
    default_acl = "public-read"
    file_overwrite = False
    
    # Custom domain is set in settings.py as AWS_S3_CUSTOM_DOMAIN
    # django-storages will use it automatically if present
