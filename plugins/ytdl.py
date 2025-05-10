import os
import tempfile
import time
import asyncio
import random
import string
import logging
import math
from typing import Optional, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
import aiohttp
import aiofiles
from mutagen.id3 import ID3, TIT2, TPE1, COMM, APIC
from mutagen.mp3 import MP3
from telethon import events
from telethon.tl.types import DocumentAttributeVideo
from telethon.tl.functions.messages import EditMessageRequest

from shared_client import client, app
from utils.func import get_video_metadata, screenshot
from devgagantools import fast_upload
from config import YT_COOKIES, INSTA_COOKIES

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Global state
thread_pool = ThreadPoolExecutor(max_workers=4)
ongoing_downloads = {}
user_progress = {}

class DownloadManager:
    @staticmethod
    def get_random_string(length: int = 7) -> str:
        """Generate a random alphanumeric string."""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    @staticmethod
    async def download_thumbnail(url: str, path: str) -> Optional[str]:
        """Download a thumbnail from URL."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        async with aiofiles.open(path, 'wb') as f:
                            await f.write(await response.read())
                        return path
        except Exception as e:
            logger.error(f"Failed to download thumbnail: {e}")
        return None

    @staticmethod
    async def extract_info(ydl_opts: Dict, url: str) -> Dict:
        """Extract video info using yt-dlp."""
        def sync_extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        return await asyncio.get_event_loop().run_in_executor(thread_pool, sync_extract)

    @staticmethod
    async def download_video(ydl_opts: Dict, url: str) -> None:
        """Download video using yt-dlp."""
        def sync_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        await asyncio.get_event_loop().run_in_executor(thread_pool, sync_download)

class ProgressManager:
    @staticmethod
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

    @staticmethod
    def time_formatter(milliseconds: int) -> str:
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

    @staticmethod
    async def progress_bar(
        current: int,
        total: int,
        ud_type: str,
        message,
        start: float
    ) -> None:
        """Update progress bar for uploads."""
        now = time.time()
        diff = now - start

        if round(diff % 10) == 0 or current == total:
            percentage = (current * 100) / total
            speed = current / diff if diff else 0
            elapsed_time = round(diff * 1000)
            time_to_completion = round((total - current) / speed) * 1000 if speed else 0
            estimated_total_time = elapsed_time + time_to_completion

            elapsed_time_str = ProgressManager.time_formatter(elapsed_time)
            estimated_total_time_str = ProgressManager.time_formatter(estimated_total_time)

            progress = "".join(["♦" for _ in range(math.floor(percentage / 10))]) + \
                      "".join(["◇" for _ in range(10 - math.floor(percentage / 10))])
            
            progress_text = (
                f"{ud_type}\n│ {progress}\n\n"
                f"│ **__Completed:__** {ProgressManager.humanbytes(current)}/{ProgressManager.humanbytes(total)}\n"
                f"│ **__Progress:__** {round(percentage, 2)}%\n"
                f"│ **__Speed:__** {ProgressManager.humanbytes(speed)}/s\n"
                f"│ **__ETA:__** {estimated_total_time_str if estimated_total_time_str else '0 s'}\n"
                f"╰─────────────────────╯"
            )
            try:
                await message.edit(text=progress_text)
            except Exception as e:
                logger.warning(f"Failed to update progress: {e}")

    @staticmethod
    async def upload_progress(
        done: int,
        total: int,
        user_id: int,
        message=None
    ) -> str:
        """Generate upload progress text."""
        if user_id not in user_progress:
            user_progress[user_id] = {
                'previous_done': 0,
                'previous_time': time.time()
            }

        user_data = user_progress[user_id]
        percent = (done / total) * 100
        completed_blocks = int(percent // 10)
        progress_bar = "♦" * completed_blocks + "◇" * (10 - completed_blocks)

        done_mb = done / (1024 * 1024)
        total_mb = total / (1024 * 1024)

        speed = done - user_data['previous_done']
        elapsed_time = time.time() - user_data['previous_time']
        speed_mbps = ((speed / elapsed_time) * 8) / (1024 * 1024) if elapsed_time > 0 else 0
        remaining_time = ((total - done) / speed) / 60 if speed > 0 else 0

        user_data['previous_done'] = done
        user_data['previous_time'] = time.time()

        return (
            f"╭──────────────────╮\n"
            f"│        **__Uploading...__**       \n"
            f"├──────────\n"
            f"│ {progress_bar}\n\n"
            f"│ **__Progress:__** {percent:.2f}%\n"
            f"│ **__Done:__** {done_mb:.2f} MB / {total_mb:.2f} MB\n"
            f"│ **__Speed:__** {speed_mbps:.2f} Mbps\n"
            f"│ **__Time Remaining:__** {remaining_time:.2f} min\n"
            f"╰──────────────────╯\n\n"
            f"**__Powered by Team SPY__**"
        )

class FileHandler:
    @staticmethod
    async def split_and_upload(
        client,
        chat_id: int,
        file_path: str,
        caption: str,
        part_size: float = 1.9 * 1024 * 1024 * 1024
    ) -> None:
        """Split large file and upload parts."""
        if not os.path.exists(file_path):
            await client.send_message(chat_id, "❌ File not found!")
            return

        file_size = os.path.getsize(file_path)
        start_msg = await client.send_message(chat_id, f"ℹ️ File size: {file_size / (1024 * 1024):.2f} MB")

        part_number = 0
        async with aiofiles.open(file_path, "rb") as f:
            while True:
                chunk = await f.read(int(part_size))
                if not chunk:
                    break

                base_name, ext = os.path.splitext(file_path)
                part_file = f"{base_name}.part{str(part_number).zfill(3)}{ext}"

                async with aiofiles.open(part_file, "wb") as part_f:
                    await part_f.write(chunk)

                progress_msg = await client.send_message(
                    chat_id,
                    f"⬆️ Uploading part {part_number + 1}..."
                )
                part_caption = f"{caption} \n\n**Part: {part_number + 1}**"
                
                await client.send_document(
                    chat_id,
                    document=part_file,
                    caption=part_caption,
                    progress=ProgressManager.progress_bar,
                    progress_args=(
                        "╭─────────────────────╮\n│      **__Pyro Uploader__**\n├─────────────────────",
                        progress_msg,
                        time.time()
                    )
                )
                await progress_msg.delete()
                os.remove(part_file)
                part_number += 1

        await start_msg.delete()
        os.remove(file_path)

    @staticmethod
    async def edit_audio_metadata(
        file_path: str,
        title: str,
        thumbnail_url: Optional[str] = None
    ) -> None:
        """Edit ID3 metadata for audio files."""
        def sync_edit():
            audio = MP3(file_path, ID3=ID3)
            try:
                audio.add_tags()
            except Exception:
                pass

            audio.tags["TIT2"] = TIT2(encoding=3, text=title)
            audio.tags["TPE1"] = TPE1(encoding=3, text="Team SPY")
            audio.tags["COMM"] = COMM(encoding=3, lang="eng", desc="Comment", text="Processed by Team SPY")

            if thumbnail_url:
                thumb_path = os.path.join(tempfile.gettempdir(), f"thumb_{os.path.basename(file_path)}.jpg")
                with requests.get(thumbnail_url, stream=True) as r:
                    r.raise_for_status()
                    with open(thumb_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                with open(thumb_path, 'rb') as img:
                    audio.tags["APIC"] = APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='Cover',
                        data=img.read()
                    )
                os.remove(thumb_path)
            audio.save()
        
        await asyncio.get_event_loop().run_in_executor(thread_pool, sync_edit)

class MediaProcessor:
    @staticmethod
    async def process_audio(
        client,
        event,
        url: str,
        cookies: Optional[str] = None
    ) -> None:
        """Process audio download and upload."""
        user_id = event.sender_id
        start_time = time.time()
        random_filename = f"@team_spy_pro_{user_id}"
        download_path = f"{random_filename}.mp3"

        # Create temp cookie file if needed
        temp_cookie_path = None
        if cookies:
            with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as f:
                f.write(cookies)
                temp_cookie_path = f.name

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

        progress_msg = await event.reply("**__Starting audio extraction...__**")

        try:
            # Extract info and download
            info_dict = await DownloadManager.extract_info(ydl_opts, url)
            title = info_dict.get('title', 'Extracted Audio')
            await DownloadManager.download_video(ydl_opts, url)

            if not os.path.exists(download_path):
                raise FileNotFoundError("Audio file not created")

            # Edit metadata
            await progress_msg.edit("**__Editing metadata...__**")
            thumbnail_url = info_dict.get('thumbnail')
            await FileHandler.edit_audio_metadata(download_path, title, thumbnail_url)

            # Upload
            await progress_msg.delete()
            progress_msg = await client.send_message(event.chat_id, "**__Starting Upload...__**")
            
            uploaded = await fast_upload(
                client,
                download_path,
                reply=progress_msg,
                progress_bar_function=lambda d, t: ProgressManager.upload_progress(d, t, user_id)
            )
            
            await client.send_file(
                event.chat_id,
                uploaded,
                caption=f"**{title}**\n\n**__Powered by Team SPY__**"
            )

        except Exception as e:
            logger.exception("Audio processing error")
            await event.reply(f"**__An error occurred: {e}__**")
        finally:
            if os.path.exists(download_path):
                os.remove(download_path)
            if temp_cookie_path and os.path.exists(temp_cookie_path):
                os.remove(temp_cookie_path)
            if progress_msg:
                await progress_msg.delete()

    @staticmethod
    async def process_video(
        client,
        event,
        url: str,
        cookies: Optional[str] = None,
        check_duration_and_size: bool = True
    ) -> None:
        """Process video download and upload."""
        user_id = event.sender_id
        start_time = time.time()
        random_filename = DownloadManager.get_random_string() + ".mp4"
        download_path = os.path.abspath(random_filename)

        # Create temp cookie file if needed
        temp_cookie_path = None
        if cookies:
            with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as f:
                f.write(cookies)
                temp_cookie_path = f.name

        ydl_opts = {
            'outtmpl': download_path,
            'format': 'best',
            'cookiefile': temp_cookie_path,
            'writethumbnail': True,
            'quiet': True,
        }

        progress_msg = await event.reply("**__Starting download...__**")
        thumbnail_path = None
        metadata = {'width': None, 'height': None, 'duration': None}

        try:
            # Check video info first
            info_dict = await DownloadManager.extract_info(ydl_opts, url)
            if not info_dict:
                return

            if check_duration_and_size:
                duration = info_dict.get('duration', 0)
                if duration > 3 * 3600:
                    await progress_msg.edit("**❌ Video is longer than 3 hours**")
                    return

                size = info_dict.get('filesize_approx', 0)
                if size > 2 * 1024 * 1024 * 1024:
                    await progress_msg.edit("**❌ Video is larger than 2GB**")
                    return

            # Download video
            await DownloadManager.download_video(ydl_opts, url)
            title = info_dict.get('title', 'Powered by Team SPY')

            # Get metadata
            video_meta = await get_video_metadata(download_path)
            metadata.update({
                'width': info_dict.get('width') or video_meta['width'],
                'height': info_dict.get('height') or video_meta['height'],
                'duration': int(info_dict.get('duration') or 0) or video_meta['duration']
            })

            # Handle thumbnail
            thumbnail_url = info_dict.get('thumbnail')
            if thumbnail_url:
                thumbnail_path = os.path.join(tempfile.gettempdir(), f"thumb_{random_filename}.jpg")
                await DownloadManager.download_thumbnail(thumbnail_url, thumbnail_path)
            
            if not thumbnail_path:
                thumbnail_path = await screenshot(download_path, metadata['duration'], user_id)

            # Upload
            await progress_msg.delete()
            progress_msg = await client.send_message(event.chat_id, "**__Starting Upload...__**")

            # Handle large files (>2GB)
            if os.path.getsize(download_path) > 1.9 * 1024 * 1024 * 1024:
                await FileHandler.split_and_upload(
                    client,
                    event.chat_id,
                    download_path,
                    title
                )
            else:
                uploaded = await fast_upload(
                    client,
                    download_path,
                    reply=progress_msg,
                    progress_bar_function=lambda d, t: ProgressManager.upload_progress(d, t, user_id)
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
                    thumb=thumbnail_path
                )

        except Exception as e:
            logger.exception("Video processing error")
            await event.reply(f"**__An error occurred: {e}__**")
        finally:
            if os.path.exists(download_path):
                os.remove(download_path)
            if temp_cookie_path and os.path.exists(temp_cookie_path):
                os.remove(temp_cookie_path)
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
            if progress_msg:
                await progress_msg.delete()

# Command Handlers
@client.on(events.NewMessage(pattern="/adl"))
async def audio_download_handler(event):
    """Handle /adl command for audio downloads."""
    user_id = event.sender_id
    if user_id in ongoing_downloads:
        await event.reply("**You already have an ongoing download!**")
        return

    if len(event.text.split()) < 2:
        await event.reply("**Usage:** `/adl <video-url>`")
        return

    url = event.text.split()[1]
    ongoing_downloads[user_id] = True

    try:
        if "instagram.com" in url:
            await MediaProcessor.process_audio(client, event, url, INSTA_COOKIES)
        elif "youtube.com" in url or "youtu.be" in url:
            await MediaProcessor.process_audio(client, event, url, YT_COOKIES)
        else:
            await MediaProcessor.process_audio(client, event, url)
    except Exception as e:
        await event.reply(f"**Error:** `{e}`")
    finally:
        ongoing_downloads.pop(user_id, None)

@client.on(events.NewMessage(pattern="/dl"))
async def video_download_handler(event):
    """Handle /dl command for video downloads."""
    user_id = event.sender_id
    if user_id in ongoing_downloads:
        await event.reply("**You already have an ongoing download!**")
        return

    if len(event.text.split()) < 2:
        await event.reply("**Usage:** `/dl <video-url>`")
        return

    url = event.text.split()[1]
    ongoing_downloads[user_id] = True

    try:
        if "instagram.com" in url:
            await MediaProcessor.process_video(
                client,
                event,
                url,
                INSTA_COOKIES,
                check_duration_and_size=False
            )
        elif "youtube.com" in url or "youtu.be" in url:
            await MediaProcessor.process_video(
                client,
                event,
                url,
                YT_COOKIES,
                check_duration_and_size=True
            )
        else:
            await MediaProcessor.process_video(
                client,
                event,
                url,
                None,
                check_duration_and_size=False
            )
    except Exception as e:
        await event.reply(f"**Error:** `{e}`")
    finally:
        ongoing_downloads.pop(user_id, None)