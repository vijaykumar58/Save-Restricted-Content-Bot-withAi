# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

from telethon import events, Button
import re
import os
import asyncio
import string
import random
from shared_client import client as gf
from config import OWNER_ID
from utils.func import get_user_data_key, save_user_data, users_collection

VIDEO_EXTENSIONS = {
    'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm',
    'mpeg', 'mpg', '3gp'
}
SET_PIC = 'settings.jpg' # This variable is defined but not used in the provided snippet
MESS = 'Customize settings for your files...'

active_conversations = {}

@gf.on(events.NewMessage(incoming=True, pattern='/settings'))
async def settings_command(event):
    user_id = event.sender_id
    await send_settings_message(event.chat_id, user_id)

async def send_settings_message(chat_id, user_id):
    buttons = [
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
            Button.inline('🔑 Session Login', b'addsession'), # Assuming this relates to user session strings
            Button.inline('🚪 Logout', b'logout') # Assuming this relates to user session strings
        ],
        [
            Button.inline('🖼️ Set Thumbnail', b'setthumb'),
            Button.inline('❌ Remove Thumbnail', b'remthumb')
        ],
        [
            Button.url('🆘 Report Errors', 'https://t.me/team_spy_pro')
        ]
    ]
    # Consider checking if an image exists at SET_PIC path and using it
    # For now, sending text message as per original apparent behavior
    await gf.send_message(chat_id, MESS, buttons=buttons)

@gf.on(events.CallbackQuery)
async def callback_query_handler(event):
    user_id = event.sender_id

    callback_actions = {
        b'setchat': {
            'type': 'setchat',
            'message': """Send me the ID of that chat (with -100 prefix):
__👉 **Note:** if you are using custom bot then your bot should be admin that chat if not then this bot should be admin.__
👉 __If you want to upload in topic group and in specific topic then pass chat id as **-100CHANNELID/TOPIC_ID** for example: **-1004783898/12**__"""
        },
        b'setrename': {
            'type': 'setrename',
            'message': 'Send me the rename tag:'
        },
        b'setcaption': {
            'type': 'setcaption',
            'message': 'Send me the caption:'
        },
        b'setreplacement': {
            'type': 'setreplacement',
            'message': "Send me the replacement words in the format: 'WORD(s)' 'REPLACEWORD'"
        },
        b'addsession': { # This was 'addsession', likely for user session strings, not bot tokens
            'type': 'addsession',
            'message': 'Send Pyrogram V2 session string:'
        },
        b'delete': {
            'type': 'deleteword',
            'message': 'Send words separated by space to delete them from caption/filename...'
        },
        b'setthumb': {
            'type': 'setthumb',
            'message': 'Please send the photo you want to set as the thumbnail.'
        }
    }

    if event.data in callback_actions:
        action = callback_actions[event.data]
        await start_conversation(event, user_id, action['type'], action['message'])
    elif event.data == b'logout': # Corresponds to user session logout
        result = await users_collection.update_one(
            {'user_id': user_id},
            {'$unset': {'session_string': ''}} # Assuming 'session_string' is the field
        )
        if result.modified_count > 0:
            await event.respond('Logged out and deleted session successfully.')
        else:
            await event.respond('You are not logged in or no session string was found.')
    elif event.data == b'reset':
        try:
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
            thumbnail_path = f'{user_id}.jpg'
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
            await event.respond('✅ All settings reset successfully. To logout user session, click Logout.')
        except Exception as e:
            await event.respond(f'Error resetting settings: {e}')
    elif event.data == b'remthumb':
        try:
            thumbnail_path = f'{user_id}.jpg'
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                await event.respond('Thumbnail removed successfully!')
            else:
                await event.respond('No thumbnail found to remove.')
        except Exception as e:
            await event.respond(f'Error removing thumbnail: {e}')
    else:
        await event.answer() # Acknowledge other callbacks if any

