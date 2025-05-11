import os, re, time, asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, MessageEntity # For caption entities if needed
from pyrogram.errors import UserNotParticipant
from config import API_ID, API_HASH, LOG_GROUP, STRING, FORCE_SUB, FREEMIUM_LIMIT, PREMIUM_LIMIT
from utils.func import get_user_data, screenshot, thumbnail, get_video_metadata
from utils.func import get_user_data_key, process_text_with_rules, is_premium_user, E
from shared_client import app as X # Assuming X is the Pyrogram Client instance from shared_client
from plugins.settings import rename_file # Assuming this function is correctly defined
from plugins.start import subscribe as sub # Assuming this function is correctly defined
from utils.custom_filters import login_in_progress
from utils.encrypt import dcs
import json
from typing import Dict, Any, Optional

# Ensure userbot (Y) is correctly initialized from shared_client if STRING is present.
# It should be an instance of Pyrogram's Client.
Y = None
if STRING:
    from shared_client import userbot as UserbotClientInstance # Renaming for clarity
    Y = UserbotClientInstance


# Global dictionaries for caching or state. Consider if these need persistence or a more robust state management.
Z: Dict[int, Dict[str, Any]] = {} # User states for commands
P: Dict[int, Any] = {}           # Progress message cache for uploads
UB: Dict[int, Client] = {}       # User-specific bot clients (Pyrogram)
UC: Dict[int, Client] = {}       # User-specific user clients (Pyrogram)
emp: Dict[Any, bool] = {}        # Cache for empty channel check (channel_id/username -> is_empty)

ACTIVE_USERS_FILE = "active_users.json"
ACTIVE_USERS: Dict[str, Any] = {} # Active batch tasks

def load_active_users():
    global ACTIVE_USERS
    try:
        if os.path.exists(ACTIVE_USERS_FILE):
            with open(ACTIVE_USERS_FILE, 'r') as f:
                ACTIVE_USERS = json.load(f)
        else:
            ACTIVE_USERS = {}
    except json.JSONDecodeError:
        print(f"Warning: Could not decode {ACTIVE_USERS_FILE}. Starting with empty active users.")
        ACTIVE_USERS = {}
    except Exception as e:
        print(f"Error loading active users: {e}")
        ACTIVE_USERS = {} # Default to empty on other errors
    return ACTIVE_USERS

async def save_active_users_to_file():
    try:
        with open(ACTIVE_USERS_FILE, 'w') as f:
            json.dump(ACTIVE_USERS, f, indent=4) # Add indent for readability
    except Exception as e:
        print(f"Error saving active users: {e}")

async def add_active_batch(user_id: int, batch_info: Dict[str, Any]):
    ACTIVE_USERS[str(user_id)] = batch_info
    await save_active_users_to_file()

def is_user_active(user_id: int) -> bool:
    return str(user_id) in ACTIVE_USERS

async def update_batch_progress(user_id: int, current: int, success: int):
    user_id_str = str(user_id)
    if user_id_str in ACTIVE_USERS:
        ACTIVE_USERS[user_id_str]["current"] = current
        ACTIVE_USERS[user_id_str]["success"] = success
        await save_active_users_to_file()

async def request_batch_cancel(user_id: int) -> bool:
    user_id_str = str(user_id)
    if user_id_str in ACTIVE_USERS:
        ACTIVE_USERS[user_id_str]["cancel_requested"] = True
        await save_active_users_to_file()
        return True
    return False

def should_cancel(user_id: int) -> bool:
    user_str = str(user_id)
    return user_str in ACTIVE_USERS and ACTIVE_USERS[user_str].get("cancel_requested", False)

async def remove_active_batch(user_id: int):
    user_id_str = str(user_id)
    if user_id_str in ACTIVE_USERS:
        del ACTIVE_USERS[user_id_str]
        await save_active_users_to_file()

def get_batch_info(user_id: int) -> Optional[Dict[str, Any]]:
    return ACTIVE_USERS.get(str(user_id))

# Load active users at startup
ACTIVE_USERS = load_active_users()


async def upd_dlg(c: Client): # c is a Pyrogram Client
    try:
        # Pyrogram clients update dialogs automatically or on interaction.
        # Explicitly getting dialogs can be heavy.
        # If needed for specific cache warming:
        # async for _ in c.get_dialogs(limit=10): pass # limit to a small number
        print(f"Dialog update requested for client {c.name}. Usually not explicitly needed for Pyrogram.")
        return True
    except Exception as e:
        print(f'Failed to update dialogs for {c.name}: {e}')
        return False

