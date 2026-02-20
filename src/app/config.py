import os

from dotenv import load_dotenv

# Load .env for local development (no-op if the file doesn't exist or in prod
# where vars are injected directly into the environment by the platform).
load_dotenv()

# Runtime environment: "development" | "production"
APP_ENV: str = os.getenv("APP_ENV", "development")

# Used for signing session cookies (TASK 5+). Must be set to a strong random
# value in production (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`)
SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")

IS_PROD: bool = APP_ENV == "production"
