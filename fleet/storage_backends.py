import logging
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage

logger = logging.getLogger(__name__)

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
    
    def _save(self, name, content):
        """
        Override _save to add error logging and ensure ACL is set.
        """
        try:
            logger.debug(f"Attempting to save file: {name} to S3 bucket: {self.bucket_name}")
            saved_name = super()._save(name, content)
            logger.info(f"Successfully saved file to S3: {saved_name}")
            return saved_name
        except Exception as e:
            logger.error(f"Failed to save file {name} to S3: {type(e).__name__}: {str(e)}")
            # Re-raise so Django can handle it properly
            raise