async def start_conversation(event, user_id, conv_type, prompt_message):
    if user_id in active_conversations:
        # Optionally, cancel the previous conversation explicitly if needed
        # For example, by sending a message or cleaning up resources
        await event.respond('Previous conversation cancelled. Starting new one.')

    msg = await event.respond(f'{prompt_message}\n\n(Send /cancel to cancel this operation)')
    active_conversations[user_id] = {'type': conv_type, 'message_id': msg.id}
    await event.answer() # Acknowledge the callback

@gf.on(events.NewMessage(pattern='/cancel'))
async def cancel_conversation(event):
    user_id = event.sender_id
    if user_id in active_conversations:
        # Potentially edit the prompt message to show it's cancelled
        # original_prompt_msg_id = active_conversations[user_id].get('message_id')
        # if original_prompt_msg_id:
        #     await gf.edit_message(event.chat_id, original_prompt_msg_id, "Operation cancelled.")
        await event.respond('Operation cancelled.')
        del active_conversations[user_id]
    else:
        await event.respond("No active operation to cancel.")

@gf.on(events.NewMessage())
async def handle_conversation_input(event):
    user_id = event.sender_id
    if user_id not in active_conversations or event.message.text.startswith('/'):
        if not (event.message.text.startswith('/') and event.message.text != '/cancel'): # allow /cancel to pass through
             return

    # If it's a command but not /cancel, and a conversation is active,
    # it might be unintentional. Let it pass for now, or add specific logic.

    conv_data = active_conversations.get(user_id)
    if not conv_data:
        return

    conv_type = conv_data['type']

    handlers = {
        'setchat': handle_setchat,
        'setrename': handle_setrename,
        'setcaption': handle_setcaption,
        'setreplacement': handle_setreplacement,
        'addsession': handle_addsession, # For user session string
        'deleteword': handle_deleteword,
        'setthumb': handle_setthumb
    }

    if conv_type in handlers:
        await handlers[conv_type](event, user_id)

    if user_id in active_conversations and active_conversations[user_id]['type'] == conv_type : # Ensure it's the same conversation
        del active_conversations[user_id]


async def handle_setchat(event, user_id):
    try:
        chat_id_text = event.text.strip()
        # Basic validation for chat ID format (numeric, possibly with -100 or - and / for topics)
        if not (chat_id_text.startswith('-100') or chat_id_text.startswith('-')) and not chat_id_text.replace('/', '').isdigit():
             if not (re.match(r"^-100\d+(/\d+)?$", chat_id_text) or re.match(r"^\d+$", chat_id_text) ): # check for user id or group id
                 await event.respond('Invalid Chat ID format. It should be a number, optionally_topic_id, or start with -100 / -.')
                 return

        await save_user_data(user_id, 'chat_id', chat_id_text)
        await event.respond('✅ Chat ID set successfully!')
    except Exception as e:
        await event.respond(f'❌ Error setting chat ID: {e}')

async def handle_setrename(event, user_id):
    rename_tag = event.text.strip()
    if not rename_tag:
        await event.respond("Rename tag cannot be empty.")
        return
    await save_user_data(user_id, 'rename_tag', rename_tag)
    await event.respond(f'✅ Rename tag set to: {rename_tag}')

async def handle_setcaption(event, user_id):
    caption = event.text # Full text including markdown
    if caption is None: # Ensure caption is not None if event.text can be None
        await event.respond("Caption cannot be empty.")
        return
    await save_user_data(user_id, 'caption', caption)
    await event.respond(f'✅ Caption set successfully!')

async def handle_setreplacement(event, user_id):
    match = re.match(r"^\s*'(.+?)'\s+'(.+?)'\s*$", event.text)
    if not match:
        await event.respond("❌ Invalid format. Usage: 'WORD(s)' 'REPLACEWORD'")
    else:
        word, replace_word = match.groups()
        delete_words = await get_user_data_key(user_id, 'delete_words', [])
        if word in delete_words: # This check might be too simplistic if 'word' is a phrase
            await event.respond(f"❌ The word/phrase '{word}' is in the delete list and cannot be replaced.")
        else:
            replacements = await get_user_data_key(user_id, 'replacement_words', {})
            replacements[word] = replace_word
            await save_user_data(user_id, 'replacement_words', replacements)
            await event.respond(f"✅ Replacement saved: '{word}' will be replaced with '{replace_word}'")

