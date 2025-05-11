from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    BadRequest, SessionPasswordNeeded, PhoneCodeInvalid, 
    PhoneCodeExpired, MessageNotModified, FloodWait, ApiIdInvalid, ApiIdPublishedFlood
)
import logging
import os
from config import API_HASH, API_ID # Ensure these are correctly loaded
from shared_client import app as bot # Assuming bot is the main Pyrogram client for commands
from utils.func import save_user_session, get_user_data, remove_user_session, save_user_bot, remove_user_bot
from utils.encrypt import ecs, dcs # Encryption for session string
from plugins.batch import UB, UC # Dictionaries for user-specific clients
from utils.custom_filters import login_in_progress, set_user_step, get_user_step

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__) # Consider renaming to avoid conflict if 'client' is used as var name
PYROGRAM_MODEL_NAME = "v3saver TeamSPY User" # Custom device model for Pyrogram sessions

# Steps for login flow
STEP_PHONE = 1
STEP_CODE = 2
STEP_PASSWORD = 3

# Cache for ongoing login processes. Key: user_id
login_cache: dict = {} 

@bot.on_message(filters.command('login') & filters.private)
async def login_command(client: Client, message: Message): # client is 'bot' here
    user_id = message.from_user.id
    
    # If user is already in a login process, inform them.
    if get_user_step(user_id):
        await message.reply("You are already in a login process. Send /cancel_login to stop it first.")
        return

    set_user_step(user_id, STEP_PHONE)
    login_cache.pop(user_id, None) # Clear any stale cache for this user_id
    
    try:
        await message.delete() # Delete the /login command message
    except Exception as e_del:
        logger.warning(f"Could not delete /login command message: {e_del}")

    status_msg = await message.reply_text( # Use reply_text for consistency
        "Please send your phone number with country code.\n"
        "Example: `+12345678900`\n\n"
        "Send /cancel_login to abort this process."
    )
    login_cache[user_id] = {'status_msg_id': status_msg.id, 'chat_id': status_msg.chat.id}


@bot.on_message(filters.command("setbot") & filters.private)
async def set_bot_token(client: Client, m: Message): # client is 'bot'
    user_id = m.from_user.id
    args = m.text.split(" ", 1)

    # Stop and remove existing bot for this user if it's in UB cache
    if user_id in UB:
        try:
            old_bot_instance = UB.pop(user_id) # Remove from cache first
            if old_bot_instance.is_connected:
                await old_bot_instance.stop()
            
            # Attempt to remove session file for the user's bot
            session_file_name = f"user_bot_{user_id}.session" # Consistent naming with get_ubot
            if os.path.exists(session_file_name):
                os.remove(session_file_name)
            logger.info(f"Stopped and removed old bot session for user {user_id}")
        except Exception as e_stop_old:
            logger.error(f"Error stopping/removing old bot for user {user_id}: {e_stop_old}")
            # UB[user_id] should have been popped already

    if len(args) < 2:
        await m.reply_text("⚠️ Please provide a bot token. Usage: `/setbot YOUR_BOT_TOKEN`", quote=True)
        return

    bot_token = args[1].strip()
    # Basic validation for bot token format (optional but good)
    if not re.match(r"^\d+:[\w-]+$", bot_token):
        await m.reply_text("⚠️ Invalid bot token format.", quote=True)
        return

    # Test the token by trying to get bot info (optional, adds delay but verifies token)
    try:
        temp_bot_client = Client(f"temp_bot_checker_{user_id}", api_id=API_ID, api_hash=API_HASH, bot_token=bot_token, in_memory=True)
        await temp_bot_client.start()
        bot_info = await temp_bot_client.get_me()
        await temp_bot_client.stop()
        logger.info(f"Bot token for user {user_id} verified for bot @{bot_info.username}")
    except Exception as e_verify_token:
        logger.error(f"Failed to verify bot token for user {user_id}: {e_verify_token}")
        await m.reply_text(f"⚠️ Could not verify the bot token. Please ensure it's correct and active. Error: {e_verify_token}", quote=True)
        return

    await save_user_bot(user_id, bot_token) # Save to DB
    await m.reply_text("✅ Bot token saved successfully. It will be used for operations requiring a bot.", quote=True)
    
    
