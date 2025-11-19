import logging
from storages.backends.s3boto3 import S3Boto3Storage
from botocore.exceptions import ClientError

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
    
    def __init__(self, *args, **kwargs):
        """Initialize storage backend."""
        super().__init__(*args, **kwargs)
    
    def _save(self, name, content):
        """
        Override _save to add error logging and ensure ACL is set.
        """
        try:
            # Call parent _save
            saved_name = super()._save(name, content)
            logger.info(f"Successfully saved file to S3: {saved_name}")
            return saved_name
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', 'No message')
            
            # Log detailed error (visible in production logs)
            logger.error(
                f"Failed to save file {name} to S3 bucket {self.bucket_name}: "
                f"{error_code} - {error_message}"
            )
            # Re-raise so Django can handle it properly
            raise
            
        except Exception as e:
            logger.error(
                f"Unexpected error saving file {name} to S3: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            # Re-raise so Django can handle it properly
            raise
