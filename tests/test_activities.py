import bootstrap
import importlib.util
import json
from datetime import datetime
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'qq-runtime/astrbot'))
folder=ROOT/'plugins/astrbot_plugin_orangepi_roleplay'
pkg=types.ModuleType('activity_test');pkg.__path__=[str(folder)];sys.modules[pkg.__name__]=pkg
spec=importlib.util.spec_from_file_location('activity_test.main',folder/'main.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)

class ActivitiesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=HERE)
        self.path=Path(self.tmp.name)/'activities.json'
        self.now=datetime(2026,10,21,12,tzinfo=module.timezone(module.timedelta(hours=8))).timestamp()
        self.config=json.loads((folder/'activities.json').read_text(encoding='utf-8')); self.config['bubbles']['enabled']=True
        self.activity=module.Activities(self.config,self.path,clock=lambda:self.now,rng=random.Random(123))

    async def asyncTearDown(self):self.tmp.cleanup()

    def make_due(self):
        for entry in self.activity.state.values():entry['next_due']=self.now

    async def test_first_send_is_delayed_and_reload_keeps_schedule(self):
        self.assertEqual(self.activity.due(),[])
        schedule={g:v['next_due'] for g,v in self.activity.state.items()}
        for value in schedule.values():self.assertTrue(5400<=value-self.now<=10800)
        reload=module.Activities(self.config,self.path,clock=lambda:self.now)
        self.assertEqual(schedule,{g:v['next_due'] for g,v in reload.state.items()})

    async def test_quiet_hours_day_cap_and_next_day(self):
        self.make_due()
        self.now=datetime(2026,10,21,23,tzinfo=module.timezone(module.timedelta(hours=8))).timestamp()
        self.assertEqual(self.activity.due(),[])
        self.now-=3600
        for entry in self.activity.state.values():entry.update(date='2026-10-21',count=3)
        self.assertEqual(self.activity.due(),[])
        self.now+=12*3600
        self.assertEqual(set(self.activity.due()),set(module.GROUPS))

    async def test_attempt_is_counted_before_send_and_survives_restart(self):
        self.make_due()
        text=self.activity.reserve('100000003')
        self.assertTrue(1<=len(text)<=2)
        self.assertEqual(self.activity.state['100000003']['status'],'pending')
        restart=module.Activities(self.config,self.path,clock=lambda:self.now)
        self.assertIsNone(restart.reserve('100000003'))
        self.assertEqual(restart.state['100000003']['count'],1)
        self.assertIsNone(restart.reserve('111'))

    async def test_keyword_is_exact_whole_text(self):
        self.assertEqual(self.activity.keyword(' 区 '),'区')
        self.assertIsNone(self.activity.keyword('社区'))
        self.assertIsNone(self.activity.keyword('区是什么意思'))
        self.assertEqual(self.activity.keyword('这么强'),'！？强强？！')

    async def test_real_timer_method_routes_only_to_actual_bot_and_allowed_group(self):
        self.make_due()
        actions=[]
        async def action(name,**kwargs):
            actions.append((name,kwargs))
            self.assertEqual(kwargs['self_id'],100000001)
            if name=='get_login_info':return {'user_id':100000001}
            if name=='get_group_list':return [{'group_id':100000003},{'group_id':111}]
            self.assertEqual(name,'send_group_msg')
            self.assertEqual(kwargs['group_id'],100000003)
            self.assertTrue(1<=len(kwargs['message'][0]['data']['text'])<=2)
            return {'message_id':123}
        main=module.Main.__new__(module.Main)
        main.activities=self.activity;main.last_chat={}
        main.voice_for=lambda _:types.SimpleNamespace(pick=lambda *a,**k:None)
        main.social_for=lambda _:types.SimpleNamespace(sticker=lambda *a,**k:None)
        main.context=types.SimpleNamespace(get_platform_inst=lambda _:types.SimpleNamespace(bot=types.SimpleNamespace(call_action=action)))
        main.policies={'100000001':module.MessagePolicy(clock=lambda:self.now)}
        main.model_state=lambda:{'status':'ready','busy':False}
        with patch.object(module.time,'time',lambda:self.now):
            await main.try_bubble()
            await main.try_bubble()
        self.assertEqual(len([a for a in actions if a[0]=='send_group_msg']),1)
        self.assertEqual(self.activity.state['100000003']['status'],'sent')
        self.assertEqual(self.activity.state['100000004']['count'],0)

    async def test_busy_and_recent_chat_defer_without_consuming_attempt(self):
        self.make_due()
        async def action(name,**kwargs):
            if name=='get_login_info':return {'user_id':100000001}
            if name=='get_group_list':return [{'group_id':int(g)} for g in module.GROUPS]
            raise AssertionError('must not send')
        main=module.Main.__new__(module.Main)
        main.activities=self.activity;main.last_chat={g:self.now for g in module.GROUPS}
        main.context=types.SimpleNamespace(get_platform_inst=lambda _:types.SimpleNamespace(bot=types.SimpleNamespace(call_action=action)))
        main.policies={'100000001':module.MessagePolicy(clock=lambda:self.now)}
        main.model_state=lambda:{'status':'ready','busy':True}
        with patch.object(module.time,'time',lambda:self.now):
            await main.try_bubble()
            main.model_state=lambda:{'status':'ready','busy':False}
            await main.try_bubble()
        self.assertTrue(all(v['count']==0 for v in self.activity.state.values()))

    async def test_voice_bubble_uses_one_record_action_and_existing_schedule(self):
        self.make_due();actions=[];receipts=[]
        async def action(name,**kwargs):
            if name=='get_login_info':return {'user_id':100000001}
            if name=='get_group_list':return [{'group_id':100000003}]
            self.assertEqual(name,'send_group_msg')
            self.assertEqual(kwargs['self_id'],100000001)
            self.assertEqual(kwargs['group_id'],100000003)
            self.assertEqual([p['type'] for p in kwargs['message']],['record'])
            self.assertEqual(self.activity.state['100000003']['status'],'pending')
            actions.append(kwargs);return {'message_id':123}
        main=module.Main.__new__(module.Main);main.activities=self.activity;main.last_chat={}
        main.context=types.SimpleNamespace(get_platform_inst=lambda _:types.SimpleNamespace(bot=types.SimpleNamespace(call_action=action)))
        main.policies={'100000001':module.MessagePolicy(clock=lambda:self.now)}
        main.model_state=lambda:{'status':'ready','busy':False}
        main.voice_for=lambda _:types.SimpleNamespace(pick=lambda *a,**k:{'path':self.path.resolve().with_suffix('.wav'),'credit':None},receipt=lambda *a:receipts.append(a))
        main.social_for=lambda _:(_ for _ in ()).throw(AssertionError('voice also reserved a sticker'))
        with patch.object(module.time,'time',lambda:self.now):
            await main.try_bubble();await main.try_bubble()
        self.assertEqual(len(actions),1)
        self.assertEqual(receipts,[('100000003','sent')])

if __name__=='__main__':unittest.main(verbosity=2)
