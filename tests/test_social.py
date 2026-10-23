import bootstrap
"""Check social rate limits and bounded image handling without network sends."""
import base64
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'plugins/astrbot_plugin_orangepi_roleplay'
package=types.ModuleType('social_test');package.__path__=[str(FOLDER)];sys.modules['social_test']=package
for name in ['policy','social','vision']:
    spec=importlib.util.spec_from_file_location('social_test.'+name,FOLDER/(name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
from social_test.social import Social
from social_test.vision import allowed_url, normalize, prepare


class FixedRandom:
    def random(self):return 0
    def choice(self, choices):return choices[0]


class SocialTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.now=[datetime(2026,10,23,6,tzinfo=timezone.utc).timestamp()]
        self.path=Path(self.tmp.name)/'state.json'
        self.assets=Path(self.tmp.name)/'stickers';self.assets.mkdir()
        for name,color in [('happy.gif','blue'),('confused.gif','red')]:Image.new('RGB',(8,8),color).save(self.assets/name)
        self.social=Social(self.assets,self.path,clock=lambda:self.now[0],rng=FixedRandom())
    def tearDown(self):self.tmp.cleanup()
    def test_passive_cannot_expand_permissions_or_handle_commands_and_targets(self):
        for group,text,options in [('1','今天天气真不错啊',{}),('100000003','不@的普通群聊',{}),('100000003','搜一下最近新闻',{}),('100000003','有人在聊天呢',{'targeted':True}),('100000003','有人在聊天呢',{'quoted':True}),('100000003','有人在聊天呢',{'media':True})]:
            self.assertFalse(self.social.passive_candidate(group,text,**options))
        self.assertTrue(self.social.passive_candidate('100000003','今天天气真不错啊'))
    def test_limits_survive_restart_and_day_rollover(self):
        for _ in range(4):
            self.assertTrue(self.social.reserve('passive','100000003'))
            self.assertFalse(self.social.reserve('passive','100000003'))
            self.now[0]+=1201
        restored=Social(self.assets,self.path,clock=lambda:self.now[0],rng=FixedRandom())
        self.assertFalse(restored.reserve('passive','100000003'))
        self.now[0]+=86400
        self.assertTrue(restored.reserve('passive','100000003'))
    def test_stickers_are_local_sparse_and_skip_serious_messages(self):
        self.assertIsNone(self.social.sticker('100000003','我很难过'))
        first=self.social.sticker('100000003','今天运气不错')
        self.assertTrue(first.is_file())
        self.assertIsNone(self.social.sticker('100000003','又来了'))
        self.now[0]+=901
        self.assertNotEqual(first,self.social.sticker('100000003','今天运气不错'))
        self.assertEqual(json.loads(self.path.read_text())['sticker:100000003']['count'],2)
    def test_quiet_hours(self):
        self.now[0]=datetime(2026,10,23,17,tzinfo=timezone.utc).timestamp()
        self.assertFalse(self.social.reserve('passive','100000003'))
        self.assertIsNone(self.social.sticker('100000003'))
    async def test_image_resize_and_no_arbitrary_file_or_http_access(self):
        image=Image.new('RGB',(1200,800),'red');buffer=io.BytesIO();image.save(buffer,format='PNG')
        prepared=await prepare('base64://'+base64.b64encode(buffer.getvalue()).decode())
        with Image.open(io.BytesIO(base64.b64decode(prepared.split(',')[1]))) as normalized:
            self.assertLessEqual(max(normalized.size),448)
        for ref in ['file:///C:/private.txt','http://127.0.0.1/secret','https://qpic.cn.evil.example/x','https://user:pass@gchat.qpic.cn/x']:
            self.assertFalse(allowed_url(ref))
            with self.assertRaises(ValueError):await prepare(ref)
        self.assertTrue(allowed_url('https://gchat.qpic.cn/a'))
        self.assertTrue(allowed_url('https://multimedia.nt.qq.com.cn/download?appid=1407'))
        with self.assertRaises(Exception):normalize(b'not an image')

if __name__=='__main__':unittest.main(verbosity=2)
