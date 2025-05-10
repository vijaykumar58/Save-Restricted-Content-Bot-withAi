from shared_client import app
from pyrogram import filters
from pyrogram.errors import UserNotParticipant, ChatAdminRequired
from pyrogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from config import LOG_GROUP, OWNER_ID, FORCE_SUB
from typing import Optional, Tuple
import logging

# Configure logging
logger = logging.getLogger(__name__)

class SubscriptionManager:
    @staticmethod
    async def check_subscription(client, message) -> Optional[bool]:
        """Check if user is subscribed to the force sub channel."""
        if not FORCE_SUB:
            return None
            
        try:
            user = await client.get_chat_member(FORCE_SUB, message.from_user.id)
            if user.status == "banned":
                await message.reply_text("⛔ You are banned. Contact @TeamSPY_Support")
                return True
            return False
        except UserNotParticipant:
            try:
                link = await client.export_chat_invite_link(FORCE_SUB)
                caption = "🔒 Join our channel to use this bot"
                await message.reply_photo(
                    photo="https://graph.org/file/d44f024a08ded19452152.jpg",
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("👉 Join Channel", url=link)
                    ]])
                )
                return True
            except ChatAdminRequired:
                logger.error(f"Bot needs admin rights in force sub channel {FORCE_SUB}")
                await message.reply_text("⚠️ Bot configuration error. Please notify admin.")
                return True
            except Exception as e:
                logger.error(f"Subscription check error: {e}")
                await message.reply_text("⚠️ An error occurred. Please try again later.")
                return True
        except Exception as e:
            logger.error(f"Unexpected subscription error: {e}")
            await message.reply_text("⚠️ System error. Contact admin.")
            return True

class CommandManager:
    BOT_COMMANDS = [
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("batch", "🫠 Extract in bulk"),
        BotCommand("login", "🔑 Get into the bot"),
        BotCommand("setbot", "🧸 Add your bot for handling files"),
        BotCommand("logout", "🚪 Get out of the bot"),
        BotCommand("adl", "👻 Download audio from 30+ sites"),
        BotCommand("dl", "💀 Download videos from 30+ sites"),
        BotCommand("status", "⟳ Refresh Payment status"),
        BotCommand("transfer", "💘 Gift premium to others"),
        BotCommand("add", "➕ Add user to premium"),
        BotCommand("rem", "➖ Remove from premium"),
        BotCommand("rembot", "🤨 Remove your custom bot"),
        BotCommand("settings", "⚙️ Personalize things"),
        BotCommand("plan", "🗓️ Check our premium plans"),
        BotCommand("terms", "🥺 Terms and conditions"),
        BotCommand("help", "❓ If you're a noob, still!"),
        BotCommand("cancel", "🚫 Cancel login/batch/settings process"),
        BotCommand("stop", "🚫 Cancel batch process")
    ]

    @staticmethod
    async def set_bot_commands(client, message):
        """Set bot commands for the user."""
        if message.from_user.id not in OWNER_ID:
            await message.reply("🔒 You are not authorized to use this command.")
            return

        try:
            await client.set_bot_commands(CommandManager.BOT_COMMANDS)
            await message.reply("✅ Bot commands configured successfully!")
            logger.info(f"Bot commands updated by {message.from_user.id}")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")
            await message.reply("⚠️ Failed to update commands. Check logs.")

