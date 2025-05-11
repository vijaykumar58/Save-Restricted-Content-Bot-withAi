# Copyright (c) 2025 devgagan : https://github.com/devgaganin.  
# Licensed under the GNU General Public License v3.0.  
# See LICENSE file in the repository root for full license text.

import asyncio
from shared_client import start_client
import importlib
import os
import sys

async def load_and_run_plugins():
    await start_client()
    plugin_dir = "plugins"
    plugins = [f[:-3] for f in os.listdir(plugin_dir) if f.endswith(".py") and f != "__init__.py"]

    for plugin in plugins:
        try:
            module = importlib.import_module(f"plugins.{plugin}")
            if hasattr(module, f"run_{plugin}_plugin"): # Optional: convention for a plugin-specific run function
                print(f"Running {plugin} plugin initialization (if any specific run function exists)...")
                await getattr(module, f"run_{plugin}_plugin")()
            elif hasattr(module, "register"): # A common pattern for plugins to have a register function
                print(f"Registering {plugin} plugin...")
                await module.register()
            else:
                print(f"Imported {plugin} plugin. No specific run or register function found.")
        except Exception as e:
            print(f"Error loading or running plugin {plugin}: {e}")

async def main():
    await load_and_run_plugins()
    print("All plugins loaded. Bot is running...")
    # Keep the main task alive, or implement specific logic for the bot to idle or handle tasks.
    # For many bots, the clients (Telethon/Pyrogram) will keep the event loop running.
    # If there's no other indefinitely running task, you might need one here.
    # For example, if your clients are started and then expected to run forever:
    try:
        while True:
            await asyncio.sleep(3600) # Sleep for a long time, or handle a shutdown signal
    except asyncio.CancelledError:
        print("Main task cancelled, shutting down...")


if __name__ == "__main__":
    print("Starting clients ...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down...")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)
    finally:
        print("Application closed.")