async def handle_addsession(event, user_id): # For user session string
    session_string = event.text.strip()
    if not session_string: # Basic validation
        await event.respond("Session string cannot be empty.")
        return
    # Add more validation for session string format if possible/needed
    await save_user_data(user_id, 'session_string', session_string)
    await event.respond('✅ User session string added successfully!')

async def handle_deleteword(event, user_id):
    words_to_delete_input = event.message.text.strip()
    if not words_to_delete_input:
        await event.respond("Please provide words to delete.")
        return
    words_to_delete = words_to_delete_input.split()
    delete_words_list = await get_user_data_key(user_id, 'delete_words', [])
    # Add new words, avoid duplicates
    updated_delete_words = list(set(delete_words_list + words_to_delete))
    await save_user_data(user_id, 'delete_words', updated_delete_words)
    await event.respond(f"✅ Words added to delete list: {', '.join(words_to_delete)}")

async def handle_setthumb(event, user_id):
    if event.photo:
        # Download media to a temporary path first
        temp_path = await event.download_media(file=os.path.join("tempDir", f"{user_id}_temp_thumb.jpg")) # Ensure tempDir exists
        try:
            thumb_path = f'{user_id}.jpg' # Final path
            # Ensure directory for thumb_path exists if it's not in the current dir
            # os.makedirs(os.path.dirname(thumb_path), exist_ok=True) # If storing in subdirectories
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
            os.rename(temp_path, thumb_path)
            await event.respond('✅ Thumbnail saved successfully!')
        except Exception as e:
            await event.respond(f'❌ Error saving thumbnail: {e}')
            if os.path.exists(temp_path): # Clean up temp file on error
                os.remove(temp_path)
    else:
        await event.respond('❌ Please send a photo. Operation cancelled.')

def generate_random_name(length=7): # This function is defined but not used in this file.
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


async def rename_file(file_path: str, sender_id: int, edit_message_object=None): # Added type hints and clarity
    # 'edit' param was 'edit message object from pyrogram', but this is telethon
    # Assuming 'edit' is a message object that can be edited (e.g. event.edit)
    # For simplicity, this example won't use 'edit_message_object' for progress updates
    # as it's complex to generalize here.

    try:
        delete_words = await get_user_data_key(sender_id, 'delete_words', [])
        custom_rename_tag = await get_user_data_key(sender_id, 'rename_tag', '')
        replacements = await get_user_data_key(sender_id, 'replacement_words', {})

        base_name, original_extension = os.path.splitext(file_path)
        original_extension = original_extension.lstrip('.') # Remove leading dot

        current_file_name_part = os.path.basename(base_name)

        # Apply delete_words and replacements to the filename part
        for word in delete_words:
            current_file_name_part = current_file_name_part.replace(word, '')

        for old_word, new_word in replacements.items():
            current_file_name_part = current_file_name_part.replace(old_word, new_word)

        # Determine final extension
        final_extension = 'mp4' # Default
        if original_extension.lower() in VIDEO_EXTENSIONS:
            final_extension = 'mp4'
        elif original_extension and len(original_extension) <= 9 and original_extension.isalpha():
            final_extension = original_extension.lower()
        elif original_extension: # Keep original if not video and not fitting simple criteria
            final_extension = original_extension.lower()


        new_file_name_base = current_file_name_part.strip()
        if custom_rename_tag:
            new_file_name_base = f"{new_file_name_base} {custom_rename_tag}".strip()

        new_file_path = os.path.join(os.path.dirname(file_path), f"{new_file_name_base}.{final_extension}")

        if file_path == new_file_path:
            return file_path # No change needed

        os.rename(file_path, new_file_path)
        return new_file_path
    except Exception as e:
        print(f"Rename error for sender {sender_id}, file {file_path}: {e}")
        # Optionally, if edit_message_object: await edit_message_object.edit(f"Error renaming: {e}")
        return file_path # Return original path on error
