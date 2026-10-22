"""Load deployment identities without embedding accounts in source."""
import json
import os
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
path = Path(os.environ.get('ORANGEPI_ROLEPLAY_CONFIG', FOLDER / 'settings.local.json'))
config = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
BOT_ID = str(config.get('bot_qq', ''))
OWNER = str(config.get('owner_qq', ''))
GROUPS = frozenset(str(group) for group in config.get('allowed_groups', []))
PLATFORM_ID = str(config.get('platform_id', 'qq-local'))
HEALTH_URL = str(config.get('health_url', 'http://127.0.0.1:8000/health'))
if BOT_ID and (not BOT_ID.isdigit() or not OWNER.isdigit()):
    raise ValueError('bot_qq and owner_qq must be numeric QQ IDs')
if any(not group.isdigit() for group in GROUPS):
    raise ValueError('allowed_groups must contain numeric QQ IDs')
