# ---------------------------------------------------
# File Name: ytdl.py (updated for Python 3.10+)
# Description: A Pyrogram bot for downloading yt and other sites videos from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan
# GitHub: https://github.com/devgaganin/
# Telegram: https://t.me/team_spy_pro
# YouTube: https://youtube.com/@dev_gagan
# Created: 2025-01-11
# Last Modified: 2025-05-11
# Version: 2.0.6
# License: MIT License
# ---------------------------------------------------

import yt_dlp
import os
import tempfile
import time
import asyncio
import random
import string
import aiohttp
import logging
import math
from shared_client import client, app
from telethon import events
from telethon.tl.types import DocumentAttributeVideo
from utils.func import get_video_metadata, screenshot
from mutagen.id3 import ID3, TIT2, TPE1, COMM, APIC
from mutagen.mp3 import MP3
from typing import Optional, Dict, Any, Union, Tuple
 
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
 
# Thread pool for synchronous operations
thread_pool = ThreadPoolExecutor(max_workers=4)
ongoing_downloads = {}
 
async def d_thumbnail(thumbnail_url: str, save_path: str) -> Optional[str]:
    """Download thumbnail from URL asynchronously."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail_url) as response:
                if response.status == 200:
                    async with aiofiles.open(save_path, 'wb') as f:
                        await f.write(await response.read())
                    return save_path
    except Exception as e:
        logger.error(f"Failed to download thumbnail: {e}")
        return None
 
async def extract_audio_async(ydl_opts: Dict[str, Any], url: str) -> Dict[str, Any]:
    """Extract audio info asynchronously using thread pool."""
    def sync_extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=True)
    return await asyncio.get_event_loop().run_in_executor(thread_pool, sync_extract)
 
def get_random_string(length: int = 7) -> str:
    """Generate random string for filenames."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
 
async def process_audio(client: Any, event: Any, url: str, cookies_env_var: Optional[str] = None) -> None:
    """Process audio download and upload."""
    cookies = None
    if cookies_env_var:
        cookies = globals().get(cookies_env_var)
 
    temp_cookie_path = None
    if cookies:
        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as temp_cookie_file:
            temp_cookie_file.write(cookies)
            temp_cookie_path = temp_cookie_file.name
 
    random_filename = f"@team_spy_pro_{event.sender_id}"
    download_path = f"{random_filename}.mp3"
 
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f"{random_filename}.%(ext)s",
        'cookiefile': temp_cookie_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192'
        }],
        'quiet': True,
        'noplaylist': True,
    }
 
    progress_message = await event.reply("**__Starting audio extraction...__**")
 
    try:
        info_dict = await extract_audio_async(ydl_opts, url)
        title = info_dict.get('title', 'Extracted Audio')
 
        await progress_message.edit("**__Editing metadata...__**")
 
        if os.path.exists(download_path):
            def edit_metadata():
                audio_file = MP3(download_path, ID3=ID3)
                try:
                    audio_file.add_tags()
                except Exception:
                    pass
                
                audio_file.tags["TIT2"] = TIT2(encoding=3, text=title)
                audio_file.tags["TPE1"] = TPE1(encoding=3, text="Team SPY")
                audio_file.tags["COMM"] = COMM(encoding=3, lang="eng", desc="Comment", text="Processed by Team SPY")
 
                thumbnail_url = info_dict.get('thumbnail')
                if thumbnail_url:
                    thumbnail_path = os.path.join(tempfile.gettempdir(), "thumb.jpg")
                    asyncio.run(d_thumbnail(thumbnail_url, thumbnail_path))
                    with open(thumbnail_path, 'rb') as img:
                        audio_file.tags["APIC"] = APIC(
                            encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img.read()
                        )
                    os.remove(thumbnail_path)
                audio_file.save()
 
            await asyncio.to_thread(edit_metadata)
 
            chat_id = event.chat_id
            await progress_message.delete()
            prog = await client.send_message(chat_id, "**__Starting Upload...__**")
            
            uploaded = await fast_upload(
                client, download_path, 
                reply=prog, 
                name=None,
                progress_bar_function=lambda done, total: progress_callback(done, total, chat_id)
            )
            
            await client.send_file(
                chat_id, 
                uploaded, 
                caption=f"**{title}**\n\n**__Powered by Team SPY__**"
            )
            
            if prog:
                await prog.delete()
        else:
            await event.reply("**__Audio file not found after extraction!__**")
 
    except Exception as e:
        logger.exception("Error during audio extraction or upload")
        await event.reply(f"**__An error occurred: {e}__**")
    finally:
        if os.path.exists(download_path):
            os.remove(download_path)
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            os.remove(temp_cookie_path)
 
