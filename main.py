import asyncio
from shared_client import start_client
import importlib
import os
import sys
from typing import List, NoReturn
import logging
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def load_and_run_plugins() -> List[asyncio.Task]:
    """
    Dynamically loads and runs all plugin modules from the plugins directory.
    Each plugin should have a 'run_{plugin_name}_plugin' async function.
    Returns a list of created tasks for the plugins.
    """
    running_plugin_tasks = []
    try:
        # Assuming start_client can be awaited here if it's async
        # Or it might be a synchronous call that sets up a global client
        # If it's a long-running async task, it should ideally be a plugin itself
        # or managed differently. For now, assuming it's a setup step.
        logger.info("Starting client...")
        await start_client() # Await start_client if it's an async function
        logger.info("Client started.")

        plugin_dir = "plugins"
        # Add plugin_dir to sys.path to allow direct module import
        if plugin_dir not in sys.path:
            sys.path.insert(0, plugin_dir)

        plugins: List[str] = []
        if os.path.exists(plugin_dir):
             plugins = [
                f[:-3] for f in os.listdir(plugin_dir)
                if f.endswith(".py") and f != "__init__.py" and not f.startswith("_")
             ]
        else:
            logger.warning(f"Plugins directory '{plugin_dir}' not found.")


        if not plugins:
            logger.warning("No loadable plugins found in the plugins directory!")
            return running_plugin_tasks # Return empty list if no plugins

        for plugin in plugins:
            try:
                # Use importlib.import_module with the package name
                module = importlib.import_module(f"{plugin_dir}.{plugin}")
                plugin_func_name = f"run_{plugin}_plugin"
                if hasattr(module, plugin_func_name):
                    plugin_func = getattr(module, plugin_func_name)
                    if asyncio.iscoroutinefunction(plugin_func):
                        logger.info(f"Creating task for {plugin} plugin...")
                        task = asyncio.create_task(plugin_func(), name=plugin)
                        running_plugin_tasks.append(task)
                    else:
                         logger.warning(f"Function '{plugin_func_name}' in plugin {plugin} is not an async function.")
                else:
                    logger.warning(f"Plugin {plugin} is missing required function '{plugin_func_name}'")
            except ImportError as e:
                logger.error(f"Failed to import plugin {plugin}: {e}")
            except Exception as e:
                logger.error(f"Error creating task for plugin {plugin}: {e}")

    except Exception as e:
        logger.critical(f"Failed during plugin loading or client start: {e}")
        # Depending on severity, you might want to re-raise or exit
        # For this example, we log and return what we have
        # raise # Uncomment to re-raise critical errors

    return running_plugin_tasks # Return the list of tasks

async def main() -> NoReturn:
    """
    Main application entry point that loads and runs plugins and keeps the bot alive.
    Handles graceful shutdown.
    """
    logger.info("Starting application main loop...")
    running_tasks = []
    try:
        # Load and run plugins, getting their tasks
        running_tasks = await load_and_run_plugins()

        if not running_tasks:
            logger.warning("No plugin tasks are running. Exiting main loop.")
            return # Exit if no tasks to keep alive

        logger.info(f"Started {len(running_tasks)} plugin tasks. Bot is running...")

        # Keep the main loop running indefinitely, allowing plugin tasks to execute
        # This task will be cancelled on shutdown signals
        await asyncio.Future() # An awaited Future that never completes

    except asyncio.CancelledError:
        logger.info("Main loop received cancellation signal. Starting graceful shutdown...")
        # This is where graceful shutdown logic for the main loop goes if needed
    except Exception as e:
        logger.critical(f"Unexpected error in main loop: {e}")
        # The asyncio.run() will handle the loop shutdown after this exception

async def shutdown(loop, signal=None):
    """
    Shut down the application gracefully.
    """
    if signal:
        logger.info(f"Received exit signal {signal.name}...")
    logger.info("Commencing graceful shutdown...")

    # Cancel all running tasks
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)]

    if not tasks:
        logger.info("No pending tasks to cancel.")
    else:
        logger.info(f"Cancelling {len(tasks)} pending tasks...")
        for task in tasks:
            task.cancel()

        # Wait for tasks to complete, with a timeout
        # The return_exceptions=True allows gathering even if some tasks raise exceptions
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, asyncio.CancelledError):
                logger.info(f"Task '{tasks[i].get_name()}' cancelled successfully.")
            elif isinstance(result, Exception):
                 logger.error(f"Task '{tasks[i].get_name()}' raised an exception during cancellation wait: {result}")
            # else: Task completed normally before cancellation or wait

        logger.info("All pending tasks finished or cancelled.")

    logger.info("Application shutdown complete.")
    # The loop is closed by asyncio.run()

if __name__ == "__main__":
    # Use asyncio.run() for the main entry point (Python 3.7+)
    # It handles loop creation and closing, and basic signal handling
    try:
        logger.info("Starting application...")
        asyncio.run(main())
    except KeyboardInterrupt:
         # asyncio.run() handles KeyboardInterrupt internally by cancelling tasks
         # The shutdown logic in main()'s CancelledError handler and the finalizer
         # in asyncio.run() will take care of cleanup.
         logger.info("Keyboard interrupt detected. asyncio.run() is handling shutdown.")
    except Exception as e:
        logger.critical(f"Fatal error during application startup or run: {e}")
        sys.exit(1)

# Note: With asyncio.run(), the explicit loop creation and closing in a finally block
# like in the original code is typically not needed for the main entry point,
# as asyncio.run() manages the loop's lifecycle. The shutdown function is designed
# to be called internally by asyncio.run()'s signal handling if needed, or could be
# adapted if you were managing the loop manually with run_forever.
