# S3 Upload Debugging Guide

## Issue: AccessDenied Error on Render

If you're getting `AccessDenied` errors when uploading files from the admin or usage form, check the following:

## 1. IAM User Permissions

The IAM user (`macnova-file-uploader`) needs these permissions on the bucket:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::macnova-machinery-media",
                "arn:aws:s3:::macnova-machinery-media/*"
            ]
        }
    ]
}
```

**Critical:** `s3:PutObjectAcl` is required because we're setting `ACL=public-read` on uploads.

## 2. Render Environment Variables

Verify these are set correctly in Render dashboard:

- `USE_S3=True` (must be exactly "True", not "true" or "TRUE")
- `AWS_ACCESS_KEY_ID` (your access key)
- `AWS_SECRET_ACCESS_KEY` (your secret key - no quotes!)
- `AWS_STORAGE_BUCKET_NAME=macnova-machinery-media` (optional, has default)
- `AWS_S3_REGION_NAME=us-east-2` (optional, has default)

## 3. Bucket Policy

The bucket should allow public reads (for viewing images):

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowPublicRead",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::macnova-machinery-media/*"
        }
    ]
}
```

## 4. Check Render Logs

In Render dashboard, check the logs when you try to upload. Look for:
- Any error messages about S3
- Whether USE_S3 is being read correctly
- Any boto3/botocore errors

## 5. Test from Render Shell

You can test S3 from Render's shell:

```bash
python manage.py shell
```

Then run:
```python
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings

print(f"USE_S3: {settings.USE_S3}")
print(f"Storage: {default_storage.__class__}")
print(f"Bucket: {settings.AWS_STORAGE_BUCKET_NAME}")

# Test upload
test_file = ContentFile(b"test", name="test.txt")
saved = default_storage.save("test.txt", test_file)
print(f"Saved: {saved}")
print(f"URL: {default_storage.url(saved)}")
```

## Common Issues

1. **Secret key has quotes**: Make sure `AWS_SECRET_ACCESS_KEY` in Render doesn't have quotes around it
2. **USE_S3 not set**: Must be exactly "True" (case-sensitive)
3. **Missing PutObjectAcl permission**: This is the most common cause of AccessDenied
4. **Wrong bucket name**: Verify the bucket name matches exactly

## Fixed Issues

✅ Storage backend simplified to use django-storages defaults
✅ Settings properly read from environment variables
✅ ACL set to "public-read" for public access
✅ Local testing works correctly
