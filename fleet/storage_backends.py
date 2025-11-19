import logging
import sys
from django.conf import settings
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
        """Initialize and log configuration."""
        super().__init__(*args, **kwargs)
        print(f"[S3 INIT] Storage initialized - Bucket: {self.bucket_name}, ACL: {self.default_acl}", file=sys.stderr, flush=True)
    
    def _save(self, name, content):
        """
        Override _save to add error logging and ensure ACL is set.
        """
        # Force flush to ensure logs appear immediately
        print(f"[S3 UPLOAD] ===== STARTING UPLOAD =====", file=sys.stderr, flush=True)
        print(f"[S3 UPLOAD] File: {name}", file=sys.stderr, flush=True)
        print(f"[S3 UPLOAD] Bucket: {self.bucket_name}", file=sys.stderr, flush=True)
        print(f"[S3 UPLOAD] ACL: {self.default_acl}", file=sys.stderr, flush=True)
        print(f"[S3 UPLOAD] USE_S3: {getattr(settings, 'USE_S3', False)}", file=sys.stderr, flush=True)
        
        try:
            logger.info(f"Attempting to save file: {name} to S3 bucket: {self.bucket_name}")
            
            # Call parent _save
            saved_name = super()._save(name, content)
            
            print(f"[S3 UPLOAD] ✅ SUCCESS! Saved as: {saved_name}", file=sys.stderr, flush=True)
            logger.info(f"Successfully saved file to S3: {saved_name}")
            return saved_name
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', 'No message')
            
            # Print detailed error to stderr (visible in Render logs)
            print(f"[S3 UPLOAD] ❌❌❌ CLIENT ERROR ❌❌❌", file=sys.stderr, flush=True)
            print(f"[S3 UPLOAD] Error Code: {error_code}", file=sys.stderr, flush=True)
            print(f"[S3 UPLOAD] Error Message: {error_message}", file=sys.stderr, flush=True)
            print(f"[S3 UPLOAD] File: {name}", file=sys.stderr, flush=True)
            print(f"[S3 UPLOAD] Bucket: {self.bucket_name}", file=sys.stderr, flush=True)
            print(f"[S3 UPLOAD] Full Response: {e.response}", file=sys.stderr, flush=True)
            
            logger.error(f"Failed to save file {name} to S3: {error_code} - {error_message}")
            # Re-raise so Django can handle it properly
            raise
            
        except Exception as e:
            print(f"[S3 UPLOAD] ❌❌❌ UNEXPECTED ERROR ❌❌❌", file=sys.stderr, flush=True)
            print(f"[S3 UPLOAD] Type: {type(e).__name__}", file=sys.stderr, flush=True)
            print(f"[S3 UPLOAD] Message: {str(e)}", file=sys.stderr, flush=True)
            logger.error(f"Failed to save file {name} to S3: {type(e).__name__}: {str(e)}")
            import traceback
            print("[S3 UPLOAD] Traceback:", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            # Re-raise so Django can handle it properly
            raise
