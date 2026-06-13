import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/transactions")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
UPLOAD_DIR = "/app/uploads"
