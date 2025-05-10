import concurrent.futures
import time
import os
import re
import cv2
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, Union
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_DB as MONGO_URI, DB_NAME

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
PUBLIC_LINK_PATTERN = re.compile(r'(https?://)?(t\.me|telegram\.me)/([^/]+)(/(\d+))?')
PRIVATE_LINK_PATTERN = re.compile(r'(https?://)?(t\.me|telegram\.me)/c/(\d+)(/(\d+))?')
VIDEO_EXTENSIONS = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "mpeg", "mpg", "3gp"}
DEFAULT_VIDEO_METADATA = {'width': 1, 'height': 1, 'duration': 1}

# Database setup
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client[DB_NAME]
users_collection = db["users"]
premium_users_collection = db["premium_users"]
statistics_collection = db["statistics"]
codedb = db["redeem_code"]

# Session encoder constants (kept as-is for compatibility)
a1 = "c2F2ZV9yZXN0cmljdGVkX2NvbnRlbnRfYm90cw=="
a2 = "Nzk2"
a3 = "Z2V0X21lc3NhZ2Vz" 
# ... [rest of encoded constants remain unchanged]

def is_private_link(link: str) -> bool:
    """Check if a Telegram link is for a private channel."""
    return bool(PRIVATE_LINK_PATTERN.match(link))

def thumbnail(sender: str) -> Optional[str]:
    """Get thumbnail path if exists."""
    thumb_path = f'{sender}.jpg'
    return thumb_path if os.path.exists(thumb_path) else None

def hhmmss(seconds: int) -> str:
    """Convert seconds to HH:MM:SS format."""
    return time.strftime('%H:%M:%S', time.gmtime(seconds))

def parse_telegram_link(link: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    Parse Telegram link into components.
    Returns: (channel_id/username, message_id, link_type)
    """
    private_match = PRIVATE_LINK_PATTERN.match(link)
    public_match = PUBLIC_LINK_PATTERN.match(link)
    
    if private_match:
        return f'-100{private_match.group(3)}', int(private_match.group(5)), 'private'
    elif public_match:
        return public_match.group(3), int(public_match.group(5)), 'public'
    return None, None, None

# Alias for backward compatibility
E = parse_telegram_link

def get_display_name(user) -> str:
    """Get user's display name from Telegram user object."""
    name_parts = []
    if user.first_name:
        name_parts.append(user.first_name)
    if user.last_name:
        name_parts.append(user.last_name)
    
    if name_parts:
        return ' '.join(name_parts)
    return user.username or "Unknown User"

def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing invalid characters."""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def get_dummy_filename(file_info: Dict[str, str]) -> str:
    """Generate a dummy filename based on file type."""
    extension_map = {
        "video": "mp4",
        "photo": "jpg",
        "document": "pdf",
        "audio": "mp3"
    }
    ext = extension_map.get(file_info.get("type", "file"), "bin")
    return f"downloaded_file_{int(time.time())}.{ext}"

async def save_user_data(
    user_id: int, 
    key: str, 
    value: Any, 
    collection: AsyncIOMotorClient = users_collection
) -> bool:
    """Save user data to MongoDB with error handling."""
    try:
        await collection.update_one(
            {"user_id": user_id},
            {"$set": {key: value, "updated_at": datetime.now()}},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error(f"Error saving data for user {user_id}: {e}", exc_info=True)
        return False

async def get_user_data(
    user_id: int, 
    collection: AsyncIOMotorClient = users_collection
) -> Optional[Dict]:
    """Retrieve all data for a user."""
    try:
        return await collection.find_one({"user_id": user_id})
    except Exception as e:
        logger.error(f"Error getting data for user {user_id}: {e}")
        return None

async def process_text_with_rules(user_id: int, text: str) -> str:
    """Process text according to user's replacement and deletion rules."""
    if not text:
        return ""
    
    try:
        replacements = await get_user_data_key(user_id, "replacement_words", {})
        delete_words = await get_user_data_key(user_id, "delete_words", [])
        
        # Apply replacements
        processed_text = text
        for word, replacement in replacements.items():
            processed_text = processed_text.replace(word, replacement)
        
        # Apply deletions
        if delete_words:
            words = processed_text.split()
            processed_text = " ".join(w for w in words if w not in delete_words)
        
        return processed_text
    except Exception as e:
        logger.error(f"Error processing text: {e}")
        return text

async def screenshot(video_path: str, duration: int, sender: str) -> Optional[str]:
    """Generate screenshot from video at midpoint."""
    if (existing := thumbnail(sender)):
        return existing
    
    timestamp = hhmmss(duration // 2)
    output_file = f"{datetime.now().isoformat('_', 'seconds')}.jpg"
    
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-ss", timestamp, "-i", video_path,
            "-frames:v", "1", output_file, "-y",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if os.path.isfile(output_file):
            return output_file
        return None
    except Exception as e:
        logger.error(f"Screenshot generation failed: {e}")
        return None

async def get_video_metadata(file_path: str) -> Dict[str, int]:
    """Get video metadata using OpenCV in a threadpool."""
    def _extract_metadata():
        try:
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                return DEFAULT_VIDEO_METADATA
                
            width = round(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            
            duration = round(frames / fps) if fps > 0 else 1
            cap.release()
            
            return {
                'width': max(1, width),
                'height': max(1, height),
                'duration': max(1, duration)
            }
        except Exception:
            return DEFAULT_VIDEO_METADATA
    
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _extract_metadata)
    except Exception as e:
        logger.error(f"Video metadata error: {e}")
        return DEFAULT_VIDEO_METADATA

async def add_premium_user(
    user_id: int,
    duration_value: int,
    duration_unit: str
) -> Tuple[bool, Union[datetime, str]]:
    """Add premium subscription for user."""
    unit_map = {
        "min": timedelta(minutes=duration_value),
        "hours": timedelta(hours=duration_value),
        "days": timedelta(days=duration_value),
        "weeks": timedelta(weeks=duration_value),
        "month": timedelta(days=30 * duration_value),
        "year": timedelta(days=365 * duration_value),
        "decades": timedelta(days=3650 * duration_value)
    }
    
    if duration_unit not in unit_map:
        return False, "Invalid duration unit"
    
    expiry_date = datetime.now() + unit_map[duration_unit]
    
    try:
        await premium_users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "subscription_start": datetime.now(),
                "subscription_end": expiry_date,
                "expireAt": expiry_date
            }},
            upsert=True
        )
        return True, expiry_date
    except Exception as e:
        logger.error(f"Premium user add failed: {e}")
        return False, str(e)

async def is_premium_user(user_id: int) -> bool:
    """Check if user has active premium subscription."""
    try:
        user = await premium_users_collection.find_one({"user_id": user_id})
        return user and datetime.now() < user.get("subscription_end", datetime.min)
    except Exception as e:
        logger.error(f"Premium check failed: {e}")
        return False