async def get_msg(c: Client, u: Optional[Client], i: Any, d: int, lt: str) -> Optional[Message]:
    # c: bot client (pyrogram), u: user client (pyrogram), i: chat_id/username, d: message_id, lt: link_type
    try:
        target_chat_id = i
        if lt == 'public':
            try:
                # For public, bot (c) should be able_to_get_messages directly.
                # If channel username is given, use it. If ID, it should be integer.
                xm = await c.get_messages(target_chat_id, d)
                if hasattr(xm, "empty") and xm.empty: # Check if message is empty (deleted or service)
                    emp[i] = True # Mark as empty
                    # If user client (u) is available and bot failed, try with user client
                    if u:
                        try:
                            await u.join_chat(target_chat_id) # Attempt to join if not already
                        except Exception as join_err:
                            print(f"User client failed to join {target_chat_id}: {join_err}")
                        # Resolve peer for user client if username was passed
                        resolved_chat_id_user = (await u.get_chat(target_chat_id)).id if isinstance(target_chat_id, str) else target_chat_id
                        xm = await u.get_messages(resolved_chat_id_user, d)
                return xm if not (hasattr(xm, "empty") and xm.empty) else None
            except Exception as e_pub:
                print(f'Error fetching public message ({target_chat_id}/{d}): {e_pub}')
                # Fallback to user client if available
                if u:
                    try:
                        resolved_chat_id_user = (await u.get_chat(target_chat_id)).id if isinstance(target_chat_id, str) else target_chat_id
                        return await u.get_messages(resolved_chat_id_user, d)
                    except Exception as e_pub_user:
                        print(f'User client also failed for public message ({target_chat_id}/{d}): {e_pub_user}')
                return None
        else: # private link
            if u: # User client (u) is necessary for private channels typically
                try:
                    # Ensure chat_id is integer for Pyrogram, starts with -100 for channels
                    chat_id_int = int(i) if str(i).lstrip('-').isdigit() else i
                    if isinstance(chat_id_int, int) and not str(chat_id_int).startswith('-100'):
                         chat_id_int = int(f"-100{chat_id_int}")


                    # No need to resolve_peer usually, get_messages handles usernames or IDs.
                    # However, if 'i' can be just the numerical part of a channel ID (without -100), adjust it.
                    # The E() function should return it with -100 already.
                    
                    # Warm up dialogs if necessary, but try direct fetch first
                    # await upd_dlg(u) # Can be slow
                    return await u.get_messages(chat_id_int, d)
                except Exception as e_priv:
                    print(f'Private channel error with user client ({chat_id_int}/{d}): {e_priv}')
                    # Attempt to explicitly get_chat then get_messages if direct fetch fails
                    try:
                        chat_obj = await u.get_chat(chat_id_int)
                        return await u.get_messages(chat_obj.id, d)
                    except Exception as e_priv_fallback:
                        print(f'Private channel fallback error ({chat_id_int}/{d}): {e_priv_fallback}')
                        return None
            else: # No user client provided for private link
                print(f"Cannot fetch private message ({i}/{d}): User client (u) not available.")
                return None
    except Exception as e_get_msg:
        print(f'Generic error in get_msg ({i}/{d}): {e_get_msg}')
        return None

async def get_ubot(uid: int) -> Optional[Client]: # User's own bot instance
    bt = await get_user_data_key(uid, "bot_token")
    if not bt: return None
    if uid in UB and UB[uid].is_connected: return UB[uid] # Check if connected
    
    # If exists but not connected, try to start it
    if uid in UB and not UB[uid].is_connected:
        try:
            await UB[uid].start()
            if UB[uid].is_connected:
                return UB[uid]
        except Exception as e_start_existing:
            print(f"Error re-starting existing bot for user {uid}: {e_start_existing}")
            # Fall through to create a new one if re-start fails, or remove from UB
            del UB[uid] # Remove if failed to restart

    try:
        # Using unique name for session file for user's bot
        bot = Client(f"user_bot_{uid}", bot_token=bt, api_id=API_ID, api_hash=API_HASH)
        await bot.start()
        UB[uid] = bot
        return bot
    except Exception as e:
        print(f"Error starting new bot for user {uid}: {e}")
        if uid in UB: del UB[uid] # Clean up if start failed
        return None

