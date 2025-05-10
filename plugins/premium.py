from datetime import timedelta
from typing import Optional, Tuple
import base64
import logging

from telethon import events
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from shared_client import client as bot_client, app
from config import OWNER_ID
from utils.func import (
    add_premium_user,
    is_private_chat,
    a1, a2, a3, a4, a5, a7, a8, a9, a10, a11
)
from plugins.start import subscribe

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class PremiumManager:
    VALID_DURATION_UNITS = [
        'min', 'hours', 'days', 'weeks', 'month', 'year', 'decades'
    ]

    @staticmethod
    def decode_base64(data: str) -> str:
        """Safely decode base64 encoded strings."""
        try:
            return base64.b64decode(data.encode()).decode()
        except Exception as e:
            logger.error(f"Base64 decoding error: {e}")
            return ""

    @staticmethod
    async def add_premium_user_handler(event) -> None:
        """Handle /add command to add premium users."""
        if not await is_private_chat(event):
            await event.respond(
                "This command can only be used in private chats."
            )
            return

        if event.sender_id not in OWNER_ID:
            await event.respond("❌ This command is owner-restricted.")
            return

        parts = event.message.text.strip().split()
        if len(parts) != 4:
            await event.respond(
                "Usage: /add user_id duration_value duration_unit\n"
                "Example: /add 123456 1 week"
            )
            return

        try:
            target_user_id = int(parts[1])
            duration_value = int(parts[2])
            duration_unit = parts[3].lower()

            if duration_unit not in PremiumManager.VALID_DURATION_UNITS:
                await event.respond(
                    f"❌ Invalid unit. Valid units: {', '.join(PremiumManager.VALID_DURATION_UNITS)}"
                )
                return

            success, result = await add_premium_user(
                target_user_id,
                duration_value,
                duration_unit
            )

            if success:
                expiry_utc = result
                expiry_ist = expiry_utc + timedelta(hours=5, minutes=30)
                formatted_expiry = expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')

                await event.respond(
                    f"✅ User {target_user_id} added as premium\n"
                    f"Valid until: {formatted_expiry} (IST)"
                )

                try:
                    await bot_client.send_message(
                        target_user_id,
                        f"🎉 You've been granted premium access!\n"
                        f"Valid until: {formatted_expiry} (IST)"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user: {e}")
            else:
                await event.respond(f"❌ Failed to add premium: {result}")

        except ValueError:
            await event.respond("❌ Invalid user ID or duration value")
        except Exception as e:
            logger.error(f"Premium add error: {e}")
            await event.respond(f"❌ An error occurred: {str(e)}")

class StartHandler:
    @staticmethod
    async def handle_start_command(client, message) -> None:
        """Handle /start command with welcome message."""
        subscription_status = await subscribe(client, message)
        if subscription_status == 1:
            return

        # Decode all base64 strings
        decoded = {
            'a1': PremiumManager.decode_base64(a1),
            'a2': int(PremiumManager.decode_base64(a2)),
            'a3': PremiumManager.decode_base64(a3),
            'a4': PremiumManager.decode_base64(a4),
            'a7': PremiumManager.decode_base64(a7),
            'a8': PremiumManager.decode_base64(a8),
            'a9': PremiumManager.decode_base64(a9),
            'a10': PremiumManager.decode_base64(a10),
            'a11': PremiumManager.decode_base64(a11),
            'attr1': PremiumManager.decode_base64("photo"),
            'attr2': PremiumManager.decode_base64("file_id"),
            'a5': PremiumManager.decode_base64(a5)
        }

        try:
            # Get photo message
            tm = await getattr(app, decoded['a3'])(
                decoded['a1'],
                decoded['a2']
            )

            # Extract file_id from photo
            pb = getattr(tm, decoded['attr1'])
            fd = getattr(pb, decoded['attr2'])

            # Create inline keyboard
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    decoded['a8'],
                    url=decoded['a10']
                )],
                [InlineKeyboardButton(
                    decoded['a9'],
                    url=decoded['a11']
                )]
            ])

            # Send welcome message
            await getattr(message, decoded['a4'])(
                fd,
                caption=decoded['a7'],
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Start command error: {e}")
            await message.reply(
                "Welcome! Use /help to see available commands."
            )

# Register command handlers
@bot_client.on(events.NewMessage(pattern='/add'))
async def add_premium_command_handler(event):
    await PremiumManager.add_premium_user_handler(event)

@app.on_message(filters.command(PremiumManager.decode_base64(a5)))
async def start_command_handler(client, message):
    await StartHandler.handle_start_command(client, message)