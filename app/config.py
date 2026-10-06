from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv('QZK_DATA_DIR', ROOT / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv('QZK_DB_PATH', DATA_DIR / 'qzk.sqlite3'))

@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv('QZK_APP_NAME', 'QZK Live Overlay')
    host: str = os.getenv('QZK_HOST', '0.0.0.0')
    port: int = int(os.getenv('PORT', os.getenv('QZK_PORT', '8000')))
    admin_password: str = os.getenv('QZK_ADMIN_PASSWORD', 'change-this-admin-password')
    token_secret: str = os.getenv('QZK_TOKEN_SECRET', 'change-this-token-secret')
    max_message: int = int(os.getenv('QZK_MAX_MESSAGE', '4000'))
    heartbeat_seconds: int = int(os.getenv('QZK_HEARTBEAT', '20'))
    cors_origins: str = os.getenv('QZK_CORS_ORIGINS', '*')

settings = Settings()
