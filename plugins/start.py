# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

from shared_client import app
from pyrogram import filters
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, RightForbidden
from pyrogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from config import LOG_GROUP, OWNER_ID, FORCE_SUB # Ensure LOG_GROUP is used or remove if not needed

async def subscribe(client_instance, message): # Renamed 'app' to 'client_instance' for clarity
    if not FORCE_SUB: # If FORCE_SUB is not set, or is 0/None
        return 0 # No subscription required

    try:
        user = await client_instance.get_chat_member(FORCE_SUB, message.from_user.id)
        if user.status == "kicked": # More specific check for banned
            await message.reply_text("You are Banned. Contact -- Team SPY")
            return 1
    except UserNotParticipant:
        try:
            link = await client_instance.export_chat_invite_link(FORCE_SUB)
            caption = "Join our channel to use the bot."
            # Consider a more generic image or no image if it's frequently unavailable
            await message.reply_photo(
                photo="https://graph.org/file/d44f024a08ded19452152.jpg", # This URL might become invalid
                caption=caption,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Now...", url=link)]])
            )
        except (ChatAdminRequired, RightForbidden):
             await message.reply_text("I need to be an admin in the force subscribe channel to get invite link.")
        except Exception as e: # Catch other potential errors during invite link export or message sending
            await message.reply_text(f"Could not verify subscription: {e}")
        return 1
    except (ChatAdminRequired, RightForbidden): # If bot is not admin in FORCE_SUB channel
        await message.reply_text(f"I am not an admin in the channel {FORCE_SUB}, so I cannot check your membership.")
        return 1 # Treat as subscription failed if check cannot be performed
    except Exception as ggn:
        await message.reply_text(f"Something Went Wrong. Contact admins... with following message: {ggn}")
        return 1
    return 0 # User is participant or no force sub

@app.on_message(filters.command("set") & filters.user(OWNER_ID)) # Ensure OWNER_ID is correctly loaded
async def set_commands_handler(_, message): # Renamed 'set' to 'set_commands_handler'
    # Removed check `if message.from_user.id not in OWNER_ID:` as filters.user(OWNER_ID) handles it.
    try:
        await app.set_bot_commands([
            BotCommand("start", "🚀 Start the bot"),
            BotCommand("help", "❓ If you're a noob, still!"),
            BotCommand("settings", "⚙️ Personalize things"),
            BotCommand("batch", "🫠 Extract in bulk"),
            BotCommand("single", "☝️ Extract a single post"),
            BotCommand("login", "🔑 Get into the bot (user session)"),
            BotCommand("logout", "🚪 Get out of the bot (user session)"),
            BotCommand("setbot", "🧸 Add your bot for handling files"),
            BotCommand("rembot", "🤨 Remove your custom bot"),
            BotCommand("status", "📊 Check your current status"),
            BotCommand("myplan", "💎 Get details about your plans"), # Added
            # BotCommand("adl", "👻 Download audio from 30+ sites"), # Marked as not in v3
            # BotCommand("dl", "💀 Download videos from 30+ sites"), # Marked as not in v3
            BotCommand("plan", "🗓️ Check our premium plans"),
            BotCommand("terms", "🥺 Terms and conditions"),
            BotCommand("cancel", "🚫 Cancel login/batch/settings process"),
            BotCommand("stop", "🛑 Cancel active batch process"), # Clarified
            # Admin/Owner commands (conditionally show or document separately)
            BotCommand("add", "➕ Add user to premium (Owner)"),
            # BotCommand("rem", "➖ Remove from premium (Owner)"), # Covered by /transfer logic or separate
            # BotCommand("transfer", "💘 Gift premium to others"), # For premium users or owner
        ])
        await message.reply("✅ Bot commands configured successfully!")
    except Exception as e:
        await message.reply(f"Error setting bot commands: {e}")


