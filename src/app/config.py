import os

# Used for signing session cookies (TASK 5+). Must be set to a strong random
# value in production (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`)
SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")

IS_PROD: bool = APP_ENV == "production"
