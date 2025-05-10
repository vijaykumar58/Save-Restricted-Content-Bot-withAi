import os
import re
import time
import asyncio
import json
from typing import Dict, Any, Optional, Tuple
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import UserNotParticipant
from config import (
    API_ID,
    API_HASH,
    LOG_GROUP,
    STRING,
    FORCE_SUB,
    FREEMIUM_LIMIT,
    PREMIUM_LIMIT
)
from utils.func import (
    get_user_data,
    screenshot,
    thumbnail,
    get_video_metadata,
    get_user_data_key,
    process_text_with_rules,
    is_premium_user,
    parse_telegram_link
)
from shared_client import app as X
from plugins.settings import rename_file
from plugins.start import subscribe as sub
from utils.custom_filters import login_in_progress
from utils.encrypt import dcs

# Initialize shared clients and state
Y = None if not STRING else __import__('shared_client').userbot
Z, P, UB, UC = {}, {}, {}, {}

# Batch processing state management
ACTIVE_USERS_FILE = "active_users.json"
ACTIVE_USERS = {}

class BatchManager:
    @staticmethod
    def load_active_users() -> Dict:
        """Load active users from file."""
        try:
            if os.path.exists(ACTIVE_USERS_FILE):
                with open(ACTIVE_USERS_FILE, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"Error loading active users: {e}")
            return {}

    @staticmethod
    async def save_active_users() -> None:
        """Save active users to file."""
        try:
            with open(ACTIVE_USERS_FILE, 'w') as f:
                json.dump(ACTIVE_USERS, f)
        except Exception as e:
            print(f"Error saving active users: {e}")

    @staticmethod
    async def add_active_batch(user_id: int, batch_info: Dict[str, Any]) -> None:
        """Add an active batch for a user."""
        ACTIVE_USERS[str(user_id)] = batch_info
        await BatchManager.save_active_users()

    @staticmethod
    def is_user_active(user_id: int) -> bool:
        """Check if user has an active batch."""
        return str(user_id) in ACTIVE_USERS

    @staticmethod
    async def update_batch_progress(user_id: int, current: int, success: int) -> None:
        """Update batch progress for a user."""
        if str(user_id) in ACTIVE_USERS:
            ACTIVE_USERS[str(user_id)]["current"] = current
            ACTIVE_USERS[str(user_id)]["success"] = success
            await BatchManager.save_active_users()

    @staticmethod
    async def request_batch_cancel(user_id: int) -> bool:
        """Request cancellation of a batch."""
        if str(user_id) in ACTIVE_USERS:
            ACTIVE_USERS[str(user_id)]["cancel_requested"] = True
            await BatchManager.save_active_users()
            return True
        return False

    @staticmethod
    def should_cancel(user_id: int) -> bool:
        """Check if batch should be cancelled."""
        user_str = str(user_id)
        return user_str in ACTIVE_USERS and ACTIVE_USERS[user_str].get("cancel_requested", False)

    @staticmethod
    async def remove_active_batch(user_id: int) -> None:
        """Remove an active batch."""
        if str(user_id) in ACTIVE_USERS:
            del ACTIVE_USERS[str(user_id)]
            await BatchManager.save_active_users()

    @staticmethod
    def get_batch_info(user_id: int) -> Optional[Dict[str, Any]]:
        """Get batch info for a user."""
        return ACTIVE_USERS.get(str(user_id))