help_pages = [
    (
        "📝 **Bot Commands Overview (Page 1/2)**:\n\n"
        "**General Commands:**\n"
        "• **/start**: 🚀 Start the bot & see welcome message.\n"
        "• **/help**: ❓ Display this help message.\n"
        "• **/settings**: ⚙️ Customize your file handling preferences (rename, caption, etc.).\n"
        "• **/status**: 📊 Check your login, premium, and custom bot status.\n"
        "• **/plan**: 🗓️ View available premium plans.\n"
        "• **/terms**: 🥺 Read the terms and conditions.\n"
        "• **/myplan**: 💎 Check your current premium subscription details.\n\n"
        "**Extraction Commands:**\n"
        "• **/batch**: 🫠 Extract multiple posts from a channel/group.\n"
        "• **/single**: ☝️ Extract a single post using its link.\n\n"
        "**Session Management (for private content):**\n"
        "• **/login**: 🔑 Log in with your Telegram account (user session) to access private channels/groups.\n"
        "• **/logout**: 🚪 Log out of your Telegram user session.\n\n"
        "**Custom Bot (for uploads):**\n"
        "• **/setbot [TOKEN]**: 🧸 Set up your own bot to handle uploads.\n"
        "• **/rembot**: 🤨 Remove your custom bot configuration."
    ),
    (
        "📝 **Bot Commands Overview (Page 2/2)**:\n\n"
        "**Process Management:**\n"
        "• **/cancel**: 🚫 Cancel an ongoing operation like login, settings configuration, or batch setup.\n"
        "• **/stop**: 🛑 Stop an active batch processing task.\n\n"
        # YTDL commands are in a separate file and might be conditionally available.
        # "✨ **Media Downloads (External Sites):**\n"
        # "• **/dl [LINK]**: 💀 Download videos from various sites (e.g., YouTube, Instagram).\n"
        # "• **/adl [LINK]**: 👻 Download audio from various sites.\n\n"
        "🔒 **Owner-Only Commands:**\n"
        "• **/add [USER_ID] [DUR_VAL] [DUR_UNIT]**: Add premium (e.g., `/add 123456 1 month`).\n"
        "• **/rem [USER_ID]**: Remove premium status from a user.\n"
        "• **/transfer [TARGET_USER_ID]**: Transfer your premium to another user (if you are premium).\n"
        # "• **/get**: Get all user IDs.\n" # Sensitive, ensure it's properly restricted
        # "• **/lock**: Lock channel from extraction.\n" # Implementation details needed
        "• **/set**: ✨ Initialize/Update bot commands list.\n\n"
        "⚙️ **Settings Details (`/settings`):**\n"
        "  - **Set Chat ID**: Specify a default chat/channel/topic for uploads.\n"
        "  - **Set Rename Tag**: Add a suffix to filenames (e.g., your channel name).\n"
        "  - **Set Caption**: Define a custom caption for uploaded files.\n"
        "  - **Replace Words**: Automatically replace specific words in filenames/captions.\n"
        "  - **Remove Words**: Automatically delete specific words from filenames/captions.\n"
        "  - **Set/Remove Thumbnail**: Manage custom thumbnails for uploads.\n"
        "  - **Session Login/Logout**: Manage your user session directly from settings.\n"
        "  - **Reset**: Revert all your custom settings to default.\n\n"
        "**__Powered by Team SPY__**"
    )
]


current_help_message = {} # Stores {chat_id: message_id} for editing

async def send_or_edit_help_page(client, chat_id, user_id, page_number, edit_message_id=None):
    if not (0 <= page_number < len(help_pages)):
        return

    text = help_pages[page_number]
    buttons = []
    if page_number > 0:
        buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"help_prev_{page_number}"))
    if page_number < len(help_pages) - 1:
        buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"help_next_{page_number}"))

    keyboard = InlineKeyboardMarkup([buttons]) if buttons else None

    if edit_message_id:
        try:
            await client.edit_message_text(chat_id, edit_message_id, text, reply_markup=keyboard)
        except Exception: # If edit fails, send new message
            msg = await client.send_message(chat_id, text, reply_markup=keyboard)
            current_help_message[chat_id] = msg.id
    else:
        msg = await client.send_message(chat_id, text, reply_markup=keyboard)
        current_help_message[chat_id] = msg.id

@app.on_message(filters.command("help"))
async def help_command(client, message): # Renamed 'help' to 'help_command'
    join_status = await subscribe(client, message)
    if join_status == 1:
        return

    # If a help message already exists for this chat, delete it or edit it.
    # For simplicity, we'll just send a new one and store its ID.
    # A more robust approach would involve deleting the old one if current_help_message[message.chat.id] exists.
    if message.chat.id in current_help_message:
        try:
            await client.delete_messages(message.chat.id, current_help_message[message.chat.id])
        except Exception:
            pass # Old message might not exist
        del current_help_message[message.chat.id]

    await send_or_edit_help_page(client, message.chat.id, message.from_user.id, 0)
    try:
      await message.delete() # Delete the original /help command
    except Exception:
      pass


@app.on_callback_query(filters.regex(r"help_(prev|next)_(\d+)"))
async def on_help_navigation(client, callback_query):
    action, page_number_str = callback_query.data.split("_")[1], callback_query.data.split("_")[2]
    page_number = int(page_number_str)

    if action == "prev":
        page_number -= 1
    elif action == "next":
        page_number += 1

    # Ensure the message to edit is the one we sent
    if callback_query.message.id == current_help_message.get(callback_query.message.chat.id):
        await send_or_edit_help_page(client, callback_query.message.chat.id, callback_query.from_user.id, page_number, edit_message_id=callback_query.message.id)
    else: # If the message ID doesn't match, maybe it was deleted or it's an old button.
        await callback_query.answer("Please use the latest /help command.", show_alert=True)
        return

    await callback_query.answer()


