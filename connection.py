import MetaTrader5 as mt5
import os
import logging
from contextlib import contextmanager
import threading
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Global variables for connection tracking
_mt5_connection_count = 0
_mt5_lock = threading.Lock()
_mt5_initialized = False
_mt5_connection_timeout = 300  # 5 minutes in seconds
_last_activity_time = 0


@contextmanager
def mt5_connection():
    """Context manager for establishing and closing MT5 connection with reference counting."""
    global _mt5_connection_count, _mt5_initialized, _mt5_lock, _last_activity_time

    # Thread-safe increment of connection count
    with _mt5_lock:
        # Initialize MT5 connection if not already initialized
        if not _mt5_initialized:
            # Load credentials from environment variables
            MT5_ACCOUNT = int(os.getenv("MT5_ACCOUNT", 0))
            MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
            MT5_SERVER = os.getenv("MT5_SERVER", "")
            MT5_PATH = os.getenv("MT5_PATH", None)  # Optional, use None if not set

            if not all([MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER]):
                logging.error(
                    "Missing MT5 credentials in environment variables (MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER)")
                raise ConnectionError("Missing MT5 credentials")

            # Initialize MT5
            kwargs = {
                "login": MT5_ACCOUNT,
                "password": MT5_PASSWORD,
                "server": MT5_SERVER,
            }
            if MT5_PATH:
                kwargs["path"] = MT5_PATH

            _mt5_initialized = mt5.initialize(**kwargs)

            if not _mt5_initialized:
                error_code = mt5.last_error()
                logging.error(f"MT5 initialize() failed, error code = {error_code}")
                raise ConnectionError(f"Failed to connect to MT5: {error_code}")

            # Optional: Check login state
            if not mt5.login(MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER):
                error_code = mt5.last_error()
                logging.error(f"MT5 login failed for account {MT5_ACCOUNT}, error code = {error_code}")
                mt5.shutdown()
                _mt5_initialized = False
                raise ConnectionError(f"Failed to login to MT5 account {MT5_ACCOUNT}: {error_code}")

            logging.info(f"MT5 Connection successful for account {MT5_ACCOUNT} on server {MT5_SERVER}")

        # Update connection count and timestamp
        _mt5_connection_count += 1
        import time
        _last_activity_time = time.time()
        logging.debug(f"MT5 connection acquired, active connections: {_mt5_connection_count}")

    try:
        yield  # Yield control back to the caller
    except Exception as e:
        logging.error(f"Error during MT5 operation: {e}")
        # Force reconnection next time if we get a terminal error
        if "Socket operation failed" in str(e) or "Connection error" in str(e):
            with _mt5_lock:
                if _mt5_initialized:
                    logging.warning("Connection failure detected, forcing reconnection on next use")
                    mt5.shutdown()
                    _mt5_initialized = False
        raise
    finally:
        with _mt5_lock:
            _mt5_connection_count -= 1
            import time
            _last_activity_time = time.time()

            if _mt5_connection_count <= 0:
                _mt5_connection_count = 0  # Safety check
                if _mt5_initialized:
                    logging.info("Shutting down MT5 connection - last user")
                    mt5.shutdown()
                    _mt5_initialized = False
            else:
                logging.debug(f"MT5 connection released, {_mt5_connection_count} still active")


# Function to start a connection timeout checker thread
def start_connection_checker():
    """Start a background thread to check for idle connections"""

    def check_idle_connections():
        global _mt5_connection_count, _mt5_initialized, _mt5_lock, _last_activity_time, _mt5_connection_timeout

        import time
        while True:
            time.sleep(60)  # Check every minute

            with _mt5_lock:
                # If connection is initialized but inactive for too long, close it
                if _mt5_initialized and _mt5_connection_count == 0:
                    current_time = time.time()
                    if current_time - _last_activity_time > _mt5_connection_timeout:
                        logging.info(f"Closing idle MT5 connection after {_mt5_connection_timeout} seconds")
                        mt5.shutdown()
                        _mt5_initialized = False

    checker_thread = threading.Thread(target=check_idle_connections, daemon=True)
    checker_thread.start()
    logging.info("MT5 connection checker thread started")