from app import create_app
import os

app = create_app()

if __name__ == "__main__":
    # For debugging in PyCharm/IDE
    # Enable debug mode only when explicitly requested via FLASK_DEBUG=1
    debug_mode = os.getenv("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)

