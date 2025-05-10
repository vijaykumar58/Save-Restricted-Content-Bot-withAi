import logging
import os
from typing import Dict, Optional
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    BadRequest,
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    MessageNotModified
)
from config import API_HASH, API_ID
from shared_client import app as bot
from utils.func import (
    save_user_session,
    get_user_data,
    remove_user_session,
    save_user_bot,
    remove_user_bot
)
from utils.encrypt import ecs, dcs
from plugins.batch import UB, UC
from utils.custom_filters import (
    login_in_progress,
    set_user_step,
    get_user_step
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
MODEL_NAME = "v3saver Team SPY"
STEP_PHONE = 1
STEP_CODE = 2
STEP_PASSWORD = 3

# Global state for login process
login_cache: Dict[int, Dict] = {}

class LoginManager:
    @staticmethod
    async def edit_message_safely(message: Message, text: str) -> None:
        """Safely edit a message with error handling."""
        try:
            await message.edit(text)
        except MessageNotModified:
            pass
        except Exception as e:
            logger.error(f'Error editing message: {e}')

    @staticmethod
    async def cleanup_login_state(user_id: int) -> None:
        """Cleanup login state for a user."""
        if user_id in login_cache and 'temp_client' in login_cache[user_id]:
            try:
                await login_cache[user_id]['temp_client'].disconnect()
            except Exception as e:
                logger.error(f'Error disconnecting temp client: {e}')
        login_cache.pop(user_id, None)
        set_user_step(user_id, None)

    @staticmethod
    async def handle_phone_step(
        user_id: int,
        phone: str,
        status_msg: Message
    ) -> None:
        """Handle phone number verification step."""
        try:
            temp_client = Client(
                f'temp_{user_id}',
                api_id=API_ID,
                api_hash=API_HASH,
                device_model=MODEL_NAME,
                in_memory=True
            )
            await temp_client.connect()
            
            sent_code = await temp_client.send_code(phone)
            
            login_cache[user_id].update({
                'phone': phone,
                'phone_code_hash': sent_code.phone_code_hash,
                'temp_client': temp_client
            })
            set_user_step(user_id, STEP_CODE)
            
            await LoginManager.edit_message_safely(
                status_msg,
                "✅ Verification code sent to your Telegram account.\n\n"
                "Please enter the code (format: 1 2 3 4 5):"
            )
        except BadRequest as e:
            await LoginManager.edit_message_safely(
                status_msg,
                f"❌ Error: {str(e)}\nPlease try again with /login."
            )
            await temp_client.disconnect()
            await LoginManager.cleanup_login_state(user_id)

    @staticmethod
    async def handle_code_step(
        user_id: int,
        code: str,
        status_msg: Message
    ) -> None:
        """Handle verification code step."""
        cache = login_cache[user_id]
        temp_client = cache['temp_client']
        
        try:
            await LoginManager.edit_message_safely(status_msg, "🔄 Verifying code...")
            
            # Try to sign in with the code
            try:
                await temp_client.sign_in(
                    cache['phone'],
                    cache['phone_code_hash'],
                    code.replace(' ', '')
                )
            except SessionPasswordNeeded:
                set_user_step(user_id, STEP_PASSWORD)
                await LoginManager.edit_message_safely(
                    status_msg,
                    "🔒 Two-step verification is enabled.\n"
                    "Please enter your password:"
                )
                return
                
            # If no password needed, complete login
            session_string = await temp_client.export_session_string()
            encrypted_session = ecs(session_string)
            await save_user_session(user_id, encrypted_session)
            
            await temp_client.disconnect()
            await LoginManager.cleanup_login_state(user_id)
            
            await LoginManager.edit_message_safely(
                status_msg,
                "✅ Logged in successfully!!"
            )
        except (PhoneCodeInvalid, PhoneCodeExpired) as e:
            await LoginManager.edit_message_safely(
                status_msg,
                f"❌ {str(e)}. Please try again with /login."
            )
            await LoginManager.cleanup_login_state(user_id)
        except Exception as e:
            logger.error(f'Error in code verification: {str(e)}')
            await LoginManager.edit_message_safely(
                status_msg,
                f"❌ An error occurred: {str(e)}\nPlease try again with /login."
            )
            await LoginManager.cleanup_login_state(user_id)

    @staticmethod
    async def handle_password_step(
        user_id: int,
        password: str,
        status_msg: Message
    ) -> None:
        """Handle two-step verification password step."""
        temp_client = login_cache[user_id]['temp_client']
        
        try:
            await LoginManager.edit_message_safely(status_msg, "🔄 Verifying password...")
            await temp_client.check_password(password)
            
            session_string = await temp_client.export_session_string()
            encrypted_session = ecs(session_string)
            await save_user_session(user_id, encrypted_session)
            
            await temp_client.disconnect()
            await LoginManager.cleanup_login_state(user_id)
            
            await LoginManager.edit_message_safely(
                status_msg,
                "✅ Logged in successfully!!"
            )
        except BadRequest as e:
            await LoginManager.edit_message_safely(
                status_msg,
                f"❌ Incorrect password: {str(e)}\nPlease try again:"
            )
        except Exception as e:
            logger.error(f'Error in password verification: {str(e)}')
            await LoginManager.edit_message_safely(
                status_msg,
                f"❌ An error occurred: {str(e)}\nPlease try again with /login."
            )
            await LoginManager.cleanup_login_state(user_id)

class BotTokenManager:
    @staticmethod
    async def set_bot_token(user_id: int, bot_token: str) -> bool:
        """Set and save a bot token for a user."""
        try:
            # Clean up existing bot if any
            if user_id in UB:
                try:
                    await UB[user_id].stop()
                except Exception as e:
                    logger.error(f"Error stopping old bot: {e}")
                finally:
                    UB.pop(user_id, None)
                
                # Remove old session file if exists
                try:
                    session_file = f"user_{user_id}.session"
                    if os.path.exists(session_file):
                        os.remove(session_file)
                except Exception as e:
                    logger.error(f"Error removing old session: {e}")

            # Save new bot token
            await save_user_bot(user_id, bot_token)
            return True
        except Exception as e:
            logger.error(f"Error setting bot token: {e}")
            return False

    @staticmethod
    async def remove_bot_token(user_id: int) -> bool:
        """Remove a bot token for a user."""
        try:
            if user_id in UB:
                try:
                    await UB[user_id].stop()
                except Exception as e:
                    logger.error(f"Error stopping bot: {e}")
                finally:
                    UB.pop(user_id, None)

            # Remove session file if exists
            try:
                session_file = f"user_{user_id}.session"
                if os.path.exists(session_file):
                    os.remove(session_file)
            except Exception as e:
                logger.error(f"Error removing session: {e}")

            await remove_user_bot(user_id)
            return True
        except Exception as e:
            logger.error(f"Error removing bot token: {e}")
            return False

# Command Handlers
@bot.on_message(filters.command('login'))
async def login_command(client: Client, message: Message) -> None:
    """Handle /login command to start authentication process."""
    user_id = message.from_user.id
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f'Could not delete message: {e}')

    set_user_step(user_id, STEP_PHONE)
    login_cache.pop(user_id, None)
    
    status_msg = await message.reply(
        "Please send your phone number with country code\n"
        "Example: `+12345678900`"
    )
    login_cache[user_id] = {'status_msg': status_msg}

