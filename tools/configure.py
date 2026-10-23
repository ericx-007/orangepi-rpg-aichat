"""Configure a stopped, initialized AstrBot checkout in this repository."""
import argparse
import copy
import json
from pathlib import Path
import runpy
import secrets
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]


def build_config(existing, deployment, access, hash_password):
    """Preserve upstream defaults and replace the managed chat configuration."""
    config = copy.deepcopy(existing)
    owner = str(deployment['owner_qq'])
    bot = str(deployment['bot_qq'])
    groups = [str(value) for value in deployment['allowed_groups']]
    if not bot.isdigit() or not owner.isdigit() or any(not group.isdigit() for group in groups):
        raise ValueError('Fill numeric bot_qq, owner_qq and allowed_groups first')
    platform = deployment.get('platform_id', 'qq-local')
    if platform != 'qq-local':
        raise ValueError('The bundled Windows setup uses platform_id=qq-local')
    if not 1 <= int(deployment['max_tokens']) <= 1024:
        raise ValueError('max_tokens must be in 1..1024')
    config['dashboard'].update(host='127.0.0.1', port=6185, username=access['username'], password='',
        pbkdf2_password=hash_password(access['password']), password_storage_upgraded=True,
        password_change_required=False, jwt_secret=access['jwt_secret'])
    config['platform'] = [{'id': platform, 'type': 'aiocqhttp', 'enable': True,
        'ws_reverse_host': '127.0.0.1', 'ws_reverse_port': 6199, 'ws_reverse_token': access['onebot_token']}]
    config['platform_settings'].update(enable_id_white_list=True,
        id_whitelist=[f'{platform}:FriendMessage:{owner}', *groups],
        wl_ignore_admin_on_group=False, wl_ignore_admin_on_friend=False,
        no_permission_reply=False, ignore_bot_self_message=True, ignore_at_all=True, id_whitelist_log=False)
    config['platform_settings']['rate_limit'].update(time=60, count=3, strategy='discard')
    config['platform_settings']['segmented_reply']['enable'] = False
    config['provider_sources'] = [{'id': 'orangepi', 'provider': 'openai', 'type': 'openai_chat_completion',
        'provider_type': 'chat_completion', 'enable': True, 'key': ['local-placeholder'],
        'api_base': deployment['api_base'], 'timeout': int(deployment['request_timeout']), 'proxy': '', 'custom_headers': {}}]
    config['provider'] = [{'id': 'orangepi/local', 'provider_source_id': 'orangepi', 'model': 'local',
        'enable': True, 'modalities': ['text', 'image'] if deployment.get('enable_vision', False) is True else ['text'], 'max_context_tokens': 4096,
        'custom_extra_body': {'max_tokens': int(deployment['max_tokens']), 'temperature': 0.6, 'top_p': 0.8,
                              'chat_template_kwargs': {'enable_thinking': False}}}]
    config['provider_settings'].update(enable=True, provider_pool=['orangepi/local'], streaming_response=False,
        web_search=False, datetime_system_prompt=False, display_reasoning_text=False, computer_use_runtime='none')
    config['provider_settings']['proactive_capability']['add_cron_tools'] = False
    runner = config['agent_runner']['config']
    runner['model'].update(provider_id='orangepi/local', fallback_provider_ids=[], request_max_retries=0)
    runner['compression'].update(max_turns=2, trim_turns=1, overflow_strategy='truncate_by_turns', fallback_max_tokens=4096)
    runner['misc'].update(max_steps=1, sanitize_context_by_modalities=True)
    config.update(plugin_set=['orangepi_roleplay'], disable_builtin_commands=True, wake_prefix=[],
                  log_level='INFO', trace_enable=False, trace_log_enable=False, t2i=False)
    config['provider_ltm_settings'].update(group_icl_enable=False, group_message_history_enable=False)
    config['provider_ltm_settings']['active_reply']['enable'] = False
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/deployment.local.json')
    args = parser.parse_args()
    deployment = json.loads(args.config.read_text(encoding='utf-8-sig'))
    base = ROOT / 'qq-runtime'
    source = base / 'astrbot'
    target = source / 'data/cmd_config.json'
    if not target.is_file():
        raise SystemExit('Start AstrBot once to initialize data/cmd_config.json, stop it, then run this tool.')
    import psutil
    for process in psutil.process_iter(['cmdline', 'cwd']):
        try:
            if process.info['cwd'] and Path(process.info['cwd']).resolve() == source.resolve() and 'main.py' in (process.info['cmdline'] or []):
                raise SystemExit('Stop this checkout of AstrBot before changing its configuration.')
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    state = base / 'state'
    state.mkdir(parents=True, exist_ok=True)
    path = state / 'astrbot-access.json'
    access = json.loads(path.read_text()) if path.exists() else {
        'username': 'astrbot', 'password': 'A1a' + secrets.token_urlsafe(24),
        'onebot_token': secrets.token_urlsafe(32), 'jwt_secret': secrets.token_urlsafe(48)}
    auth = runpy.run_path(str(source / 'astrbot/core/utils/auth_password.py'))
    config = build_config(json.loads(target.read_text(encoding='utf-8-sig')), deployment,
                          access, auth['hash_dashboard_password'])
    backup = state / ('before-setup-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir()
    shutil.copy2(target, backup / 'cmd_config.json')
    plugin = source / 'data/plugins/astrbot_plugin_orangepi_roleplay'
    if plugin.exists():
        shutil.copytree(plugin, backup / plugin.name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / 'plugins/astrbot_plugin_orangepi_roleplay', plugin, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'settings.local.json'))
    settings = {key: deployment[key] for key in ['bot_qq', 'owner_qq', 'allowed_groups', 'platform_id', 'health_url']}
    settings.update({key: deployment.get(key, False) is True for key in ['enable_vision', 'enable_passive', 'enable_stickers']})
    (plugin / 'settings.local.json').write_text(json.dumps(settings, indent=2), encoding='utf-8')
    activities = json.loads((plugin / 'activities.json').read_text(encoding='utf-8'))
    activities['bubbles']['enabled'] = bool(deployment.get('enable_bubbles', False))
    (plugin / 'activities.json').write_text(json.dumps(activities, ensure_ascii=False, indent=2), encoding='utf-8')
    path.write_text(json.dumps(access, indent=2), encoding='utf-8')
    pending = target.with_suffix('.upload')
    pending.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8-sig')
    pending.replace(target)
    print('Configured. Local credentials: qq-runtime/state/astrbot-access.json. Do not publish that file.')


if __name__ == '__main__':
    main()
