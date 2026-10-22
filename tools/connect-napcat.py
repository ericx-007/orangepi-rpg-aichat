"""Attach the configured local AstrBot transport after interactive QQ login."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'experiments/qq-bridge'))
from napcat_api import NapCat

client = NapCat()
login = client.post('/QQLogin/CheckLoginStatus')
if not login.get('isLogin') or not login.get('coreReady'):
    raise SystemExit('Finish QQ login in the local NapCat panel first.')
settings = json.loads((ROOT / 'config/deployment.local.json').read_text(encoding='utf-8-sig'))
info = client.post('/QQLogin/GetQQLoginInfo')
if str(info.get('uin')) != str(settings['bot_qq']):
    raise SystemExit('The logged-in account differs from bot_qq.')
platform = json.loads((ROOT / 'qq-runtime/astrbot/data/cmd_config.json').read_text(encoding='utf-8-sig'))['platform'][0]
config = client.post('/OB11Config/GetConfig')
name = 'orangepi-astrbot'
for kind, entries in config['network'].items():
    if any(item.get('enable') and item.get('name') != name for item in entries):
        raise SystemExit('An unrelated OneBot connection is active; review it in NapCat before connecting.')
backup = ROOT / 'qq-runtime/state/onebot-before-connect.json'
if not backup.exists():
    backup.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
config['network']['websocketClients'] = [{'name': name, 'enable': True,
    'url': 'ws://127.0.0.1:6199/ws', 'messagePostFormat': 'array', 'reportSelfMessage': False,
    'reconnectInterval': 5000, 'token': platform['ws_reverse_token'], 'debug': False,
    'heartInterval': 30000, 'verifyCertificate': True}]
client.post('/OB11Config/SetConfig', {'config': json.dumps(config, ensure_ascii=False)})
webui_path = ROOT / 'qq-runtime/state/config/webui.json'
webui = json.loads(webui_path.read_text())
webui['autoLoginAccount'] = str(settings['bot_qq'])
webui_path.write_text(json.dumps(webui, indent=2), encoding='utf-8')
print('Local reverse WebSocket configured; cached login enabled for the configured account.')