@client.on(events.NewMessage(pattern="/adl"))
async def audio_download_handler(event: Any) -> None:
    """Handle /adl command for audio downloads."""
    user_id = event.sender_id
    if user_id in ongoing_downloads:
        await event.reply("**You already have an ongoing download. Please wait until it completes!**")
        return
 
    if len(event.message.text.split()) < 2:
        await event.reply("**Usage:** `/adl <video-link>`\n\nPlease provide a valid video link!")
        return    
 
    url = event.message.text.split()[1]
    ongoing_downloads[user_id] = True
 
    try:
        if "instagram.com" in url:
            await process_audio(client, event, url, "INSTA_COOKIES")
        elif "youtube.com" in url or "youtu.be" in url:
            await process_audio(client, event, url, "YT_COOKIES")
        else:
            await process_audio(client, event, url)
    except Exception as e:
        await event.reply(f"**An error occurred:** `{e}`")
    finally:
        ongoing_downloads.pop(user_id, None)
 
async def fetch_video_info(url: str, ydl_opts: Dict[str, Any], progress_message: Any, check_duration_and_size: bool) -> Optional[Dict[str, Any]]:
    """Fetch video info with optional duration and size checks."""
    def sync_fetch():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    
    info_dict = await asyncio.get_event_loop().run_in_executor(thread_pool, sync_fetch)
 
    if check_duration_and_size and info_dict:
        duration = info_dict.get('duration', 0)
        if duration > 3 * 3600:  # 3 hours
            await progress_message.edit("**❌ __Video is longer than 3 hours. Download aborted...__**")
            return None
 
        estimated_size = info_dict.get('filesize_approx', 0)
        if estimated_size > 2 * 1024 * 1024 * 1024:  # 2GB
            await progress_message.edit("**🤞 __Video size is larger than 2GB. Aborting download.__**")
            return None
 
    return info_dict
 
def download_video(url: str, ydl_opts: Dict[str, Any]) -> None:
    """Synchronous video download function."""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
 
@client.on(events.NewMessage(pattern="/dl"))
async def video_download_handler(event: Any) -> None:
    """Handle /dl command for video downloads."""
    user_id = event.sender_id
 
    if user_id in ongoing_downloads:
        await event.reply("**You already have an ongoing ytdlp download. Please wait until it completes!**")
        return
 
    if len(event.message.text.split()) < 2:
        await event.reply("**Usage:** `/dl <video-link>`\n\nPlease provide a valid video link!")
        return    
 
    url = event.message.text.split()[1]
 
    try:
        if "instagram.com" in url:
            await process_video(client, event, url, "INSTA_COOKIES", check_duration_and_size=False)
        elif "youtube.com" in url or "youtu.be" in url:
            await process_video(client, event, url, "YT_COOKIES", check_duration_and_size=True)
        else:
            await process_video(client, event, url, None, check_duration_and_size=False)
    except Exception as e:
        await event.reply(f"**An error occurred:** `{e}`")
    finally:
        ongoing_downloads.pop(user_id, None)
 
user_progress = {}
 
