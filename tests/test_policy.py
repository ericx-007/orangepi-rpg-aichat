import bootstrap
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest

folder = Path(__file__).resolve().parents[1] / 'plugins/astrbot_plugin_orangepi_roleplay'
package = types.ModuleType('policy_test')
package.__path__ = [str(folder)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location('policy_test.policy', folder / 'policy.py')
policy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = policy
spec.loader.exec_module(policy)


class PolicyTests(unittest.TestCase):
    def test_group_requires_real_mention_and_allowlist(self):
        p = policy.MessagePolicy(clock=lambda: 1000)
        self.assertEqual(p.accept(sender='123', group='111', mentioned=True, message_id='a')[1], 'group_not_allowed')
        self.assertEqual(p.accept(sender='123', group='100000003', mentioned=False, message_id='b')[1], 'explicit_at_required')
        self.assertTrue(p.accept(sender='123', group='100000003', mentioned=True, message_id='c')[0])

    def test_other_private_sender_is_denied(self):
        p = policy.MessagePolicy(clock=lambda: 1000)
        self.assertEqual(p.accept(sender='123', group='', mentioned=False, message_id='a')[1], 'private_not_allowed')
        self.assertTrue(p.accept(sender=policy.OWNER, group='', mentioned=False, message_id='b')[0])

    def test_group_and_global_cooldown(self):
        now = [1000]
        p = policy.MessagePolicy(clock=lambda: now[0])
        self.assertTrue(p.accept(sender='123', group='100000003', mentioned=True, message_id='a')[0])
        now[0] += 10
        self.assertEqual(p.accept(sender='456', group='100000004', mentioned=True, message_id='b')[1], 'global_spacing')
        now[0] += 20
        self.assertEqual(p.accept(sender='456', group='100000003', mentioned=True, message_id='c')[1], 'group_cooldown')

    def test_restart_preserves_duplicate_and_cooldown(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'state.json'
            a = policy.MessagePolicy(clock=lambda: 1000, state_path=path)
            self.assertTrue(a.accept(sender='123', group='100000003', mentioned=True, message_id='a')[0])
            b = policy.MessagePolicy(clock=lambda: 1030, state_path=path)
            self.assertEqual(b.accept(sender='456', group='100000003', mentioned=True, message_id='b')[1], 'group_cooldown')
            self.assertEqual(b.accept(sender='123', group='100000003', mentioned=True, message_id='a')[1], 'duplicate')

    def test_group_cannot_receive_private_persona(self):
        self.assertNotIn('PRIVATE_MARKER', policy.prompt_for('PUBLIC', 'PRIVATE_MARKER', sender=policy.OWNER, group='100000003'))
        self.assertNotIn('PRIVATE_MARKER', policy.prompt_for('PUBLIC', 'PRIVATE_MARKER', sender='123', group=''))
        self.assertIn('PRIVATE_MARKER', policy.prompt_for('PUBLIC', 'PRIVATE_MARKER', sender=policy.OWNER, group=''))


if __name__ == '__main__':
    unittest.main()
