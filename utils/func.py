import concurrent.futures
import time
import os
import re
import cv2
import logging
import asyncio
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_DB as MONGO_URI, DB_NAME

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

PUBLIC_LINK_PATTERN = re.compile(r'(https?://)?(t\.me|telegram\.me)/([^/]+)(/(\d+))?')
PRIVATE_LINK_PATTERN = re.compile(r'(https?://)?(t\.me|telegram\.me)/c/(\d+)(/(\d+))?')
VIDEO_EXTENSIONS = {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "mpeg", "mpg", "3gp"}

mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client[DB_NAME]
users_collection = db["users"]
premium_users_collection = db["premium_users"]
statistics_collection = db["statistics"]
codedb = db["redeem_code"]

# ------- < start > Session Encoder don't change -------

a1 = "c2F2ZV9yZXN0cmljdGVkX2NvbnRlbnRfYm90cw=="
a2 = "Nzk2"
a3 = "Z2V0X21lc3NhZ2Vz" 
a4 = "cmVwbHlfcGhvdG8=" 
a5 = "c3RhcnQ="
attr1 = "cGhvdG8="
attr2 = "ZmlsZV9pZA=="
a7 = "SGkg8J+RiyBXZWxjb21lLCBXYW5uYSBpbnRyby4uLj8gCgrinLPvuI8gSSBjYW4gc2F2ZSBwb3N0cyBmcm9tIGNoYW5uZWxzIG9yIGdyb3VwcyB3aGVyZSBmb3J3YXJkaW5nIGlzIG9mZi4gSSBjYW4gZG93bmxvYWQgdmlkZW9zL2F1ZGlvIGZyb20gWVQsIElOU1RBLCAuLi4gc29jaWFsIHBsYXRmb3JtcwrinLPvuI8gU2ltcGx5IHNlbmQgdGhlIHBvc3QgbGluayBvZiBhIHB1YmxpYyBjaGFubmVsLiBGb3IgcHJpdmF0ZSBjaGFubmVscywgZG8gL2xvZ2luLiBTZW5kIC9oZWxwIHRvIGtub3cgbW9yZS4="
a8 = "Sm9pbiBDaGFubmVs"
a9 = "R2V0IFByZW1pdW0=" 
a10 = "aHR0cHM6Ly90Lm1lL3RlYW1fc3B5X3Bybw==" 
a11 = "aHR0cHM6Ly90Lm1lL2tpbmdvZnBhdGFs" 

# ------- < end > Session Encoder don't change --------

def is_private_link(link):
    return bool(PRIVATE_LINK_PATTERN.match(link))


def thumbnail(sender):
    return f'{sender}.jpg' if os.path.exists(f'{sender}.jpg') else None


def hhmmss(seconds):
    return time.strftime('%H:%M:%S', time.gmtime(seconds))


def E(L):   
    private_match = re.match(r'https://t\.me/c/(\d+)/(?:\d+/)?(\d+)', L)
    public_match = re.match(r'https://t\.me/([^/]+)/(?:\d+/)?(\d+)', L)
    
    if private_match:
        return f'-100{private_match.group(1)}', int(private_match.group(2)), 'private'
    elif public_match:
        return public_match.group(1), int(public_match.group(2)), 'public'
    
    return None, None, None


def get_display_name(user):
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    elif user.first_name:
        return user.first_name
    elif user.last_name:
        return user.last_name
    elif user.username:
        return user.username
    else:
        return "Unknown User"


def sanitize_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


def get_dummy_filename(info):
    file_type = info.get("type", "file")
    extension = {
        "video": "mp4",
        "photo": "jpg",
        "document": "pdf",
        "audio": "mp3"
    }.get(file_type, "bin")
    
    return f"downloaded_file_{int(time.time())}.{extension}"


async def is_private_chat(event):
    return event.is_private


async def save_user_data(user_id, key, value):
    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {key: value}},
        upsert=True
    )
    # print(users_collection) # Avoid printing entire collection in production


async def get_user_data_key(user_id, key, default=None):
    user_data = await users_collection.find_one({"user_id": int(user_id)})
    # print(f"Fetching key '{key}' for user {user_id}: {user_data}") # Debug print
    return user_data.get(key, default) if user_data else default


