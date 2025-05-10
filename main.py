import asyncio
from shared_client import start_client
import importlib
import os
import sys
from typing import List, NoReturn
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def load_and_run_plugins() -> None:
    """
    Dynamically loads and runs all plugin modules from the plugins directory.
    Each plugin should have a 'run_{plugin_name}_plugin' async function.
    """
    try:
        await start_client()
        plugin_dir = "plugins"
        plugins: List[str] = [
            f[:-3] for f in os.listdir(plugin_dir) 
            if f.endswith(".py") and f != "__init__.py" and not f.startswith("_")
        ]

        if not plugins:
            logger.warning("No plugins found in the plugins directory!")
            return

        for plugin in plugins:
            try:
                module = importlib.import_module(f"plugins.{plugin}")
                plugin_func = f"run_{plugin}_plugin"
                if hasattr(module, plugin_func):
                    logger.info(f"Initializing {plugin} plugin...")
                    await getattr(module, plugin_func)()
                else:
                    logger.warning(f"Plugin {plugin} is missing required function '{plugin_func}'")
            except ImportError as e:
                logger.error(f"Failed to import plugin {plugin}: {e}")
            except Exception as e:
                logger.error(f"Error running plugin {plugin}: {e}")

    except Exception as e:
        logger.critical(f"Failed to initialize plugins: {e}")
        raise

async def main() -> NoReturn:
    """
    Main application entry point that runs indefinitely.
    """
    try:
        await load_and_run_plugins()
        logger.info("All plugins loaded successfully. Bot is running...")
        while True:
            await asyncio.sleep(3600)  # Reduced frequency of sleep checks
    except asyncio.CancelledError:
        logger.info("Received shutdown signal...")
    except Exception as e:
        logger.critical(f"Unexpected error in main loop: {e}")
        raise

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        logger.info("Starting application...")
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down gracefully...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        try:
            # Cancel all running tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            
            # Wait for tasks to finish cancellation
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            
            # Close the loop
            loop.close()
        except Exception:
            pass
        logger.info("Application shutdown complete")