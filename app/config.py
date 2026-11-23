from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

# Permanent fallback to ensure the application is ALWAYS connected to the Neon database
DEFAULT_DATABASE_URL = "postgresql://neondb_owner:npg_0VrFXEB2pCNQ@ep-snowy-sea-aoujn0yz-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
DEFAULT_DOMO_TOKEN = "DDCI1a3420affddc32ae4a2173c96b63bf3af8dd71f8105a83d1"
DEFAULT_FRONTEND_URL = "http://localhost:5173"

def get_cors_origins() -> list[str]:
    load_dotenv(BASE_DIR / ".env", override=True)
    raw = (
        os.getenv("CORS_ORIGINS")
        or os.getenv("CORS_ORIGIN")
        or os.getenv("FRONTEND_URL")
        or DEFAULT_FRONTEND_URL
    ).strip()

    # Support single URL or comma-separated list
    raw_list = [item.strip() for item in raw.split(",") if item.strip()]

    origins = []
    for origin in raw_list:
        clean = origin.rstrip("/")
        if clean and clean not in origins:
            origins.append(clean)
            # If a localhost URL is given, also allow 127.0.0.1 on the same port for seamless local dev
            if "localhost" in clean:
                alt = clean.replace("localhost", "127.0.0.1")
                if alt not in origins:
                    origins.append(alt)

    return origins if origins else [DEFAULT_FRONTEND_URL]

def get_config():
    load_dotenv(BASE_DIR / ".env", override=True)
    return {
        "database_url": (os.getenv("DATABASE_URL") or "").strip() or DEFAULT_DATABASE_URL,
        "domo_subdomain": (os.getenv("DOMO_SUBDOMAIN") or "gwcteq-partner").strip(),
        "domo_model": (os.getenv("DOMO_MODEL") or "domo.domo_ai.domogpt-small-v2.1:anthropic").strip(),
        "domo_token": (os.getenv("DOMO_TOKEN") or "").strip() or DEFAULT_DOMO_TOKEN,
        "cors_origins": get_cors_origins(),
    }

def sqlalchemy_url(url):
    if not url: return ""
    url = url.strip()
    if url.startswith("postgres://"): url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"): url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url
