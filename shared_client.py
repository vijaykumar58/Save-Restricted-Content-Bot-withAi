# Copyright (c) 2025 devgagan : https://github.com/devgaganin.  
# Licensed under the GNU General Public License v3.0.  
# See LICENSE file in the repository root for full license text.

from telethon import TelegramClient
from config import API_ID, API_HASH, BOT_TOKEN, STRING
from pyrogram import Client
import sys
import asyncio # Added for ensure_future if needed, though not directly used here now

# Consider defining client instances globally but starting them in an async function
# This avoids issues with event loops if this module is imported before an event loop is set.
client = None
app = None
userbot = None

async def start_client():
    global client, app, userbot

    if client is None:
        client = TelegramClient("telethonbot", API_ID, API_HASH)
    
    if app is None:
        app = Client("pyrogrambot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

    if STRING and userbot is None:
        userbot = Client("4gbbot", api_id=API_ID, api_hash=API_HASH, session_string=STRING)

    if not client.is_connected():
        try:
            await client.start(bot_token=BOT_TOKEN)
            print("Telethon client (SpyLib) started...")
        except Exception as e:
            print(f"Error starting Telethon client: {e}")
            # Decide if you want to exit or continue without this client
            # sys.exit(1)


    # For Pyrogram, app.start() and userbot.start() are best called together,
    # often managed by Pyrogram's run() if it's the main entry point.
    # If running alongside Telethon, starting them individually is fine.
    try:
        await app.start()
        print("Pyrogram client (app) started...")
    except Exception as e:
        print(f"Error starting Pyrogram client (app): {e}")
        # sys.exit(1)

    if STRING and userbot:
        if not userbot.is_connected: # Pyrogram's check is slightly different
            try:
                await userbot.start()
                print("Userbot client started...")
            except Exception as e:
                print(f"Hey honey!! Check your premium string session, it may be invalid or expire: {e}")
                # sys.exit(1) # Critical if userbot is essential
    
    # Return the clients - this function is now primarily for ensuring they are started.
    # The global instances can be imported and used by other modules.
    return client, app, userbot

# Example of how this might be called if this script itself was run
# if __name__ == "__main__":
#     async def main_shared():
#         await start_client()
#         # Keep running or do other tasks
#         if client and client.is_connected():
#             print("Telethon client is active.")
#         if app and app.is_connected:
#             print("Pyrogram client (app) is active.")
#         if userbot and userbot.is_connected:
#             print("Userbot client is active.")
#         # Add logic to keep running, e.g., await asyncio.Event().wait()
#
#     asyncio.run(main_shared())
