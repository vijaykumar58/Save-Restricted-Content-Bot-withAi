from shared_client import client as bot_client_telethon, app as bot_client_pyrogram # Renamed for clarity
from telethon import events
from datetime import timedelta, timezone # Added timezone for clarity if needed, though not used in current strftime
from config import OWNER_ID
from utils.func import add_premium_user, is_private_chat
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.client import Client as PyrogramClientInstance # For type hinting
from telethon.tl.types import User # For type hinting event.sender_id origin
import base64 as spy
from utils.func import a1, a2, a3, a4, a5, a7, a8, a9, a10, a11 # Obfuscated strings
from plugins.start import subscribe # Assuming subscribe is an async function

# Ensure OWNER_ID is a list of integers
if isinstance(OWNER_ID, str):
    try:
        OWNER_ID = [int(OWNER_ID)]
    except ValueError:
        print("ERROR: OWNER_ID in config is a string but not a valid integer. Please fix.")
        OWNER_ID = [] # Default to empty if conversion fails
elif isinstance(OWNER_ID, int):
     OWNER_ID = [OWNER_ID] # Convert single int to list
elif not isinstance(OWNER_ID, list):
    print("Warning: OWNER_ID format in config is unexpected. Should be list of ints or single int/str.")
    OWNER_ID = []


@bot_client_telethon.on(events.NewMessage(pattern='/add', forwards=False)) # forwards=False to ignore forwarded /add commands
async def add_premium_handler(event: events.NewMessage.Event):
    if not await is_private_chat(event): # from utils.func
        await event.respond(
            'This command can only be used in private chats for security reasons.'
        )
        return
    
    # Ensure sender_id is available and is an int
    if not event.sender_id or not isinstance(event.sender_id, int):
        await event.respond("Could not identify sender.")
        return

    user_id = event.sender_id
    if user_id not in OWNER_ID:
        await event.respond('This command is restricted to the bot owner.')
        return
        
    text = event.message.text.strip()
    parts = text.split() # Split by any whitespace
    # Expected format: /add <user_id> <duration_value> <duration_unit>
    # Example: /add 123456789 1 week
    if len(parts) != 4:
        await event.respond(
            "Invalid format. Use: `/add <target_user_id> <duration_value> <duration_unit>`\n"
            "Example: `/add 123456789 1 week`\n"
            "Valid units: min, hours, days, weeks, month, year, decades"
        )
        return
    
    command, target_user_id_str, duration_value_str, duration_unit = parts

    try:
        target_user_id = int(target_user_id_str)
        duration_value = int(duration_value_str)
        
        # Validate duration_unit (already done in add_premium_user, but good for early check)
        valid_units = ['min', 'hours', 'days', 'weeks', 'month', 'year', 'decades']
        if duration_unit.lower() not in valid_units:
            await event.respond(
                f"Invalid duration unit: `{duration_unit}`. "
                f"Choose from: {', '.join(valid_units)}"
            )
            return

        success, result = await add_premium_user(target_user_id, duration_value, duration_unit.lower())
        
        if success and isinstance(result, timedelta): # If result is timedelta, it means expiry_date
            expiry_utc = result # This is already expiry_date from add_premium_user
            # Convert to IST for display (UTC+5:30)
            ist_offset = timedelta(hours=5, minutes=30)
            expiry_ist = expiry_utc + ist_offset # Assuming expiry_utc is naive UTC datetime
            formatted_expiry_ist = expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p IST')
            
            await event.respond(
                f"✅ User `{target_user_id}` added as a premium member.\n"
                f"Subscription valid until: **{formatted_expiry_ist}**"
            )
            # Notify the target user
            try:
                await bot_client_telethon.send_message(
                    target_user_id,
                    f"🎉 Congratulations! You have been added as a premium member.\n"
                    f"Your subscription is valid until: **{formatted_expiry_ist}**"
                )
            except Exception as e_notify:
                await event.respond(f"ℹ️ User `{target_user_id}` made premium, but could not notify them. Reason: {e_notify}")
        
        elif success and not isinstance(result, timedelta): # Should ideally be the expiry date object
            # This case might occur if add_premium_user changes its return signature for success
             await event.respond(
                f"✅ User `{target_user_id}` added as premium. Expiry details: {result}" # result might be the expiry_date object
            )
        else: # success is False
            await event.respond(f'❌ Failed to add premium user `{target_user_id}`: {result}') # result is error message string

    except ValueError:
        await event.respond(
            'Invalid User ID or Duration Value. Both must be integers.\n'
            'Use: `/add <target_user_id> <duration_value> <duration_unit>`'
        )
    except Exception as e:
        await event.respond(f'An unexpected error occurred: {str(e)}')
        
        
