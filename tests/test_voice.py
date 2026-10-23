import bootstrap
"""Verify voice permissions, semantic matching and restart-safe limits."""
import importlib.util,json,sys,tempfile,types,unittest
from pathlib import Path
from datetime import datetime,timezone
FOLDER=Path(__file__).resolve().parents[1]/'plugins/astrbot_plugin_orangepi_roleplay'
package=types.ModuleType('voice_test');package.__path__=[str(FOLDER)];sys.modules['voice_test']=package
for name in ['policy','voice']:
 spec=importlib.util.spec_from_file_location('voice_test.'+name,FOLDER/(name+'.py'));m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
VoicePack=m.VoicePack
class Random:
 def random(self):return 0
 def choice(self,choices):return choices[0]
class VoiceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.now=[datetime(2026,10,23,6,tzinfo=timezone.utc).timestamp()]
  (self.root/'short.wav').write_bytes(b'fixture')
  self.config={'enabled':True,'attribution':'synthetic source','clips':[{'file':'short.wav','text':'摸鱼','seconds':6,'bubble':True,'triggers':['摸鱼']}]}
  (self.root/'config.json').write_text(json.dumps(self.config),encoding='utf-8')
  self.path=self.root/'state.json';self.controller=VoicePack(self.root,self.path,clock=lambda:self.now[0],rng=Random())
 def tearDown(self):self.tmp.cleanup()
 def test_no_voice_for_unrelated_questions_private_unknown_group_or_quiet_hours(self):
  for group,text in [('100000003','今天几号'),('','来句语音'),('111','摸鱼')]:self.assertIsNone(self.controller.pick(group,text))
  self.now[0]=datetime(2026,10,23,17,tzinfo=timezone.utc).timestamp()
  self.assertIsNone(self.controller.pick('100000003','来句语音'))
 def test_reserved_attempt_survives_restart_and_counts_failed_sends(self):
  result=self.controller.pick('100000003','摸鱼');self.assertTrue(result['credit'])
  self.controller.credited('100000003');self.controller.receipt('100000003','uncertain')
  restored=VoicePack(self.root,self.path,clock=lambda:self.now[0],rng=Random())
  self.assertIsNone(restored.pick('100000003','来句语音'))
  self.now[0]+=1801
  self.assertIsNone(restored.pick('100000003','来句语音')['credit'])
 def test_shared_daily_cap_for_bubbles_and_replies(self):
  self.assertIsNotNone(self.controller.pick('100000003',bubble=True))
  for _ in range(2):
   self.now[0]+=1801;self.assertIsNotNone(self.controller.pick('100000003','来句语音'))
  self.now[0]+=1801;self.assertIsNone(self.controller.pick('100000003','来句语音'))
  self.now[0]+=86400;self.assertIsNotNone(self.controller.pick('100000003','来句语音'))
 def test_missing_long_and_escaping_paths_do_not_reserve(self):
  for filename,seconds in [('missing.wav',6),('short.wav',20),('../outside.wav',5)]:
   self.controller.config['clips'][0].update(file=filename,seconds=seconds)
   self.assertIsNone(self.controller.pick('100000003','来句语音'))
  self.assertFalse(self.path.exists())
 def test_disabled_public_switch_prevents_even_explicit_requests(self):
  from unittest.mock import patch
  with patch.object(sys.modules[VoicePack.__module__],'VOICE_ENABLED',False):
   self.assertIsNone(self.controller.pick('100000003','来句语音'))
  self.assertFalse(self.path.exists())
if __name__=='__main__':unittest.main(verbosity=2)