async def get_uclient(uid: int) -> Optional[Client]: # User's own user client instance
    # First check if a user's own bot (ubot) can do the job, if it's already cached
    ubot = UB.get(uid)
    if ubot and ubot.is_connected: # If user has their own bot and it's active
        # Decide if ubot is sufficient or if a user session is always preferred for certain actions
        # For restricted content, a user session (UC) is generally needed.
        pass # Fall through to check for full user client (UC)

    # Check for cached and connected user client (UC)
    cl = UC.get(uid)
    if cl and cl.is_connected: return cl

    # Attempt to start/restart user client if not connected or not found
    ud = await get_user_data(uid)
    if not ud: return ubot if ubot and ubot.is_connected else Y # Fallback to global userbot (Y) or ubot

    xxx_encrypted = ud.get('session_string')
    if xxx_encrypted:
        try:
            ss_decrypted = dcs(xxx_encrypted) # Decrypt session string
            # Using unique name for user's user client session
            user_client_instance = Client(f'user_client_{uid}', api_id=API_ID, api_hash=API_HASH, device_model="v3saver_UserClient", session_string=ss_decrypted)
            await user_client_instance.start()
            # await upd_dlg(user_client_instance) # Optional dialog warming
            UC[uid] = user_client_instance
            return user_client_instance
        except Exception as e_uclient:
            print(f'User client ({uid}) start/load error: {e_uclient}')
            # If user client fails, fallback to user's bot (if active) or global userbot Y
            return ubot if ubot and ubot.is_connected else Y
    
    # No session string found, fallback to ubot or Y
    return ubot if ubot and ubot.is_connected else Y