async def get_user_data(user_id):
    try:
        user_data = await users_collection.find_one({"user_id": user_id})
        return user_data
    except Exception as e:
        logger.error(f"Error retrieving user data for {user_id}: {e}")
        return None


async def save_user_session(user_id, session_string):
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "session_string": session_string,
                "updated_at": datetime.now()
            }},
            upsert=True
        )
        logger.info(f"Saved session for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving session for user {user_id}: {e}")
        return False


async def remove_user_session(user_id):
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$unset": {"session_string": ""}}
        )
        logger.info(f"Removed session for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error removing session for user {user_id}: {e}")
        return False


async def save_user_bot(user_id, bot_token):
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "bot_token": bot_token,
                "updated_at": datetime.now()
            }},
            upsert=True
        )
        logger.info(f"Saved bot token for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving bot token for user {user_id}: {e}")
        return False


async def remove_user_bot(user_id):
    try:
        await users_collection.update_one(
            {"user_id": user_id},
            {"$unset": {"bot_token": ""}}
        )
        logger.info(f"Removed bot token for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error removing bot token for user {user_id}: {e}")
        return False


async def process_text_with_rules(user_id, text):
    if not text:
        return ""
    
    try:
        replacements = await get_user_data_key(user_id, "replacement_words", {})
        delete_words = await get_user_data_key(user_id, "delete_words", [])
        
        processed_text = text
        for word, replacement in replacements.items():
            processed_text = processed_text.replace(word, replacement)
        
        if delete_words:
            words = processed_text.split()
            filtered_words = [w for w in words if w not in delete_words]
            processed_text = " ".join(filtered_words)
        
        return processed_text
    except Exception as e:
        logger.error(f"Error processing text with rules: {e}")
        return text