async def progress_callback(done: int, total: int, user_id: int) -> str:
    """Generate progress callback message."""
    if user_id not in user_progress:
        user_progress[user_id] = {
            'previous_done': 0,
            'previous_time': time.time()
        }
 
    user_data = user_progress[user_id]
    percent = (done / total) * 100
    completed_blocks = int(percent // 10)
    remaining_blocks = 10 - completed_blocks
    progress_bar = "♦" * completed_blocks + "◇" * remaining_blocks
 
    done_mb = done / (1024 * 1024)
    total_mb = total / (1024 * 1024)
 
    speed = done - user_data['previous_done']
    elapsed_time = time.time() - user_data['previous_time']
    speed_bps = speed / elapsed_time if elapsed_time > 0 else 0
    speed_mbps = (speed_bps * 8) / (1024 * 1024)
 
    remaining_time = (total - done) / speed_bps if speed_bps > 0 else 0
    remaining_time_min = remaining_time / 60
 
    progress_text = (
        f"╭──────────────────╮\n"
        f"│        **__Uploading...__**       \n"
        f"├──────────\n"
        f"│ {progress_bar}\n\n"
        f"│ **__Progress:__** {percent:.2f}%\n"
        f"│ **__Done:__** {done_mb:.2f} MB / {total_mb:.2f} MB\n"
        f"│ **__Speed:__** {speed_mbps:.2f} Mbps\n"
        f"│ **__Time Remaining:__** {remaining_time_min:.2f} min\n"
        f"╰──────────────────╯\n\n"
        f"**__Powered by Team SPY__**"
    )
 
    user_data['previous_done'] = done
    user_data['previous_time'] = time.time()
 
    return progress_text
 
async def process_video(client: Any, event: Any, url: str, cookies_env_var: Optional[str], check_duration_and_size: bool = False) -> None:
    """Process video download and upload."""
    cookies = None
    if cookies_env_var:
        cookies = globals().get(cookies_env_var)
 
    random_filename = get_random_string() + ".mp4"
    download_path = os.path.abspath(random_filename)
 
    temp_cookie_path = None
    if cookies:
        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as temp_cookie_file:
            temp_cookie_file.write(cookies)
            temp_cookie_path = temp_cookie_file.name
 
    thumbnail_file = None
    metadata = {'width': None, 'height': None, 'duration': None, 'thumbnail': None}
 
    ydl_opts = {
        'outtmpl': download_path,
        'format': 'best',
        'cookiefile': temp_cookie_path if temp_cookie_path else None,
        'writethumbnail': True,
        'quiet': True,
    }
    
    progress_message = await event.reply("**__Starting download...__**")
    
    try:
        info_dict = await fetch_video_info(url, ydl_opts, progress_message, check_duration_and_size)
        if not info_dict:
            return
 
        await asyncio.to_thread(download_video, url, ydl_opts)
        title = info_dict.get('title', 'Powered by Team SPY')
        k = await get_video_metadata(download_path)      
        W = k['width']
        H = k['height']
        D = k['duration']
        metadata['width'] = info_dict.get('width') or W
        metadata['height'] = info_dict.get('height') or H
        metadata['duration'] = int(info_dict.get('duration') or 0) or D
        thumbnail_url = info_dict.get('thumbnail', None)
        THUMB = None
 
        if thumbnail_url:
            thumbnail_file = os.path.join(tempfile.gettempdir(), get_random_string() + ".jpg")
            downloaded_thumb = await d_thumbnail(thumbnail_url, thumbnail_file)
            if downloaded_thumb:
                THUMB = downloaded_thumb
        else:
            THUMB = await screenshot(download_path, metadata['duration'], event.sender_id)

        chat_id = event.chat_id
        SIZE = 2 * 1024 * 1024 * 1024  # 2GB
        caption = f"{title}"
     
        if os.path.exists(download_path) and os.path.getsize(download_path) > SIZE:
            prog = await client.send_message(chat_id, "**__Starting Upload...__**")
            await split_and_upload_file(app, chat_id, download_path, caption)
            await prog.delete()
         
        if os.path.exists(download_path):
            await progress_message.delete()
            prog = await client.send_message(chat_id, "**__Starting Upload...__**")
            uploaded = await fast_upload(
                client, download_path,
                reply=prog,
                progress_bar_function=lambda done, total: progress_callback(done, total, chat_id)
            )
            await client.send_file(
                event.chat_id,
                uploaded,
                caption=f"**{title}**",
                attributes=[
                    DocumentAttributeVideo(
                        duration=metadata['duration'],
                        w=metadata['width'],
                        h=metadata['height'],
                        supports_streaming=True
                    )
                ],
                thumb=THUMB if THUMB else None
            )
            if prog:
                await prog.delete()
        else:
            await event.reply("**__File not found after download. Something went wrong!__**")
    except Exception as e:
        logger.exception("An error occurred during download or upload.")
        await event.reply(f"**__An error occurred: {e}__**")
    finally:
        if os.path.exists(download_path):
            os.remove(download_path)
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            os.remove(temp_cookie_path)
        if thumbnail_file and os.path.exists(thumbnail_file):
            os.remove(thumbnail_file)
 
async def split_and_upload_file(app: Any, sender: int, file_path: str, caption: str) -> None:
    """Split large files and upload them in parts."""
    if not os.path.exists(file_path):
        await app.send_message(sender, "❌ File not found!")
        return

    file_size = os.path.getsize(file_path)
    start = await app.send_message(sender, f"ℹ️ File size: {file_size / (1024 * 1024 * 1024):.2f} GB")
    PART_SIZE = 1.9 * 1024 * 1024 * 1024  # 1.9GB per part

    part_number = 0
    async with aiofiles.open(file_path, mode="rb") as f:
        while True:
            chunk = await f.read(PART_SIZE)
            if not chunk:
                break

            base_name, file_ext = os.path.splitext(file_path)
            part_file = f"{base_name}.part{str(part_number).zfill(3)}{file_ext}"

            async with aiofiles.open(part_file, mode="wb") as part_f:
                await part_f.write(chunk)

            edit = await app.send_message(sender, f"⬆️ Uploading part {part_number + 1}...")
            part_caption = f"{caption} \n\n**Part : {part_number + 1}**"
            
            await app.send_document(
                sender,
                document=part_file,
                caption=part_caption,
                progress=progress_bar,
                progress_args=(
                    "╭─────────────────────╮\n│      **__Pyro Uploader__**\n├─────────────────────",
                    edit,
                    time.time()
                )
            )
            
            await edit.delete()
            os.remove(part_file)
            part_number += 1

    await start.delete()
    os.remove(file_path)

PROGRESS_BAR = """
│ **__Completed:__** {1}/{2}
│ **__Bytes:__** {0}%
│ **__Speed:__** {3}/s
│ **__ETA:__** {4}
╰─────────────────────╯
"""

async def progress_bar(current: int, total: int, ud_type: str, message: Any, start: float) -> None:
    """Update progress bar for uploads."""
    now = time.time()
    diff = now - start
    
    if round(diff % 10) == 0 or current == total:
        percentage = (current * 100) / total
        speed = current / diff if diff else 0
        elapsed_time = round(diff * 1000)
        time_to_completion = round((total - current) / speed) * 1000 if speed else 0
        estimated_total_time = elapsed_time + time_to_completion

        elapsed_time_str = TimeFormatter(elapsed_time)
        estimated_total_time_str = TimeFormatter(estimated_total_time)

        progress = "".join(["♦" for _ in range(math.floor(percentage / 10))]) + \
                   "".join(["◇" for _ in range(10 - math.floor(percentage / 10))])
        
        progress_text = progress + PROGRESS_BAR.format(
            round(percentage, 2),
            humanbytes(current),
            humanbytes(total),
            humanbytes(speed),
            estimated_total_time_str if estimated_total_time_str else "0 s"
        )
        try:
            await message.edit(text=f"{ud_type}\n│ {progress_text}")
        except Exception:
            pass

def humanbytes(size: int) -> str:
    """Convert bytes to human-readable format."""
    if not size:
        return ""
    
    power = 2**10
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    n = 0
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    
    return f"{round(size, 2)} {units[n]}"

def TimeFormatter(milliseconds: int) -> str:
    """Format milliseconds to human-readable time."""
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    if seconds: parts.append(f"{seconds}s")
    if milliseconds: parts.append(f"{milliseconds}ms")
    
    return ', '.join(parts)

def convert(seconds: int) -> str:
    """Convert seconds to HH:MM:SS format."""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"