@app.on_message(filters.command("terms") & filters.private)
async def terms_command(client, message): # Renamed 'terms' to 'terms_command'
    terms_text = (
        "> 📜 **Terms and Conditions** 📜\n\n"
        "✨ We are not responsible for user deeds, and we do not promote copyrighted content. If any user engages in such activities, it is solely their responsibility.\n"
        "✨ Upon purchase, we do not guarantee the uptime, downtime, or the validity of the plan. __Authorization and banning of users are at our discretion; we reserve the right to ban or authorize users at any time.__\n"
        "✨ Payment to us **__does not guarantee__** authorization for the /batch command or any specific feature. All decisions regarding feature access and authorization are made at our discretion.\n"
    )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 See Plans", callback_data="nav_plan")],
            [InlineKeyboardButton("💬 Contact Support", url="https://t.me/kingofpatal")] # Example URL
        ]
    )
    await message.reply_text(terms_text, reply_markup=buttons)

@app.on_message(filters.command("plan") & filters.private)
async def plan_command(client, message): # Renamed 'plan' to 'plan_command'
    plan_text = (
        "> 💰 **Premium Plan Information**:\n\n"
        "🌟 **Starting Price**: $2 or 200 INR (Accepted via Amazon Gift Card, other methods may be available - T&C apply).\n"
        "📦 **Batch Limit**: Premium users can typically process a large number of files per /batch command (e.g., up to 100,000, subject to change).\n"
        "⚙️ **Features**: Access to advanced features, potentially higher limits, and priority support.\n"
        "⏳ **Process Handling**: For large batch operations, please allow time for completion. Use /stop if you need to cancel.\n\n"
        "📜 **Terms**: For detailed terms and conditions, please use the /terms command.\n"
    )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📜 See Terms", callback_data="nav_terms")],
            [InlineKeyboardButton("💬 Contact to Purchase", url="https://t.me/kingofpatal")] # Example URL
        ]
    )
    await message.reply_text(plan_text, reply_markup=buttons)

@app.on_callback_query(filters.regex("nav_plan"))
async def nav_plan_callback(client, callback_query):
    # This is essentially the same as /plan command, show plan text
    plan_text = (
        "> 💰 **Premium Plan Information**:\n\n"
        "🌟 **Starting Price**: $2 or 200 INR (Accepted via Amazon Gift Card, other methods may be available - T&C apply).\n"
        "📦 **Batch Limit**: Premium users can typically process a large number of files per /batch command (e.g., up to 100,000, subject to change).\n"
        "⚙️ **Features**: Access to advanced features, potentially higher limits, and priority support.\n"
        "⏳ **Process Handling**: For large batch operations, please allow time for completion. Use /stop if you need to cancel.\n\n"
        "📜 **Terms**: For detailed terms and conditions, please use the /terms command.\n"
    )
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📜 See Terms", callback_data="nav_terms")],
            [InlineKeyboardButton("💬 Contact to Purchase", url="https://t.me/kingofpatal")]
        ]
    )
    try:
        await callback_query.message.edit_text(plan_text, reply_markup=buttons)
    except Exception as e: # Handle message not modified, etc.
        print(f"Error editing message for nav_plan: {e}")
        await callback_query.answer("Displaying plan details.") # Fallback
        # Could resend if edit fails badly
    await callback_query.answer()

@app.on_callback_query(filters.regex("nav_terms"))
async def nav_terms_callback(client, callback_query):
    # This is essentially the same as /terms command, show terms text
    terms_text = (
        "> 📜 **Terms and Conditions** 📜\n\n"
        "✨ We are not responsible for user deeds, and we do not promote copyrighted content. If any user engages in such activities, it is solely their responsibility.\n"
        "✨ Upon purchase, we do not guarantee the uptime, downtime, or the validity of the plan. __Authorization and banning of users are at our discretion; we reserve the right to ban or authorize users at any time.__\n"
        "✨ Payment to us **__does not guarantee__** authorization for the /batch command or any specific feature. All decisions regarding feature access and authorization are made at our discretion.\n"
    )
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 See Plans", callback_data="nav_plan")],
            [InlineKeyboardButton("💬 Contact Support", url="https://t.me/kingofpatal")]
        ]
    )
    try:
        await callback_query.message.edit_text(terms_text, reply_markup=buttons)
    except Exception as e:
        print(f"Error editing message for nav_terms: {e}")
        await callback_query.answer("Displaying terms and conditions.") # Fallback
    await callback_query.answer()
