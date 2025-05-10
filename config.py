import os
from dotenv import load_dotenv
from typing import List, Optional, Dict, Any
import logging

# Initialize environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_cookies(cookies: str) -> str:
    """Validate and sanitize cookie strings."""
    if not cookies or cookies.strip().startswith("#"):
        return ""
    return cookies.strip()

def get_owner_ids() -> List[int]:
    """Safely parse owner IDs from environment."""
    try:
        owner_ids = os.getenv("OWNER_ID", "")
        return list(map(int, filter(None, owner_ids.split()))) if owner_ids else []
    except ValueError as e:
        logger.error(f"Invalid OWNER_ID format: {e}")
        return []

# Cookie configurations (with validation)
INST_COOKIES = validate_cookies("""
# write up here insta cookies
""")

YTUB_COOKIES = validate_cookies("""
# write here yt cookies
""")

# Required configurations
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("Missing required environment variables: API_ID, API_HASH, or BOT_TOKEN")
    raise ValueError("Essential configuration missing")

# Database configuration
MONGO_DB = os.getenv("MONGO_DB", "")
DB_NAME = os.getenv("DB_NAME", "telegram_downloader")

# Security configurations
def validate_key(key: str, default: str, min_length: int = 8) -> str:
    """Validate cryptographic keys."""
    if len(default) < min_length:
        logger.warning(f"Default {key} is too short (min {min_length} chars)")
    return os.getenv(key, default)

MASTER_KEY = validate_key("MASTER_KEY", "gK8HzLfT9QpViJcYeB5wRa3DmN7P2xUq", 32)
IV_KEY = validate_key("IV_KEY", "s7Yx5CpVmE3F", 12)

# Optional configurations
STRING: Optional[str] = os.getenv("STRING")  # optional session string
OWNER_ID: List[int] = get_owner_ids()
LOG_GROUP: int = int(os.getenv("LOG_GROUP", "-1001234456"))  # optional with -100
FORCE_SUB: int = int(os.getenv("FORCE_SUB", "-10012345567"))  # optional with -100

# Cookie configurations from environment with fallback
YT_COOKIES: str = validate_cookies(os.getenv("YT_COOKIES", YTUB_COOKIES))
INSTA_COOKIES: str = validate_cookies(os.getenv("INSTA_COOKIES", INST_COOKIES))

# Premium limits
FREEMIUM_LIMIT: int = max(0, int(os.getenv("FREEMIUM_LIMIT", "0")))  # minimum 0
PREMIUM_LIMIT: int = max(10, int(os.getenv("PREMIUM_LIMIT", "500")))  # minimum 10

# Validate critical configurations
if not MONGO_DB and DB_NAME == "telegram_downloader":
    logger.warning("Using default database name without MongoDB connection string")

# Security warning for default crypto keys
if MASTER_KEY == "gK8HzLfT9QpViJcYeB5wRa3DmN7P2xUq":
    logger.warning("Using default MASTER_KEY - please change this in production!")
if IV_KEY == "s7Yx5CpVmE3F":
    logger.warning("Using default IV_KEY - please change this in production!")