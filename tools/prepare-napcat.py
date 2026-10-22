"""Create a loopback-only NapCat panel with a random local token."""
import json
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]
config = ROOT / 'qq-runtime/state/config'
config.mkdir(parents=True, exist_ok=True)
path = config / 'webui.json'
data = json.loads(path.read_text()) if path.exists() else {}
data.update(host='127.0.0.1', port=6099, disableWebUI=False)
data.setdefault('autoLoginAccount', '')
data.setdefault('token', secrets.token_urlsafe(32))
if not data['token'] or data['token'] == 'napcat':
    data['token'] = secrets.token_urlsafe(32)
path.write_text(json.dumps(data, indent=2), encoding='utf-8')
print('NapCat local panel configured. Read its token locally from qq-runtime/state/config/webui.json.')
