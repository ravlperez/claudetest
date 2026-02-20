"""
Cloudflare R2 (S3-compatible) client factory.

Required environment variables:
  R2_ACCOUNT_ID        – Cloudflare account ID (used to build endpoint URL)
  R2_ACCESS_KEY_ID     – R2 API token access key ID
  R2_SECRET_ACCESS_KEY – R2 API token secret access key
  R2_BUCKET_NAME       – target bucket name
  R2_PUBLIC_DOMAIN     – public base URL for stored objects
                         e.g. "https://pub-xxx.r2.dev" or a custom domain

Note on bucket configuration:
  - The bucket should have public listing DISABLED for security.
  - Public read access is granted only through the R2_PUBLIC_DOMAIN URL.
  - All uploads go through short-lived presigned PUT URLs (1 hour TTL).
"""

import os

import boto3
from botocore.client import Config


def get_r2_client():
    """Return a boto3 S3 client pointed at the Cloudflare R2 endpoint.

    Reads credentials from environment variables; raises KeyError if any
    required variable is absent (caught at the call site and converted to 503).
    """
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def get_bucket_name() -> str:
    """Return the R2 bucket name from the environment."""
    return os.environ["R2_BUCKET_NAME"]


def get_public_base_url() -> str:
    """Return the public base URL (no trailing slash) from the environment."""
    return os.environ["R2_PUBLIC_DOMAIN"].rstrip("/")