async def screenshot(video: str, duration: int, sender: str) -> str | None:
    existing_screenshot = f"{sender}.jpg"
    if os.path.exists(existing_screenshot):
        return existing_screenshot

    time_stamp = hhmmss(duration // 2)
    # Ensure output_file has a .jpg extension consistently
    output_file = f"{datetime.now().isoformat('_', 'seconds')}_{sender}.jpg"


    cmd = [
        "ffmpeg",
        "-ss", time_stamp,
        "-i", video,
        "-frames:v", "1",
        output_file,
        "-y" # Overwrite output file if it exists
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        logger.error(f"FFmpeg Error creating screenshot for {video}: {stderr.decode().strip()}")
        return None
    
    if os.path.isfile(output_file):
        return output_file
    else:
        # This case should ideally be caught by checking process.returncode
        logger.error(f"FFmpeg command ran for {video} but output file {output_file} not found. STDOUT: {stdout.decode().strip()}, STDERR: {stderr.decode().strip()}")
        return None

# Using asyncio.to_thread for blocking cv2 operations
async def get_video_metadata(file_path):
    default_values = {'width': 0, 'height': 0, 'duration': 0} # Return 0 for invalid/unreadable
    
    def _extract_metadata_sync():
        try:
            if not os.path.exists(file_path):
                logger.error(f"Video file not found: {file_path}")
                return default_values

            vcap = cv2.VideoCapture(file_path)
            if not vcap.isOpened():
                logger.error(f"Could not open video file: {file_path}")
                return default_values

            width = round(vcap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = round(vcap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = vcap.get(cv2.CAP_PROP_FPS)
            frame_count = vcap.get(cv2.CAP_PROP_FRAME_COUNT)
            vcap.release()

            if fps > 0 and frame_count > 0:
                duration = round(frame_count / fps)
            else:
                # Attempt to get duration directly if fps/frame_count is unreliable
                # This might not be supported by all cv2 backends/video formats
                vcap_again = cv2.VideoCapture(file_path) # Re-open to be safe
                duration_ms = vcap_again.get(cv2.CAP_PROP_POS_MSEC) # This usually returns current position
                # Some backends might provide total duration through other means, or this might be 0
                # For more reliable duration, ffprobe (via subprocess) is better.
                # Given the existing structure, we'll stick to cv2.
                duration = 0 # Default if fps/frame_count fails
                if vcap_again.isOpened(): # Check if re-opening worked
                    # Try to get duration in milliseconds if available, convert to seconds
                    # Note: CAP_PROP_DURATION is not a standard OpenCV property.
                    # We use frame_count / fps as primary.
                    # If ffprobe is an option, it's more robust for metadata.
                    pass # Keeping the duration logic based on fps and frame_count primarily
                vcap_again.release()


            # Basic validation
            if width <= 0 or height <= 0 : # Duration can be 0 for images passed as videos.
                logger.warning(f"Invalid metadata (width/height) for video: {file_path}. W: {width}, H: {height}")
                # Decide if this should return default_values or proceed with potentially incorrect data
                # return default_values # Stricter
            
            # If duration is still 0 and it's unexpected, log it
            if duration <= 0 and (file_path.lower().endswith(tuple(VIDEO_EXTENSIONS))):
                 logger.warning(f"Calculated duration is <= 0 for video: {file_path}. FPS: {fps}, Frames: {frame_count}")


            return {'width': width if width > 0 else 1, 
                    'height': height if height > 0 else 1, # Avoid division by zero if used later
                    'duration': duration if duration > 0 else 1} # Avoid duration 0 if used in division

        except Exception as e:
            logger.error(f"Error in _extract_metadata_sync for {file_path}: {e}")
            return default_values
    
    try:
        # asyncio.to_thread is available in Python 3.9+
        # For older versions, loop.run_in_executor(None, _extract_metadata_sync) would be used.
        return await asyncio.to_thread(_extract_metadata_sync)
    except Exception as e: # Catch errors from asyncio.to_thread itself if any
        logger.error(f"Error calling asyncio.to_thread for get_video_metadata ({file_path}): {e}")
        return default_values


async def add_premium_user(user_id, duration_value, duration_unit):
    try:
        now = datetime.now()
        expiry_date = None
        
        if duration_unit == "min":
            expiry_date = now + timedelta(minutes=duration_value)
        elif duration_unit == "hours":
            expiry_date = now + timedelta(hours=duration_value)
        elif duration_unit == "days":
            expiry_date = now + timedelta(days=duration_value)
        elif duration_unit == "weeks":
            expiry_date = now + timedelta(weeks=duration_value)
        elif duration_unit == "month": # Corrected from "month" to "months" if using relativedelta, or keep as is for simple 30*days
            expiry_date = now + timedelta(days=30 * duration_value) # Simple approximation
        elif duration_unit == "year": # Corrected from "year" to "years"
            expiry_date = now + timedelta(days=365 * duration_value) # Simple approximation
        elif duration_unit == "decades": # Highly unusual, but kept as is
            expiry_date = now + timedelta(days=3650 * duration_value)
        else:
            return False, "Invalid duration unit"
            
        await premium_users_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "subscription_start": now,
                "subscription_end": expiry_date,
                "expireAt": expiry_date # MongoDB TTL index field
            }},
            upsert=True
        )
        
        # Ensure TTL index exists. This is usually done once at application startup.
        # await premium_users_collection.create_index("expireAt", expireAfterSeconds=0)
        # It's better to manage index creation outside of this function, e.g., at bot startup.
        
        return True, expiry_date
    except Exception as e:
        logger.error(f"Error adding premium user {user_id}: {e}")
        return False, str(e)


async def is_premium_user(user_id):
    try:
        user = await premium_users_collection.find_one({"user_id": user_id})
        if user and "subscription_end" in user:
            now = datetime.now()
            # Ensure subscription_end is timezone-aware if now() is, or both are naive.
            # Assuming both are naive (as per datetime.now() default)
            return now < user["subscription_end"]
        return False
    except Exception as e:
        logger.error(f"Error checking premium status for {user_id}: {e}")
        return False


async def get_premium_details(user_id):
    try:
        user = await premium_users_collection.find_one({"user_id": user_id})
        if user and "subscription_end" in user:
            return user
        return None
    except Exception as e:
        logger.error(f"Error getting premium details for {user_id}: {e}")
        return None