# These attributes are used for obfuscated command and message elements
# Their names come from the utils.func where they are defined.
# For clarity, it's better to decode them once here if they are static.
try:
    DECODED_A1 = spy.b64decode(a1).decode()  # "save_restricted_content_bots"
    DECODED_A2_INT = int(spy.b64decode(a2).decode()) # 796 (message_id)
    DECODED_A3 = spy.b64decode(a3).decode()  # "get_messages"
    DECODED_A4 = spy.b64decode(a4).decode()  # "reply_photo"
    DECODED_A5_CMD = spy.b64decode(a5.encode()).decode() # "start" (command)
    DECODED_A7_CAPTION = spy.b64decode(a7).decode() # Welcome message
    DECODED_A8_BTN_JOIN = spy.b64decode(a8).decode() # "Join Channel"
    DECODED_A9_BTN_PREM = spy.b64decode(a9).decode() # "Get Premium"
    DECODED_A10_URL_JOIN = spy.b64decode(a10).decode() # t.me/team_spy_pro
    DECODED_A11_URL_PREM = spy.b64decode(a11).decode() # t.me/kingofpatal

    # Assuming attr1 and attr2 from utils.func are 'photo' and 'file_id' b64 encoded
    # These are used to access attributes of a message object.
    # This part is highly obfuscated and makes the code hard to read/maintain.
    # For robustness, consider direct attribute access if possible after understanding intent.
    # If these are fixed strings ('photo', 'file_id'), then:
    OBFUSCATED_ATTR_PHOTO = "photo" # spy.b64decode("cGhvdG8=".encode()).decode()
    OBFUSCATED_ATTR_FILE_ID = "file_id" # spy.b64decode("ZmlsZV9pZA==".encode()).decode()

except Exception as e_decode_obf:
    print(f"Error decoding obfuscated strings for start handler: {e_decode_obf}")
    # Define defaults or raise critical error if these are essential
    DECODED_A5_CMD = "start_fallback" # Fallback command if decoding fails

@bot_client_pyrogram.on_message(filters.command(DECODED_A5_CMD) & filters.private)
async def obfuscated_start_handler(client: PyrogramClientInstance, message: Message):
    # Force subscribe check
    subscription_status = await subscribe(client, message) # client is Pyrogram instance
    if subscription_status == 1: # User needs to subscribe
        return

    try:
        # Fetch a specific message (presumably with a photo) from a specific chat
        # DECODED_A1 ("save_restricted_content_bots") seems like a chat username/id
        # DECODED_A2_INT (796) seems like a message_id in that chat
        # DECODED_A3 ("get_messages") is the method name
        
        # Using getattr to call client.get_messages(chat_id, message_id)
        source_message_with_photo = await getattr(client, DECODED_A3)(DECODED_A1, DECODED_A2_INT)

        if not source_message_with_photo or not hasattr(source_message_with_photo, OBFUSCATED_ATTR_PHOTO):
            await message.reply_text("Error: Could not retrieve the start message image. Please contact admin.")
            return

        # Get the photo object and then its file_id
        # getattr(source_message_with_photo, 'photo') -> Photo object
        # getattr(photo_object, 'file_id') -> file_id string
        photo_object = getattr(source_message_with_photo, OBFUSCATED_ATTR_PHOTO)
        if not photo_object or not hasattr(photo_object, OBFUSCATED_ATTR_FILE_ID):
            await message.reply_text("Error: Start message image format is invalid. Please contact admin.")
            return
            
        photo_file_id = getattr(photo_object, OBFUSCATED_ATTR_FILE_ID)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(DECODED_A8_BTN_JOIN, url=DECODED_A10_URL_JOIN)],
            [InlineKeyboardButton(DECODED_A9_BTN_PREM, url=DECODED_A11_URL_PREM)]
        ])

        # Reply with the fetched photo using its file_id and the decoded caption
        # DECODED_A4 ("reply_photo") is the method name
        await getattr(message, DECODED_A4)(
            photo=photo_file_id, # Send by file_id
            caption=DECODED_A7_CAPTION,
            reply_markup=keyboard
        )
    except Exception as e_obf_start:
        print(f"Error in obfuscated_start_handler: {e_obf_start}")
        await message.reply_text("An error occurred while processing the start command. Please try again later or contact support.")