class ClientManager:
    @staticmethod
    async def update_dialogs(client: Client) -> bool:
        """Update client dialogs."""
        try:
            async for _ in client.get_dialogs(limit=100):
                pass
            return True
        except Exception as e:
            print(f'Failed to update dialogs: {e}')
            return False

    @staticmethod
    async def get_message(
        client: Client,
        user_client: Optional[Client],
        chat_id: str,
        message_id: int,
        link_type: str
    ) -> Optional[Message]:
        """Get a message from a chat."""
        try:
            if link_type == 'public':
                try:
                    message = await client.get_messages(chat_id, message_id)
                    if getattr(message, "empty", False):
                        try:
                            await user_client.join_chat(chat_id)
                        except:
                            pass
                        chat = await user_client.get_chat(f"@{chat_id}")
                        message = await user_client.get_messages(chat.id, message_id)
                    return message
                except Exception as e:
                    print(f'Error fetching public message: {e}')
                    return None
            else:
                if not user_client:
                    return None
                    
                try:
                    await ClientManager.update_dialogs(user_client)
                    resolved_id = await ClientManager.resolve_chat_id(user_client, chat_id)
                    return await user_client.get_messages(resolved_id, message_id)
                except Exception as e:
                    print(f'Private channel error: {e}')
                    return None
        except Exception as e:
            print(f'Error fetching message: {e}')
            return None

    @staticmethod
    async def resolve_chat_id(client: Client, chat_id: str) -> str:
        """Resolve a chat ID to its proper format."""
        try:
            peer = await client.resolve_peer(chat_id)
            if hasattr(peer, 'channel_id'):
                return f'-100{peer.channel_id}'
            elif hasattr(peer, 'chat_id'):
                return f'-{peer.chat_id}'
            elif hasattr(peer, 'user_id'):
                return peer.user_id
            return chat_id
        except Exception:
            try:
                chat = await client.get_chat(chat_id)
                return chat.id
            except Exception:
                await ClientManager.update_dialogs(client)
                return chat_id

    @staticmethod
    async def get_user_bot(user_id: int) -> Optional[Client]:
        """Get or create a user bot client."""
        bot_token = await get_user_data_key(user_id, "bot_token", None)
        if not bot_token:
            return None
            
        if user_id in UB:
            return UB[user_id]
            
        try:
            bot = Client(
                f"user_{user_id}",
                bot_token=bot_token,
                api_id=API_ID,
                api_hash=API_HASH
            )
            await bot.start()
            UB[user_id] = bot
            return bot
        except Exception as e:
            print(f"Error starting bot for user {user_id}: {e}")
            return None

    @staticmethod
    async def get_user_client(user_id: int) -> Optional[Client]:
        """Get or create a user client."""
        # Check cached client
        if user_id in UC:
            return UC[user_id]
            
        # Get user data
        user_data = await get_user_data(user_id)
        if not user_data:
            return await ClientManager.get_user_bot(user_id) or Y
            
        # Try to create from session string
        session_string = user_data.get('session_string')
        if session_string:
            try:
                decrypted_session = dcs(session_string)
                client = Client(
                    f'{user_id}_client',
                    api_id=API_ID,
                    api_hash=API_HASH,
                    device_model="v3saver",
                    session_string=decrypted_session
                )
                await client.start()
                await ClientManager.update_dialogs(client)
                UC[user_id] = client
                return client
            except Exception as e:
                print(f'User client error: {e}')
                return await ClientManager.get_user_bot(user_id) or Y
                
        return await ClientManager.get_user_bot(user_id) or Y