async def prog(current, total, client_to_edit_message, chat_id_of_progress_message, message_id_of_progress_message, start_time_of_upload):
    # client_to_edit_message: The Pyrogram client instance that sent the progress message
    # chat_id_of_progress_message: Chat where the progress message is
    # message_id_of_progress_message: ID of the message to edit
    # start_time_of_upload: time.time() when upload started
    
    global P # P is used to track previous percentage to reduce edits
    
    # Use a unique key for P, e.g., combining chat_id and message_id
    progress_key = f"{chat_id_of_progress_message}_{message_id_of_progress_message}"

    p = current / total * 100
    
    # Determine edit interval based on total size or fixed percentage steps
    interval_percent_step = 5 # Edit every 5%
    # More sophisticated: larger step for larger files, or time-based interval
    
    # Calculate current step based on percentage
    current_percent_step = int(p // interval_percent_step) * interval_percent_step

    if progress_key not in P or P[progress_key] != current_percent_step or p >= 100:
        P[progress_key] = current_percent_step
        
        c_mb = current / (1024 * 1024)
        t_mb = total / (1024 * 1024)
        bar = '🟢' * int(p / 10) + '🔴' * (10 - int(p / 10))
        
        elapsed_time = time.time() - start_time_of_upload
        speed_bytes_per_sec = current / elapsed_time if elapsed_time > 0 else 0
        speed_mb_per_sec = speed_bytes_per_sec / (1024 * 1024)
        
        eta_seconds = (total - current) / speed_bytes_per_sec if speed_bytes_per_sec > 0 else 0
        eta_formatted = time.strftime('%M:%S', time.gmtime(eta_seconds))
        
        progress_text = (
            f"__**Pyro Handler Uploading...**__\n\n"
            f"{bar}\n\n"
            f"⚡**__Completed__**: {c_mb:.2f} MB / {t_mb:.2f} MB\n"
            f"📊 **__Done__**: {p:.2f}%\n"
            f"🚀 **__Speed__**: {speed_mb_per_sec:.2f} MB/s\n"
            f"⏳ **__ETA__**: {eta_formatted}\n\n"
            f"**__Powered by Team SPY__**"
        )
        try:
            await client_to_edit_message.edit_message_text(chat_id_of_progress_message, message_id_of_progress_message, progress_text)
        except Exception as e_prog_edit:
            print(f"Error editing progress message: {e_prog_edit}")
            # If editing fails (e.g. message deleted), remove from P to stop trying
            P.pop(progress_key, None)

        if p >= 100:
            P.pop(progress_key, None) # Clean up when done


async def send_direct(c: Client, m: Message, tcid: int, ft: Optional[str] = None, rtmid: Optional[int] = None) -> bool:
    # c: Client to send with, m: source Message, tcid: target chat_id, ft: formatted text, rtmid: reply_to_message_id
    try:
        caption_to_send = ft if ft and (m.video or m.audio or m.photo or m.document) else None

        if m.video:
            await c.send_video(tcid, m.video.file_id, caption=caption_to_send, 
                               duration=m.video.duration, width=m.video.width, height=m.video.height, 
                               reply_to_message_id=rtmid)
        elif m.video_note: # Video notes don't have captions
            await c.send_video_note(tcid, m.video_note.file_id, reply_to_message_id=rtmid)
        elif m.voice: # Voice messages don't have captions
            await c.send_voice(tcid, m.voice.file_id, reply_to_message_id=rtmid)
        elif m.sticker:
            await c.send_sticker(tcid, m.sticker.file_id, reply_to_message_id=rtmid)
        elif m.audio:
            await c.send_audio(tcid, m.audio.file_id, caption=caption_to_send, 
                               duration=m.audio.duration, performer=m.audio.performer, title=m.audio.title, 
                               reply_to_message_id=rtmid)
        elif m.photo:
            # Pyrogram message.photo is a Photo object, not a list, if it's a single photo.
            # If it could be a list (e.g. from media group), handle accordingly.
            # Assuming m.photo is a Photo object.
            await c.send_photo(tcid, m.photo.file_id, caption=caption_to_send, reply_to_message_id=rtmid)
        elif m.document:
            await c.send_document(tcid, m.document.file_id, caption=caption_to_send, 
                                  file_name=m.document.file_name, reply_to_message_id=rtmid)
        # Consider other media types like animation, game, poll, etc. if needed.
        else:
            # If it's a text message or unhandled media type that needs direct forwarding of text
            if m.text: # Handle text messages if send_direct is also for text
                 await c.send_message(tcid, text=m.text.markdown if m.text else "", reply_to_message_id=rtmid) # Send markdown for entities
                 return True
            return False # Unhandled media type or no media
        return True
    except Exception as e:
        print(f'Direct send error to {tcid}: {e}')
        return False


async def process_msg(bot_client: Client, user_client: Optional[Client], source_msg: Message, 
                      target_chat_id_user_perspective: str, # This is the chat_id of the user running the command
                      link_type: str, user_id_of_commander: int, 
                      source_chat_identifier: Any) -> str: # chat_id/username of the source channel
    # bot_client: The bot's own Pyrogram client (X or a user-specific bot UB[uid])
    # user_client: The commander's user session (UC[uid] or global Y) or None
    # source_msg: The Message object from the source channel
    # target_chat_id_user_perspective: Where the final message should appear for the user (e.g., their PM with the bot)
    # link_type: 'public' or 'private'
    # user_id_of_commander: The user ID who initiated this process
    # source_chat_identifier: The ID or username of the channel/group where source_msg is from
    
    try:
        # Determine target chat and reply_to_message_id based on user's settings
        raw_chat_setting = await get_user_data_key(user_id_of_commander, 'chat_id')
        final_target_chat_id: int = int(target_chat_id_user_perspective) # Default to user's PM with bot
        final_reply_to_message_id: Optional[int] = None

        if raw_chat_setting:
            if '/' in str(raw_chat_setting):
                parts = str(raw_chat_setting).split('/', 1)
                try:
                    final_target_chat_id = int(parts[0])
                    final_reply_to_message_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                except ValueError:
                    print(f"Warning: Invalid chat_id setting '{raw_chat_setting}' for user {user_id_of_commander}. Defaulting to PM.")
                    final_target_chat_id = int(target_chat_id_user_perspective) # Fallback
            else:
                try:
                    final_target_chat_id = int(raw_chat_setting)
                except ValueError:
                    print(f"Warning: Invalid chat_id setting '{raw_chat_setting}' for user {user_id_of_commander}. Defaulting to PM.")
                    final_target_chat_id = int(target_chat_id_user_perspective) # Fallback
        
        if source_msg.media:
            original_caption = source_msg.caption.markdown if source_msg.caption and source_msg.caption.markdown else \
                               (source_msg.caption if source_msg.caption else "") # Handle None caption
            
            processed_caption_rules = await process_text_with_rules(user_id_of_commander, original_caption)
            user_custom_caption = await get_user_data_key(user_id_of_commander, 'caption', '')
            
            final_caption = f'{processed_caption_rules}\n\n{user_custom_caption}'.strip() \
                if processed_caption_rules and user_custom_caption else \
                (user_custom_caption or processed_caption_rules)

            # Condition for direct send (e.g. from public channel, no modification needed, or if file is small)
            # emp.get(source_chat_identifier, False) seems to be a cache for "is channel empty/inaccessible by bot"
            if link_type == 'public' and not emp.get(source_chat_identifier, False):
                if await send_direct(bot_client, source_msg, final_target_chat_id, final_caption, final_reply_to_message_id):
                    return 'Sent directly (public, bot access).'
            
            # If direct send failed or not applicable, proceed with download-upload
            # Choose download client: user_client if available and needed (e.g. restricted), else bot_client.
            # For private links, user_client is essential. For public, bot_client might work or user_client as fallback.
            downloader_client = user_client if user_client else bot_client # Prefer user_client for download if available

            if not downloader_client: # Should not happen if logic is correct
                 return "Error: No suitable client to download."

            progress_msg = await bot_client.send_message(target_chat_id_user_perspective, 'Downloading source media...')
            start_time_download = time.time()
            
            # Using Pyrogram's download_media which needs the message object itself
            downloaded_file_path = await downloader_client.download_media(
                message=source_msg,
                progress=prog, # Assuming prog is compatible with Pyrogram's progress callback
                progress_args=(bot_client, progress_msg.chat.id, progress_msg.id, start_time_download)
            )
                
            if not downloaded_file_path or not os.path.exists(str(downloaded_file_path)):
                await bot_client.edit_message_text(progress_msg.chat.id, progress_msg.id, 'Download failed.')
                return 'Download failed.'
            
            await bot_client.edit_message_text(progress_msg.chat.id, progress_msg.id, 'Renaming (if needed)...')
            
            # Rename file based on settings
            # rename_file expects sender_id (user_id_of_commander) and progress_msg (for edits)
            renamed_file_path = await rename_file(str(downloaded_file_path), user_id_of_commander, progress_msg)
            
            file_size_gb = os.path.getsize(renamed_file_path) / (1024 * 1024 * 1024)
            
            # Get thumbnail path from user settings for the commander
            custom_thumb_path = thumbnail(str(user_id_of_commander)) # func.thumbnail expects string sender_id

            upload_client = bot_client # Upload usually via the main bot client (X or UB)
            
            # Large file handling (using global userbot Y if file > 2GB and Y is configured)
            if file_size_gb > 1.9 and Y and Y.is_connected: # Pyrogram uses 2GB limit typically, use 1.9 as buffer
                await bot_client.edit_message_text(progress_msg.chat.id, progress_msg.id, 'File > 2GB. Using premium userbot (Y) to upload to LOG_GROUP first...')
                
                # await upd_dlg(Y) # Optional dialog warming for Y
                video_meta = await get_video_metadata(renamed_file_path) # from utils.func
                duration, height, width = video_meta['duration'], video_meta['height'], video_meta['width']
                
                # Use custom_thumb_path if set, else generate screenshot
                thumb_for_upload = custom_thumb_path if custom_thumb_path else await screenshot(renamed_file_path, duration, str(user_id_of_commander))
                
                start_time_upload_Y = time.time()
                # Upload to LOG_GROUP using Y
                # Determine media type for Y.send_XYZ
                # This logic is complex and needs to map source_msg.media_type to Y.send_ functions
                # Simplified: try sending as video if it's a video, else as document.
                sent_to_log_group = None
                if source_msg.video or renamed_file_path.lower().endswith(('.mp4', '.mkv', '.webm')):
                    sent_to_log_group = await Y.send_video(LOG_GROUP, renamed_file_path, thumb=thumb_for_upload,
                                          caption=final_caption, duration=duration, width=width, height=height,
                                          reply_to_message_id=None, # No reply in log group usually
                                          progress=prog, 
                                          progress_args=(bot_client, progress_msg.chat.id, progress_msg.id, start_time_upload_Y))
                else: # Fallback to document or specific types
                    sent_to_log_group = await Y.send_document(LOG_GROUP, renamed_file_path, thumb=thumb_for_upload, 
                                                 caption=final_caption, reply_to_message_id=None,
                                                 progress=prog,
                                                 progress_args=(bot_client, progress_msg.chat.id, progress_msg.id, start_time_upload_Y))

                if sent_to_log_group:
                    # Forward from LOG_GROUP to the final target
                    await bot_client.copy_message(final_target_chat_id, LOG_GROUP, sent_to_log_group.id, 
                                             reply_to_message_id=final_reply_to_message_id)
                    await bot_client.delete_messages(progress_msg.chat.id, progress_msg.id) # Delete "Downloading..." etc.
                    if os.path.exists(renamed_file_path): os.remove(renamed_file_path)
                    if thumb_for_upload and not custom_thumb_path and os.path.exists(thumb_for_upload): os.remove(thumb_for_upload) # remove generated thumb
                    return 'Done (Large file via Y).'
                else:
                    await bot_client.edit_message_text(progress_msg.chat.id, progress_msg.id, 'Failed to upload large file with Y.')
                    if os.path.exists(renamed_file_path): os.remove(renamed_file_path)
                    return 'Failed (Large file via Y).'

            # Regular upload if not large file or Y not available
            await bot_client.edit_message_text(progress_msg.chat.id, progress_msg.id, 'Uploading to target...')
            start_time_upload_bot = time.time()

            video_meta_bot = await get_video_metadata(renamed_file_path)
            duration_bot, height_bot, width_bot = video_meta_bot['duration'], video_meta_bot['height'], video_meta_bot['width']
            thumb_for_bot_upload = custom_thumb_path if custom_thumb_path else await screenshot(renamed_file_path, duration_bot, str(user_id_of_commander))

            try:
                # Match media type for sending
                if source_msg.video or renamed_file_path.lower().endswith(('.mp4', '.mkv', '.webm')):
                    await upload_client.send_video(final_target_chat_id, video=renamed_file_path, caption=final_caption,
                                         thumb=thumb_for_bot_upload, width=width_bot, height=height_bot, duration=duration_bot,
                                         progress=prog, progress_args=(bot_client, progress_msg.chat.id, progress_msg.id, start_time_upload_bot),
                                         reply_to_message_id=final_reply_to_message_id)
                elif source_msg.audio or renamed_file_path.lower().endswith(('.mp3', '.ogg', '.wav', '.flac')):
                     # Pyrogram needs performer and title for audio if available from source_msg.audio
                    performer = source_msg.audio.performer if source_msg.audio else None
                    title = source_msg.audio.title if source_msg.audio else os.path.basename(renamed_file_path)
                    audio_duration = source_msg.audio.duration if source_msg.audio else 0 # Get duration from source if possible
                    
                    await upload_client.send_audio(final_target_chat_id, audio=renamed_file_path, caption=final_caption,
                                         thumb=thumb_for_bot_upload, # Thumb for audio is possible
                                         duration=audio_duration, performer=performer, title=title,
                                         progress=prog, progress_args=(bot_client, progress_msg.chat.id, progress_msg.id, start_time_upload_bot),
                                         reply_to_message_id=final_reply_to_message_id)
                elif source_msg.photo: # Assuming single photo. If media group, this needs more complex handling.
                    await upload_client.send_photo(final_target_chat_id, photo=renamed_file_path, caption=final_caption,
                                         progress=prog, progress_args=(bot_client, progress_msg.chat.id, progress_msg.id, start_time_upload_bot),
                                         reply_to_message_id=final_reply_to_message_id)
                # Add other types like video_note, voice, sticker based on source_msg
                elif source_msg.document or True: # Default to document
                    doc_filename = source_msg.document.file_name if source_msg.document else os.path.basename(renamed_file_path)
                    await upload_client.send_document(final_target_chat_id, document=renamed_file_path, caption=final_caption,
                                            thumb=thumb_for_bot_upload, file_name=doc_filename, # file_name is important for documents
                                            progress=prog, progress_args=(bot_client, progress_msg.chat.id, progress_msg.id, start_time_upload_bot),
                                            reply_to_message_id=final_reply_to_message_id)

            except Exception as e_upload:
                await bot_client.edit_message_text(progress_msg.chat.id, progress_msg.id, f'Upload failed: {str(e_upload)[:100]}')
                if os.path.exists(renamed_file_path): os.remove(renamed_file_path)
                if thumb_for_bot_upload and not custom_thumb_path and os.path.exists(thumb_for_bot_upload): os.remove(thumb_for_bot_upload)
                return f'Upload failed: {str(e_upload)[:50]}'
            
            if os.path.exists(renamed_file_path): os.remove(renamed_file_path)
            if thumb_for_bot_upload and not custom_thumb_path and os.path.exists(thumb_for_bot_upload): os.remove(thumb_for_bot_upload)
            await bot_client.delete_messages(progress_msg.chat.id, progress_msg.id)
            return 'Done.'
            
        elif source_msg.text: # Handle text messages
            # Apply text processing rules if any for text messages too
            processed_text = await process_text_with_rules(user_id_of_commander, source_msg.text.markdown)
            user_custom_caption_for_text = await get_user_data_key(user_id_of_commander, 'caption', '') # Re-evaluate if 'caption' applies to text messages
            
            final_text_to_send = f'{processed_text}\n\n{user_custom_caption_for_text}'.strip() \
                if processed_text and user_custom_caption_for_text else \
                (user_custom_caption_for_text or processed_text)

            await bot_client.send_message(final_target_chat_id, text=final_text_to_send, reply_to_message_id=final_reply_to_message_id)
            return 'Text message sent.'
        else:
            return "Unsupported message type or empty message."
            
    except Exception as e_proc:
        # Attempt to clean up progress message if it exists
        if 'progress_msg' in locals() and progress_msg:
            try:
                await bot_client.edit_message_text(progress_msg.chat.id, progress_msg.id, f'Error: {str(e_proc)[:100]}')
            except: pass # Ignore errors editing progress message on final error
        print(f"Error in process_msg: {e_proc}")
        return f'Error: {str(e_proc)[:50]}'

@X.on_message(filters.command(['batch', 'single']))
async def process_cmd(c: Client, m: Message): # c is X (main bot client)
    uid = m.from_user.id
    cmd = m.command[0]
    
    if FREEMIUM_LIMIT == 0 and not await is_premium_user(uid):
        await m.reply_text("This bot does not provide free services, get subscription from OWNER")
        return
    
    if await sub(c, m) == 1: return # Force subscribe check
    
    pro = await m.reply_text('Performing initial checks...')
    
    if is_user_active(uid):
        await pro.edit('You have an active task. Use /cancel or /stop to cancel it before starting a new one.')
        return
    
    # Ensure user has a bot_token set for /setbot, as get_ubot will try to use it
    user_bot_token = await get_user_data_key(uid, "bot_token")
    if not user_bot_token:
        await pro.edit('You need to add your bot token first using /setbot command.')
        return

    # Check if the user's bot (ubot) can be started/is active
    ubot = await get_ubot(uid) # This will attempt to start the user's bot if not active
    if not ubot or not ubot.is_connected:
        await pro.edit('Failed to start/activate your bot (from /setbot). Please check your token or try /setbot again.')
        Z.pop(uid, None) # Clear any pending state for this user
        return
    
    Z[uid] = {'step': 'start' if cmd == 'batch' else 'start_single'}
    await pro.edit(f'Send the {"start link of the batch..." if cmd == "batch" else "link of the single message to process"}.')


@X.on_message(filters.command(['cancel', 'stop']))
async def cancel_cmd(c: Client, m: Message):
    uid = m.from_user.id
    
    # Cancel batch/single processing if active
    if is_user_active(uid):
        if await request_batch_cancel(uid): # This sets a flag
            await m.reply_text('Cancellation requested. The current process will stop shortly.')
            # The running batch/single loop needs to check should_cancel(uid)
        else:
            # This case (request_batch_cancel returning False) shouldn't happen if is_user_active is true.
            await m.reply_text('Failed to request cancellation (user not found in active list). This is unexpected.')
    else:
        await m.reply_text('No active batch/single process found to cancel.')

    # Also cancel any pending input step via Z dictionary (e.g., waiting for link or count)
    if uid in Z:
        Z.pop(uid, None)
        await m.reply_text('Any pending input steps have also been cleared.')
        # No active process, but maybe was waiting for input.


# Adjusted filter for text_handler to avoid conflicts with other command handlers
# It should only trigger if a user is in a Z state (multi-step command like batch/single)
# And the message is not another command.
async def z_state_filter(_, __, message: Message):
    if message.from_user and message.from_user.id in Z and message.text:
        # Ensure it's not a command starting with / unless it's part of the expected input
        # This check might be too simple if commands can be part of valid input text
        # For now, if in Z state, and it's text, assume it's for the current step.
        return not message.text.startswith('/')
    return False

custom_z_state_filter = filters.create(z_state_filter)

@X.on_message(custom_z_state_filter & filters.text & filters.private & ~login_in_progress)
async def text_handler(c: Client, m: Message): # c is X (main bot client)
    uid = m.from_user.id
    # uid check already in custom_z_state_filter, but good for safety
    if uid not in Z: return 
    
    s = Z[uid].get('step')
    current_bot_for_user = await get_ubot(uid) # This is the user's configured bot
    if not current_bot_for_user or not current_bot_for_user.is_connected:
        await m.reply_text("Your personal bot (from /setbot) is not active. Please use /setbot again.")
        Z.pop(uid, None)
        return

    if s == 'start': # Waiting for start link for batch
        L = m.text
        i, d, lt = E(L) # E extracts (chat_id/username, message_id, link_type)
        if not i or not d:
            await m.reply_text('Invalid link format for batch start. Please send a valid Telegram message link.')
            Z.pop(uid, None)
            return
        Z[uid].update({'step': 'count', 'cid': i, 'sid': d, 'lt': lt})
        await m.reply_text('Link received. Now, how many messages do you want to process in this batch?')

    elif s == 'start_single': # Waiting for link for single message processing
        L = m.text
        i, d_single, lt_single = E(L)
        if not i or not d_single:
            await m.reply_text('Invalid link format for single message. Please send a valid Telegram message link.')
            Z.pop(uid, None)
            return

        # For single message, process immediately
        # Z[uid].update({'step': 'process_single', 'cid': i, 'sid': d_single, 'lt': lt_single})
        # No need to update Z if processing is done here. Clear Z for this user.
        
        cid_single, start_msg_id_single, link_type_single = i, d_single, lt_single
        
        pt_single = await m.reply_text(f'Processing single message: {L}')
        
        # ubot is current_bot_for_user
        # uc is the user's own client session for accessing restricted content
        uc_single = await get_uclient(uid) # This will fallback to Y (global userbot) if user has no session
        
        if not uc_single and link_type_single == 'private':
            await pt_single.edit('Cannot process private link without a user session. Please /login with your user account.')
            Z.pop(uid, None)
            return
        
        # Check if another task is active for this user (should have been caught by process_cmd, but double check)
        if is_user_active(uid):
            await pt_single.edit('Another task is already active. Please use /stop or /cancel first.')
            Z.pop(uid, None)
            return

        await add_active_batch(uid, { # Using batch mechanism for single too, for cancellation
            "total": 1, "current": 0, "success": 0, "cancel_requested": False, 
            "progress_message_id": pt_single.id, "type": "single"
        })

        try:
            msg_to_process = await get_msg(current_bot_for_user, uc_single, cid_single, start_msg_id_single, link_type_single)
            if msg_to_process:
                # process_msg args: bot_client, user_client, source_msg, target_chat_id_user_perspective, link_type, user_id_of_commander, source_chat_identifier
                res_single = await process_msg(current_bot_for_user, uc_single, msg_to_process, 
                                               str(m.chat.id), link_type_single, uid, cid_single)
                await pt_single.edit(f'Result (1/1): {res_single}')
                if "Done" in res_single or "Sent" in res_single:
                    await update_batch_progress(uid, 1,1) # Mark as success
            else:
                await pt_single.edit(f'Message not found at link: {L}')
        except Exception as e_single:
            await pt_single.edit(f'Error processing single message: {str(e_single)[:100]}')
        finally:
            await remove_active_batch(uid) # Clear active state
            Z.pop(uid, None) # Clear Z state

    elif s == 'count': # Waiting for number of messages for batch
        if not m.text.isdigit():
            await m.reply_text('Please enter a valid number for the message count.')
            # Z[uid]['step'] remains 'count' to await valid input
            return
        
        count = int(m.text)
        max_limit = PREMIUM_LIMIT if await is_premium_user(uid) else FREEMIUM_LIMIT

        if count <= 0:
            await m.reply_text('Number of messages must be greater than 0.')
            return
        if count > max_limit:
            await m.reply_text(f'Maximum batch limit is {max_limit}. You requested {count}.')
            # Z[uid]['step'] remains 'count' or pop Z to restart
            Z.pop(uid, None) # Or ask for new count
            return

        # Z[uid].update({'step': 'process_batch', 'did': str(m.chat.id), 'num': count})
        # Extract info from Z for batch processing
        cid_batch = Z[uid]['cid']
        start_msg_id_batch = Z[uid]['sid']
        num_messages_batch = count
        link_type_batch = Z[uid]['lt']
        target_display_chat_id = str(m.chat.id) # Where progress and final messages are shown

        # Clear Z state as we are proceeding with batch
        Z.pop(uid, None) 
        
        pt_batch = await m.reply_text(f'Starting batch process for {num_messages_batch} messages from message ID {start_msg_id_batch}...')
        
        uc_batch = await get_uclient(uid) # User client (session or Y)
        if not uc_batch and link_type_batch == 'private':
            await pt_batch.edit('Cannot process private links in batch without a user session. Please /login.')
            return

        if is_user_active(uid): # Should not happen if initial checks were done
            await pt_batch.edit('Another task is already active. This is an unexpected state.')
            return
        
        await add_active_batch(uid, {
            "total": num_messages_batch, "current": 0, "success": 0, 
            "cancel_requested": False, "progress_message_id": pt_batch.id, "type": "batch"
        })
        
        success_count_batch = 0
        try:
            for j in range(num_messages_batch):
                if should_cancel(uid):
                    await pt_batch.edit(f'Batch processing cancelled by user at {j+1}/{num_messages_batch}. Successfully processed: {success_count_batch}.')
                    break
                
                current_message_id_in_batch = int(start_msg_id_batch) + j
                await update_batch_progress(uid, j + 1, success_count_batch) # current is (j+1)th message
                
                # Update progress message for the user
                try:
                    await pt_batch.edit_text(f"Processing message {j+1}/{num_messages_batch} (ID: {current_message_id_in_batch})... Success: {success_count_batch}")
                except Exception: pass # Ignore if editing fails (e.g., rate limits)

                msg_to_process_batch = await get_msg(current_bot_for_user, uc_batch, cid_batch, current_message_id_in_batch, link_type_batch)
                
                if msg_to_process_batch:
                    res_batch = await process_msg(current_bot_for_user, uc_batch, msg_to_process_batch,
                                                  target_display_chat_id, link_type_batch, uid, cid_batch)
                    if "Done" in res_batch or "Sent" in res_batch: # Crude success check
                        success_count_batch += 1
                    # Log individual message result (optional, could be verbose)
                    # print(f"Batch ({uid}) msg {j+1}: {res_batch}")
                else:
                    # print(f"Batch ({uid}) msg {j+1} (ID: {current_message_id_in_batch}) not found or failed to fetch.")
                    pass # Optionally log this failure
                
                await asyncio.sleep(max(1, int(os.getenv("BATCH_SLEEP_INTERVAL", "5")))) # Configurable sleep, default 5s
            
            # Final message after loop finishes (or breaks due to cancellation)
            if not should_cancel(uid): # If not cancelled
                 await pt_batch.reply_text(f'Batch processing completed for {num_messages_batch} messages. Successfully processed: {success_count_batch}/{num_messages_batch}.')

        except Exception as e_batch:
            await pt_batch.reply_text(f'An error occurred during batch processing: {str(e_batch)[:100]}')
        finally:
            await remove_active_batch(uid) # Clear active state
            # Z should already be cleared for this user
            
    else: # Unknown step in Z, should not happen
        await m.reply_text("I'm confused about our current conversation. Please start over with a command.")
        Z.pop(uid, None)
