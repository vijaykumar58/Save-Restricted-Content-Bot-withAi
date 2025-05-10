from datetime import datetime, timedelta
from typing import Optional, Union, List
from telethon import events
from shared_client import client as bot_client
from utils.func import (
    get_premium_details,
    is_private_chat,
    get_display_name,
    get_user_data,
    premium_users_collection,
    is_premium_user
)
from config import OWNER_ID
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('teamspy')

class PremiumManager:
    @staticmethod
    async def transfer_premium(
        sender_id: int,
        sender_name: str,
        target_user_id: int,
        event: events.NewMessage.Event
    ) -> bool:
        """Transfer premium subscription from one user to another."""
        try:
            # Get sender's premium details
            premium_details = await get_premium_details(sender_id)
            if not premium_details:
                await event.respond('❌ Error retrieving your premium details.')
                return False

            # Get target user info
            target_name = 'Unknown'
            try:
                target_entity = await bot_client.get_entity(target_user_id)
                target_name = get_display_name(target_entity)
            except Exception as e:
                logger.warning(f'Could not get target user name: {e}')

            # Update database
            expiry_date = premium_details['subscription_end']
            await premium_users_collection.update_one(
                {'user_id': target_user_id},
                {'$set': {
                    'user_id': target_user_id,
                    'subscription_start': datetime.now(),
                    'subscription_end': expiry_date,
                    'expireAt': expiry_date,
                    'transferred_from': sender_id,
                    'transferred_from_name': sender_name
                }},
                upsert=True
            )
            await premium_users_collection.delete_one({'user_id': sender_id})

            # Format expiry time for display
            expiry_ist = expiry_date + timedelta(hours=5, minutes=30)
            formatted_expiry = expiry_ist.strftime('%d-%b-%Y %I:%M:%S %p')

            # Notify users
            await event.respond(
                f'✅ Premium transferred to {target_name} ({target_user_id}).\n'
                f'Your premium access has been removed.'
            )

            try:
                await bot_client.send_message(
                    target_user_id,
                    f'🎁 You received premium from {sender_name} ({sender_id}).\n'
                    f'Valid until: {formatted_expiry} (IST)'
                )
            except Exception as e:
                logger.error(f'Could not notify target user: {e}')

            # Notify owner
            try:
                owner_id = OWNER_ID[0] if isinstance(OWNER_ID, list) else OWNER_ID
                await bot_client.send_message(
                    owner_id,
                    f'♻️ Premium Transfer:\n'
                    f'From: {sender_name} ({sender_id})\n'
                    f'To: {target_name} ({target_user_id})\n'
                    f'Expiry: {formatted_expiry}'
                )
            except Exception as e:
                logger.error(f'Could not notify owner: {e}')

            return True

        except Exception as e:
            logger.error(f'Premium transfer error: {e}')
            await event.respond(f'❌ Transfer failed: {str(e)}')
            return False

    @staticmethod
    async def remove_premium(
        admin_id: int,
        target_user_id: int,
        event: events.NewMessage.Event
    ) -> bool:
        """Remove premium subscription from a user."""
        try:
            # Check if target has premium
            if not await is_premium_user(target_user_id):
                await event.respond(f'❌ User {target_user_id} has no premium.')
                return False

            # Get target user info
            target_name = 'Unknown'
            try:
                target_entity = await bot_client.get_entity(target_user_id)
                target_name = get_display_name(target_entity)
            except Exception as e:
                logger.warning(f'Could not get target user name: {e}')

            # Remove premium
            result = await premium_users_collection.delete_one(
                {'user_id': target_user_id}
            )

            if result.deleted_count > 0:
                await event.respond(
                    f'✅ Removed premium from {target_name} ({target_user_id}).'
                )
                try:
                    await bot_client.send_message(
                        target_user_id,
                        '⚠️ Your premium subscription was removed by admin.'
                    )
                except Exception as e:
                    logger.error(f'Could not notify user: {e}')
                return True
            else:
                await event.respond(f'❌ Failed to remove premium.')
                return False

        except Exception as e:
            logger.error(f'Premium removal error: {e}')
            await event.respond(f'❌ Removal failed: {str(e)}')
            return False

class StatusManager:
    @staticmethod
    def format_ist_time(utc_time: datetime) -> str:
        """Convert UTC time to IST formatted string."""
        ist_time = utc_time + timedelta(hours=5, minutes=30)
        return ist_time.strftime('%d-%b-%Y %I:%M:%S %p')

    @staticmethod
    async def get_user_status(user_id: int) -> str:
        """Generate status message for a user."""
        user_data = await get_user_data(user_id)
        
        # Check session status
        session_status = '✅ Active' if user_data and "session_string" in user_data else '❌ Inactive'
        
        # Check premium status
        premium_details = await get_premium_details(user_id)
        if premium_details:
            expiry_time = StatusManager.format_ist_time(premium_details["subscription_end"])
            premium_status = f"✅ Premium until {expiry_time} (IST)"
        else:
            premium_status = "❌ Not a premium member"
        
        # Check bot status
        bot_status = '✅ Active' if user_data and "bot_token" in user_data else '❌ Inactive'
        
        return (
            "**Your current status:**\n\n"
            f"**Login Status:** {session_status}\n"
            f"**Bot Status:** {bot_status}\n"
            f"**Premium:** {premium_status}"
        )

# Command Handlers
@bot_client.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    """Handle /status command to check user session and bot status"""
    if not await is_private_chat(event):
        await event.respond("This command can only be used in private chats.")
        return
    
    status_message = await StatusManager.get_user_status(event.sender_id)
    await event.respond(status_message)

@bot_client.on(events.NewMessage(pattern='/transfer'))
async def transfer_handler(event):
    """Handle premium transfer between users"""
    if not await is_private_chat(event):
        await event.respond('This command can only be used in private chats.')
        return
    
    # Check premium status
    user_id = event.sender_id
    if not await is_premium_user(user_id):
        await event.respond("❌ You don't have a premium subscription to transfer.")
        return
    
    # Validate command format
    args = event.text.split()
    if len(args) != 2:
        await event.respond('Usage: /transfer user_id\nExample: /transfer 123456789')
        return
    
    # Validate target user ID
    try:
        target_user_id = int(args[1])
    except ValueError:
        await event.respond('❌ Invalid user ID. Must be numeric.')
        return
    
    # Prevent self-transfer
    if target_user_id == user_id:
        await event.respond('❌ Cannot transfer to yourself.')
        return
    
    # Check if target already has premium
    if await is_premium_user(target_user_id):
        await event.respond('❌ Target user already has premium.')
        return
    
    # Get sender info
    sender = await event.get_sender()
    sender_name = get_display_name(sender)
    
    # Perform transfer
    await PremiumManager.transfer_premium(
        user_id,
        sender_name,
        target_user_id,
        event
    )

@bot_client.on(events.NewMessage(pattern='/rem'))
async def remove_premium_handler(event):
    """Handle premium removal by admin"""
    if not await is_private_chat(event):
        return
    
    # Check admin privileges
    user_id = event.sender_id
    if user_id not in OWNER_ID:
        return
    
    # Validate command format
    args = event.text.split()
    if len(args) != 2:
        await event.respond('Usage: /rem user_id\nExample: /rem 123456789')
        return
    
    # Validate target user ID
    try:
        target_user_id = int(args[1])
    except ValueError:
        await event.respond('❌ Invalid user ID. Must be numeric.')
        return
    
    # Perform removal
    await PremiumManager.remove_premium(user_id, target_user_id, event)