from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage

class PublicMediaStorage(S3Boto3Storage):
    """
    Custom S3 storage backend for public media files.
    Uses settings from Django settings (AWS_STORAGE_BUCKET_NAME, AWS_S3_REGION_NAME).
    """
    default_acl = "public-read"
    file_overwrite = False
    
    @property
    def bucket_name(self):
        """Get bucket name from settings."""
        return getattr(settings, "AWS_STORAGE_BUCKET_NAME", "macnova-machinery-media")
    
    @property
    def custom_domain(self):
        """Dynamically construct custom domain from settings."""
        bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "macnova-machinery-media")
        region = getattr(settings, "AWS_S3_REGION_NAME", "us-east-2")
        return f"{bucket}.s3.{region}.amazonaws.com"
