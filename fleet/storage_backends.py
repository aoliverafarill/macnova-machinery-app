from storages.backends.s3boto3 import S3Boto3Storage

class PublicMediaStorage(S3Boto3Storage):
    bucket_name = "macnova-machinery-media"
    default_acl = "public-read"
    file_overwrite = False
    custom_domain = "macnova-machinery-media.s3.us-east-2.amazonaws.com"
