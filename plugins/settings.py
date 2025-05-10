import re
import os
import asyncio
import string
import random
from typing import Dict, Optional, Tuple
from telethon import events, Button
from shared_client import client as gf
from config import OWNER_ID
from utils.func import get_user_data_key, save_user_data, users_collection

# Constants
VIDEO_EXTENSIONS = {
    'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm',
    'mpeg', 'mpg', '3gp'
}
SETTINGS_PHOTO = 'settings.jpg'
SETTINGS_MESSAGE = '⚙️ Customize your bot settings:'
MAX_THUMBNAIL_SIZE = 5 * 1024 * 1024  # 5MB

# Global state for active conversations
active_conversations: Dict[int, Dict] = {}

class SettingsManager:
    @staticmethod
    async def generate_settings_menu() -> List[List[Button]]:
        """Generate the settings menu buttons."""
        return [
            [
                Button.inline('📝 Set Chat ID', b'setchat'),
                Button.inline('🏷️ Set Rename Tag', b'setrename')
            ],
            [
                Button.inline('📋 Set Caption', b'setcaption'),
                Button.inline('🔄 Replace Words', b'setreplacement')
            ],
            [
                Button.inline('🗑️ Remove Words', b'delete'),
                Button.inline('🔄 Reset Settings', b'reset')
            ],
            [
                Button.inline('🔑 Session Login', b'addsession'),
                Button.inline('🚪 Logout', b'logout')
            ],
            [
                Button.inline('🖼️ Set Thumbnail', b'setthumb'),
                Button.inline('❌ Remove Thumbnail', b'remthumb')
            ],
            [
                Button.url('🆘 Support', 'https://t.me/team_spy_pro')
            ]
        ]

    @staticmethod
    async def reset_user_settings(user_id: int) -> bool:
        """Reset all settings for a user."""
        try:
            # Clear database settings
            await users_collection.update_one(
                {'user_id': user_id},
                {'$unset': {
                    'delete_words': '',
                    'replacement_words': '',
                    'rename_tag': '',
                    'caption': '',
                    'chat_id': ''
                }}
            )
            
            # Remove thumbnail file if exists
            thumbnail_path = f'{user_id}.jpg'
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                
            return True
        except Exception as e:
            logger.error(f"Error resetting settings for {user_id}: {e}")
            return False

    @staticmethod
    def validate_chat_id(chat_id: str) -> bool:
        """Validate Telegram chat ID format."""
        if chat_id.startswith('-100') and chat_id[4:].isdigit():
            return True
        if '/' in chat_id:  # For topic groups
            base, topic = chat_id.split('/', 1)
            return base.startswith('-100') and base[4:].isdigit() and topic.isdigit()
        return False

class ConversationHandler:
    CALLBACK_ACTIONS = {
        b'setchat': {
            'type': 'setchat',
            'message': """📌 Enter the chat ID (with -100 prefix):\n\n"""
                     """__Note:__ Your bot must be admin in that chat\n"""
                     """For topic groups: __-100CHATID/TOPICID__"""
        },
        b'setrename': {
            'type': 'setrename',
            'message': '🏷 Enter your rename tag:'
        },
        b'setcaption': {
            'type': 'setcaption',
            'message': '📝 Enter your caption:'
        },
        b'setreplacement': {
            'type': 'setreplacement',
            'message': "🔄 Enter replacement pair:\n'OLD_WORD' 'NEW_WORD'"
        },
        b'addsession': {
            'type': 'addsession',
            'message': '🔑 Enter your Pyrogram V2 session string:'
        },
        b'delete': {
            'type': 'deleteword',
            'message': '🗑 Enter words to remove (space separated):'
        },
        b'setthumb': {
            'type': 'setthumb',
            'message': '🖼 Send the photo for thumbnail:'
        }
    }

    @staticmethod
    async def start_conversation(event, user_id: int, conv_type: str, prompt: str):
        """Start a new settings conversation."""
        if user_id in active_conversations:
            await event.respond('⚠️ Previous operation cancelled.')
        
        msg = await event.respond(
            f"{prompt}\n\n/cancel to cancel",
            parse_mode='md'
        )
        active_conversations[user_id] = {
            'type': conv_type,
            'message_id': msg.id
        }

    @staticmethod
    async def handle_setchat(event, user_id: int):
        """Handle chat ID setting."""
        chat_id = event.text.strip()
        if not SettingsManager.validate_chat_id(chat_id):
            await event.respond('❌ Invalid chat ID format. Must start with -100')
            return
        
        await save_user_data(user_id, 'chat_id', chat_id)
        await event.respond(f'✅ Chat ID set:\n`{chat_id}`')

    @staticmethod
    async def handle_setrename(event, user_id: int):
        """Handle rename tag setting."""
        rename_tag = event.text.strip()
        if len(rename_tag) > 50:
            await event.respond('❌ Tag too long (max 50 chars)')
            return
            
        await save_user_data(user_id, 'rename_tag', rename_tag)
        await event.respond(f'✅ Rename tag set:\n`{rename_tag}`')

    @staticmethod
    async def handle_setcaption(event, user_id: int):
        """Handle caption setting."""
        caption = event.text
        if len(caption) > 1024:
            await event.respond('❌ Caption too long (max 1024 chars)')
            return
            
        await save_user_data(user_id, 'caption', caption)
        await event.respond('✅ Caption set successfully!')

    @staticmethod
    async def handle_setreplacement(event, user_id: int):
        """Handle word replacement setting."""
        match = re.match(r"'(.*?)' '(.*?)'", event.text)
        if not match:
            await event.respond("❌ Format: 'OLD' 'NEW'")
            return
            
        old_word, new_word = match.groups()
        delete_words = await get_user_data_key(user_id, 'delete_words', [])
        
        if old_word in delete_words:
            await event.respond(f"❌ '{old_word}' is in delete list")
            return
            
        replacements = await get_user_data_key(user_id, 'replacement_words', {})
        replacements[old_word] = new_word
        await save_user_data(user_id, 'replacement_words', replacements)
        await event.respond(f"✅ Replacement:\n'{old_word}' → '{new_word}'")

    @staticmethod
    async def handle_addsession(event, user_id: int):
        """Handle session string setting."""
        session_string = event.text.strip()
        if not session_string.startswith('1'):
            await event.respond('❌ Invalid session format')
            return
            
        await save_user_data(user_id, 'session_string', session_string)
        await event.respond('✅ Session saved!')

    @staticmethod
    async def handle_deleteword(event, user_id: int):
        """Handle word deletion setting."""
        words = [w.strip() for w in event.text.split() if w.strip()]
        if not words:
            await event.respond('❌ No valid words provided')
            return
            
        delete_words = list(set(
            await get_user_data_key(user_id, 'delete_words', []) + words
        ))
        await save_user_data(user_id, 'delete_words', delete_words)
        await event.respond(f"✅ Deletion list updated:\n{', '.join(words)}")

    @staticmethod
    async def handle_setthumb(event, user_id: int):
        """Handle thumbnail setting."""
        if not event.photo:
            await event.respond('❌ Please send a photo')
            return
            
        if event.file.size > MAX_THUMBNAIL_SIZE:
            await event.respond('❌ Image too large (max 5MB)')
            return
            
        try:
            thumb_path = f'{user_id}.jpg'
            await event.download_media(file=thumb_path)
            await event.respond('✅ Thumbnail saved!')
        except Exception as e:
            await event.respond(f'❌ Error saving thumbnail: {str(e)}')