@bot.on_message(filters.command("setbot"))
async def set_bot_token_handler(client: Client, message: Message) -> None:
    """Handle /setbot command to set a bot token."""
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.reply_text(
            "⚠️ Please provide a bot token.\nUsage: `/setbot token`",
            quote=True
        )
        return

    success = await BotTokenManager.set_bot_token(user_id, args[1].strip())
    await message.reply_text(
        "✅ Bot token saved successfully." if success 
        else "❌ Failed to save bot token",
        quote=True
    )

@bot.on_message(filters.command("rembot"))
async def rem_bot_token_handler(client: Client, message: Message) -> None:
    """Handle /rembot command to remove a bot token."""
    user_id = message.from_user.id
    success = await BotTokenManager.remove_bot_token(user_id)
    await message.reply_text(
        "✅ Bot token removed successfully." if success 
        else "❌ Failed to remove bot token",
        quote=True
    )

@bot.on_message(
    login_in_progress & 
    filters.text & 
    filters.private & 
    ~filters.command([
        'start', 'batch', 'cancel', 'login', 'logout', 'stop', 'set', 'pay',
        'redeem', 'gencode', 'generate', 'keyinfo', 'encrypt', 'decrypt', 
        'keys', 'setbot', 'rembot'
    ])
)
async def handle_login_steps(client: Client, message: Message) -> None:
    """Handle login process steps."""
    user_id = message.from_user.id
    text = message.text.strip()
    step = get_user_step(user_id)
    
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f'Could not delete message: {e}')

    # Get or create status message
    status_msg = login_cache.get(user_id, {}).get('status_msg')
    if not status_msg:
        status_msg = await message.reply('Processing...')
        login_cache[user_id]['status_msg'] = status_msg

    try:
        if step == STEP_PHONE:
            if not text.startswith('+'):
                await LoginManager.edit_message_safely(
                    status_msg,
                    '❌ Please provide a valid phone number starting with +'
                )
                return
            await LoginManager.handle_phone_step(user_id, text, status_msg)
            
        elif step == STEP_CODE:
            await LoginManager.handle_code_step(user_id, text, status_msg)
            
        elif step == STEP_PASSWORD:
            await LoginManager.handle_password_step(user_id, text, status_msg)
            
    except Exception as e:
        logger.error(f'Error in login flow: {str(e)}')
        await LoginManager.edit_message_safely(
            status_msg,
            f"❌ An error occurred: {str(e)}\nPlease try again with /login."
        )
        await LoginManager.cleanup_login_state(user_id)