@bot.on_message(filters.command("rembot") & filters.private)
async def rem_bot_token(client: Client, m: Message): # client is 'bot'
    user_id = m.from_user.id
    
    if user_id in UB:
        try:
            bot_instance_to_remove = UB.pop(user_id) # Remove from cache
            if bot_instance_to_remove.is_connected:
                await bot_instance_to_remove.stop()
            
            session_file_name = f"user_bot_{user_id}.session" # Consistent naming
            if os.path.exists(session_file_name):
                os.remove(session_file_name)
            logger.info(f"Stopped and removed bot session for user {user_id} from cache and disk.")
        except Exception as e_rem_cache:
            logger.error(f"Error stopping/removing cached bot for user {user_id}: {e_rem_cache}")

    removed_from_db = await remove_user_bot(user_id) # Remove from DB
    if removed_from_db:
        await m.reply_text("✅ Bot token removed successfully from database.", quote=True)
    else: # This might mean it wasn't in DB or DB operation failed
        await m.reply_text("ℹ️ No bot token found in database for your account, or an error occurred.", quote=True)


# Filter for messages during login process: text, private, not a command
@bot.on_message(login_in_progress & filters.text & filters.private & ~filters.command([
    'start', 'batch', 'cancel', 'login', 'logout', 'stop', 'set', 'pay', 'help', # Add all other commands
    'redeem', 'gencode', 'generate', 'keyinfo', 'encrypt', 'decrypt', 'keys', 
    'setbot', 'rembot', 'cancel_login' # Add cancel_login here
    # This list needs to be comprehensive to avoid interference.
]))
async def handle_login_steps(client: Client, message: Message): # client is 'bot'
    user_id = message.from_user.id
    text = message.text.strip()
    step = get_user_step(user_id)

    # Ensure login_cache has entry for user, otherwise something is wrong
    if user_id not in login_cache or 'status_msg_id' not in login_cache[user_id]:
        await message.reply_text("Login process state error. Please start with /login again.")
        set_user_step(user_id, None) # Reset step
        login_cache.pop(user_id, None)
        return

    status_msg_chat_id = login_cache[user_id]['chat_id']
    status_msg_id = login_cache[user_id]['status_msg_id']

    try:
        await message.delete() # Delete user's input message (phone/code/password)
    except Exception as e_del_input:
        logger.warning(f'Could not delete user input message: {e_del_input}')
    
    current_temp_client: Optional[Client] = login_cache[user_id].get('temp_client')

    try:
        if step == STEP_PHONE:
            if not text.startswith('+') or not text[1:].isdigit(): # Basic phone validation
                await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    '❌ Invalid phone number format. Please provide a valid phone number starting with `+` and followed by digits.\nExample: `+12345678900`')
                return
            
            await edit_message_safely(client, status_msg_chat_id, status_msg_id, '🔄 Processing phone number...')
            
            # Create a new temporary Pyrogram client for this login attempt
            # Use in_memory=True to avoid creating session files for these temp clients
            temp_client = Client(f'temp_login_{user_id}', api_id=API_ID, api_hash=API_HASH, 
                                 device_model=PYROGRAM_MODEL_NAME, in_memory=True)
            login_cache[user_id]['temp_client'] = temp_client

            try:
                await temp_client.connect()
                sent_code_info = await temp_client.send_code(text) # 'text' is phone number
                
                # Store phone and phone_code_hash for the next step
                login_cache[user_id]['phone'] = text
                login_cache[user_id]['phone_code_hash'] = sent_code_info.phone_code_hash
                set_user_step(user_id, STEP_CODE)
                
                await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    "✅ Verification code sent to your Telegram account (or via SMS/call if not logged in elsewhere).\n\n"
                    "Please enter the code you received (e.g., `12345` or `1 2 3 4 5`).\n\n"
                    "Send /cancel_login to abort."
                )
            except FloodWait as e_flood:
                await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    f"❌ Flood wait: Please wait for {e_flood.value} seconds before trying again with /login.")
                await cleanup_login_attempt(user_id)
            except (ApiIdInvalid, ApiIdPublishedFlood) as e_api_id:
                 await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    f"❌ API ID issue: {e_api_id}. Please contact bot admin.")
                 await cleanup_login_attempt(user_id)
            except BadRequest as e_bad_phone: # Covers some phone number issues
                await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    f"❌ Error with phone number: {e_bad_phone}.\nPlease check the number and try /login again.")
                await cleanup_login_attempt(user_id)
            except Exception as e_send_code: # Catch other errors during send_code
                logger.error(f"Error sending code for user {user_id}: {e_send_code}")
                await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    f"❌ An unexpected error occurred while sending code: {e_send_code}. Please try /login again.")
                await cleanup_login_attempt(user_id)

        elif step == STEP_CODE:
            code = text.replace(' ', '') # Remove spaces if user types "1 2 3 4 5"
            if not code.isdigit():
                await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    '❌ Invalid code format. Please enter digits only.')
                return # Keep user at STEP_CODE

            phone = login_cache[user_id]['phone']
            phone_code_hash = login_cache[user_id]['phone_code_hash']
            
            if not current_temp_client: # Should not happen if flow is correct
                raise Exception("Temporary client not found in cache for code verification.")

            await edit_message_safely(client, status_msg_chat_id, status_msg_id, '🔄 Verifying code...')
            try:
                await current_temp_client.sign_in(phone, phone_code_hash, code)
                # Successfully signed in (or needs 2FA password)
                # If sign_in is successful without needing 2FA, it proceeds directly.
                # If it needs 2FA, it raises SessionPasswordNeeded.
                
                # If here, sign_in was successful and no 2FA needed.
                session_string = await current_temp_client.export_session_string()
                encrypted_session = ecs(session_string) # Encrypt the session string
                await save_user_session(user_id, encrypted_session) # Save to DB
                
                await edit_message_safely(client, status_msg_chat_id, status_msg_id, "✅ Logged in successfully!")
                await cleanup_login_attempt(user_id, logged_in=True)

            except SessionPasswordNeeded:
                set_user_step(user_id, STEP_PASSWORD)
                await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    "🔒 Two-step verification (2FA) is enabled.\nPlease enter your password:"
                )
            except (PhoneCodeInvalid, PhoneCodeExpired) as e_code_err:
                await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    f'❌ {e_code_err}. Please try the login process again with /login.')
                await cleanup_login_attempt(user_id) # Clean up on code error
            except FloodWait as e_flood_signin:
                await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    f"❌ Flood wait during sign-in: Please wait {e_flood_signin.value}s and try /login again.")
                await cleanup_login_attempt(user_id)
            except BadRequest as e_bad_signin: # Other sign-in errors
                 await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    f"❌ Error during sign-in: {e_bad_signin}. Please try /login again.")
                 await cleanup_login_attempt(user_id)


        elif step == STEP_PASSWORD:
            password = text # User's 2FA password
            if not current_temp_client:
                 raise Exception("Temporary client not found in cache for password verification.")

            await edit_message_safely(client, status_msg_chat_id, status_msg_id, '🔄 Verifying password...')
            try:
                await current_temp_client.check_password(password)
                # Password correct, now export and save session
                session_string = await current_temp_client.export_session_string()
                encrypted_session = ecs(session_string)
                await save_user_session(user_id, encrypted_session)
                
                await edit_message_safely(client, status_msg_chat_id, status_msg_id, "✅ Logged in successfully (2FA verified)!")
                await cleanup_login_attempt(user_id, logged_in=True)

            except BadRequest as e_bad_pass: # Often "PASSWORD_HASH_INVALID" or similar
                await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    f"❌ Incorrect password or other error: {e_bad_pass}.\nIf you made a typo, please send the correct password. Otherwise, /cancel_login and try /login again.")
                # User remains at STEP_PASSWORD to allow re-try of password
            except FloodWait as e_flood_pass:
                await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                    f"❌ Flood wait during password check: Wait {e_flood_pass.value}s and try /login again.")
                await cleanup_login_attempt(user_id)
        
    except Exception as e_login_flow:
        logger.error(f'Error in login flow for user {user_id} at step {step}: {e_login_flow}', exc_info=True)
        try:
            await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                f"❌ An unexpected error occurred: {str(e_login_flow)[:100]}.\nPlease try again with /login.")
        except: pass # If editing status message itself fails
        await cleanup_login_attempt(user_id)