class ProgressManager:
    @staticmethod
    async def update_progress(
        client: Client,
        total: int,
        current: int,
        chat_id: int,
        message_id: int,
        start_time: float
    ) -> None:
        """Update progress message."""
        progress = current / total * 100
        interval = (
            10 if total >= 100 * 1024 * 1024 else
            20 if total >= 50 * 1024 * 1024 else
            30 if total >= 10 * 1024 * 1024 else
            50
        )
        step = int(progress // interval) * interval
        
        if message_id not in P or P[message_id] != step or progress >= 100:
            P[message_id] = step
            
            current_mb = current / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            bar = '🟢' * int(progress / 10) + '🔴' * (10 - int(progress / 10))
            
            elapsed = time.time() - start_time
            speed = current / elapsed / (1024 * 1024) if elapsed > 0 else 0
            eta = time.strftime(
                '%M:%S',
                time.gmtime((total - current) / (speed * 1024 * 1024))
            ) if speed > 0 else '00:00'
            
            text = (
                f"__**Pyro Handler...**__\n\n{bar}\n\n"
                f"⚡**__Completed__**: {current_mb:.2f} MB / {total_mb:.2f} MB\n"
                f"📊 **__Done__**: {progress:.2f}%\n"
                f"🚀 **__Speed__**: {speed:.2f} MB/s\n"
                f"⏳ **__ETA__**: {eta}\n\n"
                f"**__Powered by Team SPY__**"
            )
            
            try:
                await client.edit_message_text(chat_id, message_id, text)
                if progress >= 100:
                    P.pop(message_id, None)
            except Exception as e:
                print(f"Error updating progress: {e}")

class MessageProcessor:
    @staticmethod
    async def send_direct(
        client: Client,
        message: Message,
        target_chat_id: int,
        formatted_text: Optional[str] = None,
        reply_to_message_id: Optional[int] = None
    ) -> bool:
        """Send a message directly to target chat."""
        try:
            if message.video:
                await client.send_video(
                    target_chat_id,
                    message.video.file_id,
                    caption=formatted_text,
                    duration=message.video.duration,
                    width=message.video.width,
                    height=message.video.height,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.video_note:
                await client.send_video_note(
                    target_chat_id,
                    message.video_note.file_id,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.voice:
                await client.send_voice(
                    target_chat_id,
                    message.voice.file_id,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.sticker:
                await client.send_sticker(
                    target_chat_id,
                    message.sticker.file_id,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.audio:
                await client.send_audio(
                    target_chat_id,
                    message.audio.file_id,
                    caption=formatted_text,
                    duration=message.audio.duration,
                    performer=message.audio.performer,
                    title=message.audio.title,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.photo:
                photo_id = (
                    message.photo.file_id if hasattr(message.photo, 'file_id')
                    else message.photo[-1].file_id
                )
                await client.send_photo(
                    target_chat_id,
                    photo_id,
                    caption=formatted_text,
                    reply_to_message_id=reply_to_message_id
                )
            elif message.document:
                await client.send_document(
                    target_chat_id,
                    message.document.file_id,
                    caption=formatted_text,
                    file_name=message.document.file_name,
                    reply_to_message_id=reply_to_message_id
                )
            else:
                return False
            return True
        except Exception as e:
            print(f'Direct send error: {e}')
            return False

    @staticmethod
    async def process_message(
        client: Client,
        user_client: Client,
        message: Message,
        user_id: int,
        chat_id: str,
        message_id: int,
        link_type: str,
        target_chat_id: int
    ) -> str:
        """Process a single message."""
        try:
            # Get target chat configuration
            cfg_chat = await get_user_data_key(user_id, 'chat_id', None)
            reply_to_id = None
            
            if cfg_chat and '/' in cfg_chat:
                parts = cfg_chat.split('/', 1)
                target_chat_id = int(parts[0])
                reply_to_id = int(parts[1]) if len(parts) > 1 else None
            
            # Handle text messages
            if not message.media:
                await client.send_message(
                    target_chat_id,
                    text=message.text.markdown,
                    reply_to_message_id=reply_to_id
                )
                return 'Sent.'
            
            # Process media messages
            original_text = message.caption.markdown if message.caption else ''
            processed_text = await process_text_with_rules(user_id, original_text)
            user_caption = await get_user_data_key(user_id, 'caption', '')
            
            final_text = (
                f'{processed_text}\n\n{user_caption}' if processed_text and user_caption
                else user_caption if user_caption
                else processed_text
            )
            
            # Try direct send for public channels
            if link_type == 'public' and not getattr(message, "empty", False):
                if await MessageProcessor.send_direct(
                    client,
                    message,
                    target_chat_id,
                    final_text,
                    reply_to_id
                ):
                    return 'Sent directly.'
            
            # Download and process media
            progress_msg = await client.send_message(user_id, 'Downloading...')
            start_time = time.time()
            
            try:
                file_path = await user_client.download_media(
                    message,
                    progress=ProgressManager.update_progress,
                    progress_args=(
                        client,
                        user_id,
                        progress_msg.id,
                        start_time
                    )
                )
                
                if not file_path:
                    await client.edit_message_text(
                        user_id,
                        progress_msg.id,
                        'Failed to download.'
                    )
                    return 'Download failed.'
                
                # Rename file if needed
                await client.edit_message_text(user_id, progress_msg.id, 'Renaming...')
                if any([
                    (message.video and message.video.file_name),
                    (message.audio and message.audio.file_name),
                    (message.document and message.document.file_name)
                ]):
                    file_path = await rename_file(file_path, user_id, progress_msg)
                
                file_size = os.path.getsize(file_path)
                thumb = thumbnail(user_id)
                
                # Handle large files (>2GB)
                if file_size > 2 * 1024 * 1024 * 1024 and Y:
                    await client.edit_message_text(
                        user_id,
                        progress_msg.id,
                        'File is larger than 2GB. Using alternative method...'
                    )
                    
                    await ClientManager.update_dialogs(Y)
                    metadata = await get_video_metadata(file_path)
                    thumb = await screenshot(
                        file_path,
                        metadata['duration'],
                        user_id
                    )
                    
                    # Determine media type and send accordingly
                    media_type = None
                    if file_path.endswith('.mp4'):
                        media_type = 'video'
                    elif message.video_note:
                        media_type = 'video_note'
                    elif message.voice:
                        media_type = 'voice'
                    elif message.audio:
                        media_type = 'audio'
                    elif message.photo:
                        media_type = 'photo'
                    else:
                        media_type = 'document'
                    
                    # Send to log group first
                    send_method = getattr(Y, f'send_{media_type}', Y.send_document)
                    sent_message = await send_method(
                        LOG_GROUP,
                        file_path,
                        thumb=thumb if media_type == 'video' else None,
                        duration=metadata['duration'] if media_type == 'video' else None,
                        height=metadata['height'] if media_type == 'video' else None,
                        width=metadata['width'] if media_type == 'video' else None,
                        caption=final_text if message.caption and media_type not in ['video_note', 'voice'] else None,
                        reply_to_message_id=reply_to_id,
                        progress=ProgressManager.update_progress,
                        progress_args=(
                            client,
                            user_id,
                            progress_msg.id,
                            start_time
                        )
                    )
                    
                    # Copy to target chat
                    await client.copy_message(
                        target_chat_id,
                        LOG_GROUP,
                        sent_message.id
                    )
                    
                    # Cleanup
                    os.remove(file_path)
                    await client.delete_messages(user_id, progress_msg.id)
                    
                    return 'Done (Large file).'
                
                # Upload normally for smaller files
                await client.edit_message_text(user_id, progress_msg.id, 'Uploading...')
                
                if message.video or os.path.splitext(file_path)[1].lower() == '.mp4':
                    metadata = await get_video_metadata(file_path)
                    thumb = await screenshot(
                        file_path,
                        metadata['duration'],
                        user_id
                    )
                    
                    await client.send_video(
                        target_chat_id,
                        video=file_path,
                        caption=final_text if message.caption else None,
                        thumb=thumb,
                        width=metadata['width'],
                        height=metadata['height'],
                        duration=metadata['duration'],
                        progress=ProgressManager.update_progress,
                        progress_args=(
                            client,
                            user_id,
                            progress_msg.id,
                            start_time
                        ),
                        reply_to_message_id=reply_to_id
                    )
                elif message.video_note:
                    await client.send_video_note(
                        target_chat_id,
                        video_note=file_path,
                        progress=ProgressManager.update_progress,
                        progress_args=(
                            client,
                            user_id,
                            progress_msg.id,
                            start_time
                        ),
                        reply_to_message_id=reply_to_id
                    )
                elif message.voice:
                    await client.send_voice(
                        target_chat_id,
                        voice=file_path,
                        progress=ProgressManager.update_progress,
                        progress_args=(
                            client,
                            user_id,
                            progress_msg.id,
                            start_time
                        ),
                        reply_to_message_id=reply_to_id
                    )
                elif message.sticker:
                    await client.send_sticker(
                        target_chat_id,
                        message.sticker.file_id
                    )
                elif message.audio:
                    await client.send_audio(
                        target_chat_id,
                        audio=file_path,
                        caption=final_text if message.caption else None,
                        thumb=thumb,
                        progress=ProgressManager.update_progress,
                        progress_args=(
                            client,
                            user_id,
                            progress_msg.id,
                            start_time
                        ),
                        reply_to_message_id=reply_to_id
                    )
                elif message.photo:
                    await client.send_photo(
                        target_chat_id,
                        photo=file_path,
                        caption=final_text if message.caption else None,
                        progress=ProgressManager.update_progress,
                        progress_args=(
                            client,
                            user_id,
                            progress_msg.id,
                            start_time
                        ),
                        reply_to_message_id=reply_to_id
                    )
                else:
                    await client.send_document(
                        target_chat_id,
                        document=file_path,
                        caption=final_text if message.caption else None,
                        progress=ProgressManager.update_progress,
                        progress_args=(
                            client,
                            user_id,
                            progress_msg.id,
                            start_time
                        ),
                        reply_to_message_id=reply_to_id
                    )
                
                # Cleanup
                os.remove(file_path)
                await client.delete_messages(user_id, progress_msg.id)
                
                return 'Done.'
                
            except Exception as e:
                await client.edit_message_text(
                    user_id,
                    progress_msg.id,
                    f'Upload failed: {str(e)[:30]}'
                )
                if os.path.exists(file_path):
                    os.remove(file_path)
                return 'Failed.'
                
        except Exception as e:
            return f'Error: {str(e)[:50]}'

# Initialize active users
ACTIVE_USERS = BatchManager.load_active_users()

# Command Handlers
@X.on_message(filters.command(['batch', 'single']))
async def handle_batch_command(client: Client, message: Message) -> None:
    """Handle /batch and /single commands."""
    user_id = message.from_user.id
    command = message.command[0]
    
    # Check if service is available for free users
    if FREEMIUM_LIMIT == 0 and not await is_premium_user(user_id):
        await message.reply_text(
            "This bot does not provide free services. Get a subscription from OWNER"
        )
        return
    
    # Check force subscription
    if await sub(client, message) == 1:
        return
    
    progress_msg = await message.reply_text('Doing some checks, please wait...')
    
    # Check for active tasks
    if BatchManager.is_user_active(user_id):
        await progress_msg.edit('You have an active task. Use /stop to cancel it.')
        return
    
    # Check if user has a bot set up
    user_bot = await ClientManager.get_user_bot(user_id)
    if not user_bot:
        await progress_msg.edit('Please add your bot with /setbot first')
        return
    
    # Initialize batch state
    Z[user_id] = {
        'step': 'start' if command == 'batch' else 'start_single',
        'client': user_bot
    }
    
    await progress_msg.edit(
        f"Send {'the start link...' if command == 'batch' else 'the link to process'}"
    )

@X.on_message(filters.command(['cancel', 'stop']))
async def handle_cancel_command(client: Client, message: Message) -> None:
    """Handle /cancel and /stop commands."""
    user_id = message.from_user.id
    
    if BatchManager.is_user_active(user_id):
        if await BatchManager.request_batch_cancel(user_id):
            await message.reply_text(
                'Cancellation requested. The current batch will stop after '
                'the current download completes.'
            )
        else:
            await message.reply_text(
                'Failed to request cancellation. Please try again.'
            )
    else:
        await message.reply_text('No active batch process found.')

@X.on_message(
    filters.text &
    filters.private &
    ~login_in_progress &
    ~filters.command([
        'start', 'batch', 'cancel', 'login', 'logout', 'stop', 'set', 
        'pay', 'redeem', 'gencode', 'single', 'generate', 'keyinfo', 
        'encrypt', 'decrypt', 'keys', 'setbot', 'rembot'
    ])
)
async def handle_text_message(client: Client, message: Message) -> None:
    """Handle text messages during batch processing."""
    user_id = message.from_user.id
    if user_id not in Z:
        return
        
    state = Z[user_id].get('step')
    text = message.text.strip()
    
    if state == 'start' or state == 'start_single':
        # Parse the Telegram link
        chat_id, message_id, link_type = parse_telegram_link(text)
        if not chat_id or not message_id:
            await message.reply_text('Invalid link format.')
            Z.pop(user_id, None)
            return
            
        Z[user_id].update({
            'step': 'count' if state == 'start' else 'process_single',
            'chat_id': chat_id,
            'message_id': message_id,
            'link_type': link_type
        })
        
        if state == 'start':
            await message.reply_text('How many messages?')
        else:
            await process_single_message(client, message, user_id)
            
    elif state == 'count':
        if not text.isdigit():
            await message.reply_text('Please enter a valid number.')
            return
            
        count = int(text)
        max_limit = (
            PREMIUM_LIMIT if await is_premium_user(user_id)
            else FREEMIUM_LIMIT
        )
        
        if count > max_limit:
            await message.reply_text(
                f'Maximum limit is {max_limit} for your account type.'
            )
            return
            
        Z[user_id].update({
            'step': 'process',
            'target_chat_id': str(message.chat.id),
            'count': count
        })
        
        await process_batch_messages(client, message, user_id)

async def process_single_message(
    client: Client,
    message: Message,
    user_id: int
) -> None:
    """Process a single message from a link."""
    state = Z[user_id]
    progress_msg = await message.reply_text('Processing...')
    
    user_bot = UB.get(user_id)
    if not user_bot:
        await progress_msg.edit('Please add your bot with /setbot first')
        Z.pop(user_id, None)
        return
        
    user_client = await ClientManager.get_user_client(user_id)
    if not user_client:
        await progress_msg.edit('Cannot proceed without user client.')
        Z.pop(user_id, None)
        return
        
    if BatchManager.is_user_active(user_id):
        await progress_msg.edit('You have an active task. Use /stop first.')
        Z.pop(user_id, None)
        return
    
    try:
        msg = await ClientManager.get_message(
            user_bot,
            user_client,
            state['chat_id'],
            state['message_id'],
            state['link_type']
        )
        
        if msg:
            result = await MessageProcessor.process_message(
                client,
                user_client,
                msg,
                user_id,
                state['chat_id'],
                state['message_id'],
                state['link_type'],
                state.get('target_chat_id', str(message.chat.id))
            )
            await progress_msg.edit(f'1/1: {result}')
        else:
            await progress_msg.edit('Message not found')
    except Exception as e:
        await progress_msg.edit(f'Error: {str(e)[:50]}')
    finally:
        Z.pop(user_id, None)

async def process_batch_messages(
    client: Client,
    message: Message,
    user_id: int
) -> None:
    """Process a batch of messages."""
    state = Z[user_id]
    progress_msg = await message.reply_text('Processing batch...')
    
    user_bot = state.get('client')
    user_client = await ClientManager.get_user_client(user_id)
    
    if not user_client or not user_bot:
        await progress_msg.edit('Missing client setup')
        Z.pop(user_id, None)
        return
        
    if BatchManager.is_user_active(user_id):
        await progress_msg.edit('You already have an active task')
        Z.pop(user_id, None)
        return
    
    # Initialize batch tracking
    await BatchManager.add_active_batch(user_id, {
        "total": state['count'],
        "current": 0,
        "success": 0,
        "cancel_requested": False,
        "progress_message_id": progress_msg.id
    })
    
    success_count = 0
    
    try:
        for i in range(state['count']):
            if BatchManager.should_cancel(user_id):
                await progress_msg.edit(
                    f'Cancelled at {i}/{state["count"]}. Success: {success_count}'
                )
                break
                
            await BatchManager.update_batch_progress(user_id, i, success_count)
            
            current_message_id = int(state['message_id']) + i
            
            try:
                msg = await ClientManager.get_message(
                    user_bot,
                    user_client,
                    state['chat_id'],
                    current_message_id,
                    state['link_type']
                )
                
                if msg:
                    result = await MessageProcessor.process_message(
                        client,
                        user_client,
                        msg,
                        user_id,
                        state['chat_id'],
                        current_message_id,
                        state['link_type'],
                        state['target_chat_id']
                    )
                    
                    if any(s in result for s in ['Done', 'Copied', 'Sent']):
                        success_count += 1
                else:
                    pass  # Message not found, skip
            except Exception as e:
                try:
                    await progress_msg.edit(
                        f'{i+1}/{state["count"]}: Error - {str(e)[:30]}'
                    )
                except:
                    pass
                
            await asyncio.sleep(10)  # Rate limiting
            
        if i + 1 == state['count']:
            await message.reply_text(
                f'Batch Completed ✅ Success: {success_count}/{state["count"]}'
            )
    finally:
        await BatchManager.remove_active_batch(user_id)
        Z.pop(user_id, None)