class HelpManager:
    PAGES = [
        (
            "📝 **Bot Commands Overview (1/2)**:\n\n"
            "1. **/add userID**\n"
            "> Add user to premium (Owner only)\n\n"
            "2. **/rem userID**\n"
            "> Remove user from premium (Owner only)\n\n"
            "3. **/transfer userID**\n"
            "> Transfer premium to others (Premium users)\n\n"
            "4. **/get**\n"
            "> Get all user IDs (Owner only)\n\n"
            "5. **/lock**\n"
            "> Lock channel from extraction (Owner only)\n\n"
            "6. **/dl link**\n"
            "> Download videos\n\n"
            "7. **/adl link**\n"
            "> Download audio\n\n"
            "8. **/login**\n"
            "> Log into the bot\n\n"
            "9. **/batch**\n"
            "> Bulk extraction\n\n"
        ),
        (
            "📝 **Bot Commands Overview (2/2)**:\n\n"
            "10. **/logout**\n"
            "> Logout from the bot\n\n"
            "11. **/stats**\n"
            "> Get bot stats\n\n"
            "12. **/plan**\n"
            "> Check premium plans\n\n"
            "13. **/speedtest**\n"
            "> Test server speed\n\n"
            "14. **/terms**\n"
            "> Terms and conditions\n\n"
            "15. **/cancel**\n"
            "> Cancel ongoing process\n\n"
            "16. **/myplan**\n"
            "> Check your plan details\n\n"
            "17. **/session**\n"
            "> Generate Pyrogram session\n\n"
            "18. **/settings**\n"
            "> Customize bot behavior\n\n"
            "**__Powered by Team SPY__**"
        )
    ]

    @staticmethod
    async def send_help_page(client, message, page: int = 0):
        """Send or edit help page with navigation buttons."""
        if page < 0 or page >= len(HelpManager.PAGES):
            return

        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"help_prev_{page}"))
        if page < len(HelpManager.PAGES) - 1:
            buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"help_next_{page}"))

        keyboard = InlineKeyboardMarkup([buttons]) if buttons else None

        try:
            if message.id:  # Edit existing message
                await message.edit_text(
                    HelpManager.PAGES[page],
                    reply_markup=keyboard
                )
            else:  # Send new message
                await message.reply_text(
                    HelpManager.PAGES[page],
                    reply_markup=keyboard
                )
        except Exception as e:
            logger.error(f"Help page error: {e}")

class TermsManager:
    TERMS_TEXT = (
        "📜 **Terms and Conditions**\n\n"
        "🔹 We are not responsible for user actions\n"
        "🔹 No guarantees on service uptime\n"
        "🔹 Authorization is at our discretion\n"
        "🔹 Payments don't guarantee access\n"
    )

    PLAN_TEXT = (
        "💰 **Premium Plans**\n\n"
        "🔸 Starting from $2 or 200 INR\n"
        "🔸 Amazon Gift Cards accepted\n"
        "🔸 100,000 files per batch\n"
        "🔸 /batch and /bulk modes\n"
    )

    @staticmethod
    def get_terms_markup():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 See Plans", callback_data="see_plan")],
            [InlineKeyboardButton("💬 Contact", url="https://t.me/kingofpatal")]
        ])

    @staticmethod
    def get_plan_markup():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 See Terms", callback_data="see_terms")],
            [InlineKeyboardButton("💬 Contact", url="https://t.me/kingofpatal")]
        ])

# Command Handlers
@app.on_message(filters.command("set") & filters.user(OWNER_ID))
async def set_commands_handler(_, message):
    await CommandManager.set_bot_commands(app, message)

@app.on_message(filters.command("help"))
async def help_handler(client, message):
    is_blocked = await SubscriptionManager.check_subscription(client, message)
    if is_blocked:
        return
    await HelpManager.send_help_page(client, message)

@app.on_callback_query(filters.regex(r"help_(prev|next)_(\d+)"))
async def help_navigation_handler(client, callback_query):
    action, page = callback_query.data.split("_")[1], int(callback_query.data.split("_")[2])
    page = page - 1 if action == "prev" else page + 1
    await HelpManager.send_help_page(client, callback_query.message, page)
    await callback_query.answer()

@app.on_message(filters.command("terms") & filters.private)
async def terms_handler(_, message):
    await message.reply_text(
        TermsManager.TERMS_TEXT,
        reply_markup=TermsManager.get_terms_markup()
    )

@app.on_message(filters.command("plan") & filters.private)
async def plan_handler(_, message):
    await message.reply_text(
        TermsManager.PLAN_TEXT,
        reply_markup=TermsManager.get_plan_markup()
    )

@app.on_callback_query(filters.regex("see_(plan|terms)"))
async def terms_plan_toggle_handler(client, callback_query):
    action = callback_query.data.split("_")[1]
    
    if action == "plan":
        text = TermsManager.PLAN_TEXT
        markup = TermsManager.get_plan_markup()
    else:
        text = TermsManager.TERMS_TEXT
        markup = TermsManager.get_terms_markup()
    
    await callback_query.message.edit_text(text, reply_markup=markup)
    await callback_query.answer()