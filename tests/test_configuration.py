import bootstrap
import copy
import importlib.util
from pathlib import Path
import unittest

from astrbot.core.config.default import DEFAULT_CONFIG

spec = importlib.util.spec_from_file_location('configure_public', Path(__file__).resolve().parents[1] / 'tools/configure.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.deployment = {'bot_qq': '100000001', 'owner_qq': '100000002',
            'allowed_groups': ['100000003', '100000004'], 'max_tokens': 160,
            'api_base': 'http://127.0.0.1:8000/v1', 'request_timeout': 600}
        self.access = {'username': 'test', 'password': 'synthetic-test-password',
            'onebot_token': 'synthetic-test-token', 'jwt_secret': 'synthetic-test-secret'}

    def build(self):
        return module.build_config(DEFAULT_CONFIG, self.deployment, self.access, lambda _: 'synthetic-hash')

    def test_original_defaults_untouched_and_managed_plugin_enabled(self):
        before = copy.deepcopy(DEFAULT_CONFIG)
        config = self.build()
        self.assertEqual(DEFAULT_CONFIG, before)
        self.assertEqual(config['plugin_set'], ['orangepi_roleplay'])
        self.assertFalse(config['platform_settings']['segmented_reply']['enable'])

    def test_whitelist_and_loopback_transport_match_plugin(self):
        config = self.build()
        self.assertEqual(config['platform_settings']['id_whitelist'],
            ['qq-local:FriendMessage:100000002', '100000003', '100000004'])
        self.assertEqual(config['platform'][0]['ws_reverse_host'], '127.0.0.1')
        self.assertFalse(config['platform_settings']['wl_ignore_admin_on_group'])
        self.assertEqual(config['dashboard']['password'], '')

    def test_local_provider_has_complete_reply_headroom_and_timeout(self):
        config = self.build()
        self.assertEqual(config['provider'][0]['custom_extra_body']['max_tokens'], 160)
        self.assertEqual(config['provider_sources'][0]['timeout'], 600)
        self.assertFalse(config['provider_settings']['streaming_response'])
        self.assertEqual(config['agent_runner']['config']['compression']['max_turns'], 2)

    def test_missing_identity_cannot_generate_active_config(self):
        self.deployment['owner_qq'] = ''
        with self.assertRaises(ValueError):
            self.build()


if __name__ == '__main__':
    unittest.main()
