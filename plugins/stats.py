# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

from datetime import timedelta, datetime, timezone
from shared_client import client as bot_client # Assuming bot_client is Telethon
from telethon import events
from utils.func import (
    get_premium_details,
    is_private_chat,
    get_display_name,
    get_user_data,
    premium_users_collection, # Direct use, ensure it's appropriate or abstract further
    is_premium_user
)
from config import OWNER_ID
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__) # Consistent logger name

@bot_client.on(events.NewMessage(pattern='/status', chats=None)) # Allow from all chats, filter with is_private_chat
async def status_handler(event):
    if not await is_private_chat(event): # Ensure it's a private chat
        # Silently ignore or reply that it's private only
        # await event.respond("This command can only be used in private chats.")
        return

    user_id = event.sender_id
    user_data = await get_user_data(user_id) # Fetches all data for the user

    session_active = False
    custom_bot_active = False # Renamed for clarity

    if user_data:
        if user_data.get("session_string"): # More explicit check
            session_active = True
        if user_data.get("bot_token"): # Check for custom bot token
            custom_bot_active = True

    premium_status_message = "❌ Not a premium member"
    premium_details = await get_premium_details(user_id)

    if premium_details and premium_details.get("subscription_end"):
        expiry_utc = premium_details["subscription_end"]
        # Ensure expiry_utc is offset-aware before arithmetic if it's naive
        if expiry_utc.tzinfo is None:
            expiry_utc = expiry_utc.replace(tzinfo=timezone.utc)

        # Convert to IST timezone (UTC+5:30)
        try:
            ist_tz = timezone(timedelta(hours=5, minutes=30))
            expiry_ist = expiry_utc.astimezone(ist_tz)
            formatted_expiry = expiry_ist.strftime("%d-%b-%Y %I:%M:%S %p %Z")
            # Check if subscription is still active
            if datetime.now(timezone.utc) < expiry_utc:
                 premium_status_message = f"✅ Premium until {formatted_expiry}"
            else:
                 premium_status_message = f"❌ Premium expired on {formatted_expiry}"
        except Exception as e:
            logger.error(f"Error formatting premium expiry for {user_id}: {e}")
            premium_status_message = "✅ Premium (unable to format expiry)"


    status_lines = [
        "**Your current status:**\n",
        f"**👤 User Login Session:** {'✅ Active' if session_active else '❌ Inactive'}",
        f"**🤖 Custom Bot Configured:** {'✅ Active' if custom_bot_active else '❌ Inactive'}",
        f"**💎 Premium Membership:** {premium_status_message}"
    ]
    await event.respond("\n".join(status_lines))