async def edit_message_safely(client: Client, chat_id: int, message_id: int, text: str):
    """Helper function to edit message and handle MessageNotModified and other common errors."""
    try:
        await client.edit_message_text(chat_id, message_id, text)
    except MessageNotModified:
        pass # Ignore if text is the same
    except FloodWait as e_flood_edit:
        logger.warning(f"Flood wait while editing message {message_id} in {chat_id}: {e_flood_edit.value}s. Will retry editing later if needed.")
        # For critical status updates, you might want to schedule a retry. For now, just log.
    except Exception as e_edit:
        logger.error(f'Error editing message {message_id} in chat {chat_id}: {e_edit}')

async def cleanup_login_attempt(user_id: int, logged_in: bool = False):
    """Cleans up resources after a login attempt (success, failure, or cancel)."""
    temp_client_instance = login_cache.get(user_id, {}).get('temp_client')
    if temp_client_instance:
        if temp_client_instance.is_connected:
            try:
                if not logged_in: # Only explicitly logout if login didn't complete successfully with this client instance
                     # For successful login, exporting session_string is enough, client can be discarded.
                     # No need to call .log_out() on the temp_client if session was exported.
                     pass
                await temp_client_instance.disconnect()
            except Exception as e_disconnect:
                logger.error(f"Error disconnecting temp_client for user {user_id}: {e_disconnect}")
    
    login_cache.pop(user_id, None)
    set_user_step(user_id, None) # Reset user's step

    # Stop and clear user's client from UC cache if login was successful,
    # as a new session string is now saved and get_uclient will pick it up on next call.
    if logged_in and user_id in UC:
        try:
            uc_instance_to_clear = UC.pop(user_id)
            if uc_instance_to_clear.is_connected:
                await uc_instance_to_clear.stop()
            
            # Remove the user's client session file if it exists
            user_client_session_name = f"user_client_{user_id}.session" # Consistent naming
            if os.path.exists(user_client_session_name):
                os.remove(user_client_session_name)
            logger.info(f"Cleared old user client session for {user_id} from cache and disk after successful login.")
        except Exception as e_clear_uc:
            logger.error(f"Error clearing old user client (UC) for {user_id} after login: {e_clear_uc}")