# Command Handlers
@gf.on(events.NewMessage(pattern='/settings'))
async def settings_command(event):
    """Handle /settings command."""
    buttons = await SettingsManager.generate_settings_menu()
    await event.respond(SETTINGS_MESSAGE, buttons=buttons)

@gf.on(events.CallbackQuery())
async def callback_handler(event):
    """Handle all callback queries."""
    user_id = event.sender_id
    
    if event.data == b'logout':
        result = await users_collection.update_one(
            {'user_id': user_id},
            {'$unset': {'session_string': ''}}
        )
        response = '✅ Logged out' if result.modified_count else '❌ Not logged in'
        await event.respond(response)
    elif event.data == b'reset':
        success = await SettingsManager.reset_user_settings(user_id)
        await event.respond(
            '✅ Settings reset' if success else '❌ Reset failed'
        )
    elif event.data == b'remthumb':
        thumb_path = f'{user_id}.jpg'
        try:
            os.remove(thumb_path)
            await event.respond('✅ Thumbnail removed')
        except FileNotFoundError:
            await event.respond('❌ No thumbnail found')
        except Exception as e:
            await event.respond(f'❌ Error: {str(e)}')
    elif event.data in ConversationHandler.CALLBACK_ACTIONS:
        action = ConversationHandler.CALLBACK_ACTIONS[event.data]
        await ConversationHandler.start_conversation(
            event, user_id, action['type'], action['message']
        )

@gf.on(events.NewMessage(pattern='/cancel'))
async def cancel_handler(event):
    """Handle conversation cancellation."""
    user_id = event.sender_id
    if user_id in active_conversations:
        del active_conversations[user_id]
        await event.respond('❌ Operation cancelled')

@gf.on(events.NewMessage())
async def message_handler(event):
    """Handle ongoing conversations."""
    user_id = event.sender_id
    if user_id not in active_conversations or event.text.startswith('/'):
        return
        
    conv_type = active_conversations[user_id]['type']
    handler_name = f'handle_{conv_type}'
    
    if hasattr(ConversationHandler, handler_name):
        handler = getattr(ConversationHandler, handler_name)
        await handler(event, user_id)
        
    if user_id in active_conversations:  # Cleanup if not already done
        del active_conversations[user_id]

# File Renaming Utilities
def generate_random_name(length: int = 8) -> str:
    """Generate a random filename."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

async def rename_file(file_path: str, user_id: int) -> str:
    """Rename a file according to user settings."""
    try:
        # Get user settings
        delete_words = await get_user_data_key(user_id, 'delete_words', [])
        rename_tag = await get_user_data_key(user_id, 'rename_tag', '')
        replacements = await get_user_data_key(user_id, 'replacement_words', {})
        
        # Extract filename parts
        base, ext = os.path.splitext(file_path)
        ext = ext.lstrip('.').lower()
        
        # Determine proper extension
        if not ext or ext not in VIDEO_EXTENSIONS:
            ext = 'mp4' if any(v in base.lower() for v in VIDEO_EXTENSIONS) else 'bin'
        
        # Process filename
        filename = os.path.basename(base)
        for word in delete_words:
            filename = filename.replace(word, '')
            
        for old, new in replacements.items():
            filename = filename.replace(old, new)
            
        # Construct new filename
        new_filename = f"{filename} {rename_tag}".strip() + f".{ext}"
        new_path = os.path.join(os.path.dirname(file_path), new_filename)
        
        os.rename(file_path, new_path)
        return new_path
    except Exception as e:
        logger.error(f"File rename error: {e}")
        return file_path