@bot.on_message(filters.command('cancel'))
async def cancel_command(client: Client, message: Message) -> None:
    """Handle /cancel command to abort login process."""
    user_id = message.from_user.id
    await message.delete()
    
    if get_user_step(user_id):
        status_msg = login_cache.get(user_id, {}).get('status_msg')
        await LoginManager.cleanup_login_state(user_id)
        
        if status_msg:
            await LoginManager.edit_message_safely(
                status_msg,
                '✅ Login process cancelled. Use /login to start again.'
            )
        else:
            temp_msg = await message.reply(
                '✅ Login process cancelled. Use /login to start again.'
            )
            await temp_msg.delete(5)
    else:
        temp_msg = await message.reply('No active login process to cancel.')
        await temp_msg.delete(5)

@bot.on_message(filters.command('logout'))
async def logout_command(client: Client, message: Message) -> None:
    """Handle /logout command to terminate session."""
    user_id = message.from_user.id
    await message.delete()
    status_msg = await message.reply('🔄 Processing logout request...')
    
    try:
        session_data = await get_user_data(user_id)
        
        if not session_data or 'session_string' not in session_data:
            await LoginManager.edit_message_safely(
                status_msg,
                '❌ No active session found for your account.'
            )
            return
            
        # Decrypt and connect with session
        encss = session_data['session_string']
        session_string = dcs(encss)
        temp_client = Client(
            f'temp_logout_{user_id}',
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string
        )
        
        try:
            await temp_client.connect()
            await temp_client.log_out()
            await LoginManager.edit_message_safely(
                status_msg,
                '✅ Telegram session terminated successfully. '
                'Removing from database...'
            )
        except Exception as e:
            logger.error(f'Error terminating session: {str(e)}')
            await LoginManager.edit_message_safely(
                status_msg,
                f"⚠️ Error terminating Telegram session: {str(e)}\n"
                "Still removing from database..."
            )
        finally:
            await temp_client.disconnect()
            
        # Clean up
        await remove_user_session(user_id)
        if UC.get(user_id, None):
            del UC[user_id]
            
        # Remove session file if exists
        try:
            session_file = f"{user_id}_client.session"
            if os.path.exists(session_file):
                os.remove(session_file)
        except Exception as e:
            logger.error(f"Error removing session file: {e}")
            
        await LoginManager.edit_message_safely(
            status_msg,
            '✅ Logged out successfully!!'
        )
    except Exception as e:
        logger.error(f'Error in logout command: {str(e)}')
        try:
            await remove_user_session(user_id)
            if UC.get(user_id, None):
                del UC[user_id]
        except Exception as e:
            logger.error(f'Error during cleanup: {e}')
            
        await LoginManager.edit_message_safely(
            status_msg,
            f'❌ An error occurred during logout: {str(e)}'
        )