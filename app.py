import os
from flask import Flask, render_template
from typing import Any
import logging
from werkzeug.middleware.proxy_fix import ProxyFix

# Initialize Flask application
app = Flask(__name__)

# Configure proxy settings if running behind a reverse proxy
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_prefix=1
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.route("/")
def welcome() -> Any:
    """
    Render the welcome page with animated "Team SPY" text.
    
    Returns:
        Rendered HTML template from welcome.html
    """
    try:
        logger.info("Serving welcome page request")
        return render_template("welcome.html")
    except Exception as e:
        logger.error(f"Error rendering welcome page: {e}")
        return "An error occurred while loading the page", 500

def create_app() -> Flask:
    """
    Application factory pattern for creating the Flask app.
    
    Returns:
        Flask application instance
    """
    return app

if __name__ == "__main__":
    # Get port from environment variable or default to 5000
    port = int(os.environ.get("PORT", 5000))
    
    # Configure host based on environment
    host = "0.0.0.0" if os.environ.get("DOCKER_ENV") or os.environ.get("FLASK_ENV") == "production" else "127.0.0.1"
    
    try:
        logger.info(f"Starting Flask server on {host}:{port}")
        app.run(
            host=host,
            port=port,
            debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
            threaded=True
        )
    except Exception as e:
        logger.critical(f"Failed to start Flask server: {e}")
        raise