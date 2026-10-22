import bootstrap  # Isolated synthetic identities and optional AstrBot source.
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
folder=ROOT/'plugins/astrbot_plugin_orangepi_roleplay'
pkg=types.ModuleType('web_test');pkg.__path__=[str(folder)];sys.modules[pkg.__name__]=pkg
spec=importlib.util.spec_from_file_location('web_test.web_search',folder/'web_search.py')
web=importlib.util.module_from_spec(spec);sys.modules[spec.name]=web;spec.loader.exec_module(web)

class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=HERE)
        self.path=Path(self.tmp.name)/'web-state.json'
        self.service=web.WebSearch(self.path,clock=lambda:1792584000)

    async def asyncTearDown(self):self.tmp.cleanup()

    def command(self,text,**kwargs):
        defaults={'sender':'100000002','group':'','private':True,'message_id':'1'}
        defaults.update(kwargs)
        return self.service.control(text,**defaults)

    async def test_only_actual_owner_private_can_mutate(self):
        for kwargs in [{'sender':'999'},{'group':'100000003'},{'private':False},{'sender':'100000002','group':'100000004','private':False}]:
            self.command('关闭联网',**kwargs)
            self.assertTrue(self.service.state['enabled'])
        self.assertIn('已关闭',self.command('关闭联网'))
        reloaded=web.WebSearch(self.path)
        self.assertFalse(reloaded.state['enabled'])

    async def test_replay_is_silent_and_status_does_not_enable(self):
        self.command('关闭联网')
        self.assertIsNone(self.command('开启联网'))
        self.assertIn('关闭',self.command('联网状态',message_id='2'))
        self.assertFalse(self.service.state['enabled'])
        self.command('开启联网',message_id='3')
        self.assertTrue(self.service.state['enabled'])

    async def test_commands_and_query_prefixes_are_exact(self):
        self.assertIsNone(self.command('请开启联网'))
        for text,expected in [('搜一下 浙江大学','浙江大学'),('查一下：今天的新闻','今天的新闻'),('搜索Python','Python'),('搜一下','')]:
            self.assertEqual(web.query_from(text),expected)
        self.assertIsNone(web.query_from('你知道怎么搜索吗'))

    async def test_disabled_invalid_busy_and_daily_limit_never_fetch(self):
        async def no_fetch(*args,**kwargs):raise AssertionError('Unexpected network')
        self.service.read_url=no_fetch
        self.command('关闭联网')
        self.assertEqual((await self.service.retrieve('anything'))['status'],'disabled')
        self.command('开启联网',message_id='2')
        self.assertEqual((await self.service.retrieve(''))['status'],'invalid_query')
        async with self.service.lock:
            self.assertEqual((await self.service.retrieve('anything'))['status'],'busy')
        self.service.state.update(date='2026-10-21',count=30)
        self.assertEqual((await self.service.retrieve('anything'))['status'],'daily_limit')

    async def test_full_bodies_not_search_snippets_form_evidence(self):
        async def read(session,url,limit=500000):
            if 'bing.com/search' in url:
                return b'<rss><channel><item><title>Official fact</title><link>https://example.com/article</link><description>UNTRUSTED SNIPPET WRONG FACT</description></item></channel></rss>','text/xml',url
            html='<html><body><nav>MENU</nav><article><p>The verified orchard contains exactly seventeen golden apples, harvested on the twenty-first day.</p></article><script>BAD SCRIPT</script></body></html>'
            return html.encode(),'text/html',url
        self.service.read_url=read
        result=await self.service.retrieve('orchard')
        self.assertEqual(result['status'],'ok')
        self.assertIn('seventeen',result['sources'][0]['body'])
        self.assertNotIn('SNIPPET',json.dumps(result))
        self.assertNotIn('BAD SCRIPT',json.dumps(result))
        self.assertEqual(web.WebSearch(self.path).state['count'],1)

    async def test_no_pages_timeout_and_private_targets_fail_honestly(self):
        async def timeout(*args,**kwargs):raise asyncio.TimeoutError()
        self.service.read_url=timeout
        self.assertEqual((await self.service.retrieve('orchard'))['status'],'unavailable')
        async def empty(*args,**kwargs):return b'<rss><channel></channel></rss>','text/xml','https://www.bing.com/'
        self.service.read_url=empty
        self.assertEqual((await self.service.retrieve('orchard'))['status'],'no_results')
        for url in ['http://127.0.0.1:6185/','http://192.168.1.1/','http://localhost/','file:///secret','https://user:password@example.com','http://foo.internal/']:
            self.assertFalse(web.public_url(url),url)
        resolver=web.PublicResolver()
        with patch.object(web.aiohttp.resolver.ThreadedResolver,'resolve',return_value=[{'host':'127.0.0.1'}]):
            with self.assertRaises(OSError):await resolver.resolve('rebind.example.com')

if __name__=='__main__':unittest.main(verbosity=2)
