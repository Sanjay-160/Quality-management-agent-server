import time
import threading
import logging
from sqlalchemy import create_engine, text
from .config import get_config, sqlalchemy_url

logger = logging.getLogger("qcore.db")

_cached_engine = None
_cached_url = None
_keep_alive_started = False
_lock = threading.Lock()

def engine():
    global _cached_engine, _cached_url
    url = sqlalchemy_url(get_config().get("database_url", ""))
    if not url:
        raise RuntimeError("DATABASE_URL is not configured. Add the Neon connection string to backend/.env and restart the API.")
    
    with _lock:
        if _cached_engine is not None and _cached_url == url:
            return _cached_engine
        
        _cached_url = url
        _cached_engine = create_engine(
            url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,      # Actively verifies connection health before checkout
            pool_recycle=300,        # Recycles sockets every 5 minutes to prevent stale disconnections
            pool_timeout=30,
            connect_args={"sslmode": "require", "connect_timeout": 15}
        )
        return _cached_engine

def execute_with_retry(fn, max_retries=3, delay=1.0):
    """Executes a database function with automatic retry for serverless compute wakeup."""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_err = exc
            logger.warning(f"Database operation attempt {attempt}/{max_retries} failed: {exc}. Retrying...")
            if attempt < max_retries:
                time.sleep(delay * attempt)
    raise last_err

def test_connection():
    def _test():
        with engine().connect() as conn:
            return conn.execute(text("SELECT version(), current_database()")).fetchone()
    return execute_with_retry(_test, max_retries=3, delay=1.5)

def _keep_alive_loop():
    """Runs a lightweight periodic query to keep the Neon serverless compute node active and warm."""
    logger.info("Neon keep-alive monitor started.")
    while True:
        try:
            time.sleep(120)  # Ping every 2 minutes (well before Neon's 5-minute auto-suspend window)
            eng = engine()
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.debug("Neon keep-alive ping successful.")
        except Exception as exc:
            logger.debug(f"Neon keep-alive ping retry: {exc}")

def start_keep_alive():
    global _keep_alive_started
    with _lock:
        if not _keep_alive_started:
            _keep_alive_started = True
            t = threading.Thread(target=_keep_alive_loop, daemon=True, name="neon-keep-alive")
            t.start()