@bot.on_message(filters.command('cancel_login') & filters.private)
async def cancel_login_command(client: Client, message: Message): # client is 'bot'
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except Exception: pass

    if get_user_step(user_id): # If user was in a login step
        status_info = login_cache.get(user_id, {})
        status_msg_chat_id = status_info.get('chat_id')
        status_msg_id = status_info.get('status_msg_id')

        await cleanup_login_attempt(user_id) # Disconnects temp client, clears cache and step

        if status_msg_chat_id and status_msg_id:
            await edit_message_safely(client, status_msg_chat_id, status_msg_id,
                '✅ Login process cancelled. Use /login to start again if needed.')
        else: # Fallback if status message info was lost
            temp_cancel_msg = await message.reply_text('Login process cancelled.')
            await asyncio.sleep(5)
            try: await temp_cancel_msg.delete()
            except: pass
    else:
        temp_no_login_msg = await message.reply_text('No active login process to cancel.')
        await asyncio.sleep(5)
        try: await temp_no_login_msg.delete()
        except: pass
        
@bot.on_message(filters.command('logout') & filters.private)
async def logout_command(client: Client, message: Message): # client is 'bot'
    user_id = message.from_user.id
    
    try:
        await message.delete()
    except Exception: pass

    status_msg = await message.reply_text('🔄 Processing logout request...')
    
    # Clear from UC cache and stop client if active
    if user_id in UC:
        try:
            uc_instance_to_logout = UC.pop(user_id)
            if uc_instance_to_logout.is_connected:
                # Pyrogram's log_out() terminates the session on server-side.
                # Using stop() is usually for client disconnection.
                # To properly log out a session, it's better to load it, call log_out(), then delete.
                # However, get_uclient will create a new instance on next use if session string exists.
                # For simplicity here, just stopping the cached client.
                await uc_instance_to_logout.stop() 
            
            user_client_session_name = f"user_client_{user_id}.session" # Consistent naming
            if os.path.exists(user_client_session_name):
                os.remove(user_client_session_name)
            logger.info(f"Logged out and removed user client session for {user_id} from cache and disk.")
        except Exception as e_uc_logout:
            logger.error(f"Error stopping/removing UC instance for {user_id} during logout: {e_uc_logout}")

    # Remove session from database
    db_session_removed = await remove_user_session(user_id) # This deletes 'session_string' from DB

    if db_session_removed:
        await edit_message_safely(client, status_msg.chat.id, status_msg.id,
            '✅ Logged out successfully! Your session has been removed from the database.')
    else:
        # This could mean no session was in DB, or DB operation failed.
        await edit_message_safely(client, status_msg.chat.id, status_msg.id,
            'ℹ️ No active session found in the database to log out, or an error occurred during database update.')
