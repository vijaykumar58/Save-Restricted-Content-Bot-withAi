from telethon import TelegramClient
from config import API_ID, API_HASH, BOT_TOKEN, STRING
from pyrogram import Client
import sys
import asyncio
from typing import Tuple, Optional

# Initialize clients with type hints
client: TelegramClient = TelegramClient("telethonbot", API_ID, API_HASH)
app: Client = Client("pyrogrambot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
userbot: Optional[Client] = None

if STRING:
    userbot = Client("4gbbot", api_id=API_ID, api_hash=API_HASH, session_string=STRING)

async def start_client() -> Tuple[TelegramClient, Client, Optional[Client]]:
    """
    Start all Telegram clients and return them as a tuple.
    
    Returns:
        Tuple containing (telethon_client, pyrogram_bot_client, pyrogram_user_client)
    """
    try:
        # Start Telethon client
        if not client.is_connected():
            await client.start(bot_token=BOT_TOKEN)
            print("SpyLib Telethon client started successfully")
        
        # Start Pyrogram user client if STRING is available
        if STRING and userbot:
            try:
                if not await userbot.start():
                    await userbot.start()
                print("Userbot started successfully")
            except Exception as e:
                print(f"Error starting userbot: {e}")
                print("Please check your premium string session - it may be invalid or expired")
                sys.exit(1)
        
        # Start Pyrogram bot client
        if not await app.start():
            await app.start()
        print("Pyrogram bot client started successfully")
        
        return client, app, userbot
    
    except Exception as e:
        print(f"Fatal error during client startup: {e}")
        sys.exit(1)