@bot_client.on(events.NewMessage(pattern='/transfer', chats=None))
async def transfer_premium_handler(event):
    if not await is_private_chat(event):
        # await event.respond('This command can only be used in private chats for security reasons.')
        return

    user_id = event.sender_id
    sender = await event.get_sender()
    sender_name = get_display_name(sender) # Ensure this handles potential None sender

    if not await is_premium_user(user_id):
        await event.respond("❌ You don't have an active premium subscription to transfer.")
        return

    args = event.text.split()
    if len(args) != 2:
        await event.respond('Usage: /transfer <target_user_id>\nExample: /transfer 123456789')
        return

    try:
        target_user_id = int(args[1])
    except ValueError:
        await event.respond('❌ Invalid user ID. Please provide a valid numeric user ID.')
        return

    if target_user_id == user_id:
        await event.respond('❌ You cannot transfer premium to yourself.')
        return

    if await is_premium_user(target_user_id):
        await event.respond('❌ The target user already has an active premium subscription.')
        return

    try:
        premium_details = await get_premium_details(user_id)
        if not premium_details or "subscription_end" not in premium_details:
            await event.respond('❌ Error retrieving your premium details or subscription end date is missing.')
            return

        target_name = f"User ({target_user_id})" # Default name
        try:
            target_entity = await bot_client.get_entity(target_user_id)
            target_name = get_display_name(target_entity)
        except Exception as e:
            logger.warning(f'Could not get target user name for {target_user_id}: {e}')

        now_utc = datetime.now(timezone.utc)
        expiry_date_utc = premium_details['subscription_end']
        if expiry_date_utc.tzinfo is None: # Make sure it's offset-aware
            expiry_date_utc = expiry_date_utc.replace(tzinfo=timezone.utc)


        # Update target user's premium status
        await premium_users_collection.update_one(
            {'user_id': target_user_id},
            {'$set': {
                'user_id': target_user_id,
                'subscription_start': now_utc,
                'subscription_end': expiry_date_utc,
                'expireAt': expiry_date_utc, # For MongoDB TTL index
                'transferred_from': user_id,
                'transferred_from_name': sender_name,
                'last_updated': now_utc
            }},
            upsert=True
        )

        # Remove premium from the original user
        await premium_users_collection.delete_one({'user_id': user_id})

        ist_tz = timezone(timedelta(hours=5, minutes=30))
        formatted_expiry = expiry_date_utc.astimezone(ist_tz).strftime('%d-%b-%Y %I:%M:%S %p %Z')

        await event.respond(
            f'✅ Premium subscription successfully transferred to {target_name}. '
            f'Their premium is valid until {formatted_expiry}. Your premium access has been removed.'
        )

        try:
            await bot_client.send_message(
                target_user_id,
                f'🎁 You have received a premium subscription transfer from {sender_name} ({user_id}).\n'
                f'Your premium is valid until {formatted_expiry}.'
            )
        except Exception as e:
            logger.error(f'Could not notify target user {target_user_id} about transfer: {e}')

        # Notify owner(s)
        if OWNER_ID:
            owner_ids_list = [int(oid) for oid in str(OWNER_ID).split()] if isinstance(OWNER_ID, str) else OWNER_ID
            for owner in owner_ids_list:
                try:
                    await bot_client.send_message(
                        owner,
                        f'♻️ Premium Transfer Notification:\n'
                        f'From: {sender_name} ({user_id})\n'
                        f'To: {target_name} ({target_user_id})\n'
                        f'New Expiry: {formatted_expiry}'
                    )
                except Exception as e:
                    logger.error(f'Could not notify owner {owner} about premium transfer: {e}')

    except Exception as e:
        logger.error(f'Error transferring premium from {user_id} to {target_user_id}: {e}')
        await event.respond(f'❌ An unexpected error occurred while transferring premium: {str(e)}')


@bot_client.on(events.NewMessage(pattern='/rem', chats=None)) # Allow from all, then check owner
async def remove_premium_handler(event):
    user_id = event.sender_id
    if not await is_private_chat(event): # Command should be in private
        return
    # Ensure OWNER_ID is a list of integers for proper checking
    owner_ids_list = []
    if isinstance(OWNER_ID, (list, tuple)):
        owner_ids_list = [int(oid) for oid in OWNER_ID]
    elif isinstance(OWNER_ID, (int, str)): # handles single owner id
        try:
            owner_ids_list = [int(OWNER_ID)]
        except ValueError:
            logger.error("OWNER_ID is not a valid integer or list of integers.")
            return


    if user_id not in owner_ids_list:
        # await event.respond("This command is restricted to the bot owner.")
        return # Silently ignore if not owner

    args = event.text.split()
    if len(args) != 2:
        await event.respond('Usage: /rem <target_user_id>\nExample: /rem 123456789')
        return

    try:
        target_user_id_to_remove = int(args[1])
    except ValueError:
        await event.respond('❌ Invalid user ID. Please provide a valid numeric user ID.')
        return

    if not await is_premium_user(target_user_id_to_remove):
        await event.respond(f'❌ User {target_user_id_to_remove} does not have an active premium subscription.')
        return

    try:
        target_name_to_remove = f"User ({target_user_id_to_remove})" # Default
        try:
            target_entity_to_remove = await bot_client.get_entity(target_user_id_to_remove)
            target_name_to_remove = get_display_name(target_entity_to_remove)
        except Exception as e:
            logger.warning(f'Could not get target user name for {target_user_id_to_remove}: {e}')

        result = await premium_users_collection.delete_one({'user_id': target_user_id_to_remove})

        if result.deleted_count > 0:
            await event.respond(
                f'✅ Premium subscription successfully removed from {target_name_to_remove} ({target_user_id_to_remove}).'
            )
            try:
                await bot_client.send_message(
                    target_user_id_to_remove,
                    '⚠️ Your premium subscription has been removed by the administrator.'
                )
            except Exception as e:
                logger.error(f'Could not notify user {target_user_id_to_remove} about premium removal: {e}')
        else:
            # This case should ideally not be reached if is_premium_user was true,
            # but good for robustness.
            await event.respond(f'❌ Failed to remove premium from user {target_user_id_to_remove}. No matching record found, or already removed.')

    except Exception as e:
        logger.error(f'Error removing premium from {target_user_id_to_remove}: {e}')
        await event.respond(f'❌ An unexpected error occurred while removing premium: {str(e)}')
