import bootstrap
"""Use actual AstrBot/OneBot event objects to protect message authorization."""
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'qq-runtime/astrbot'))
from aiocqhttp.event import Event
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import AiocqhttpAdapter
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.pipeline.whitelist_check.stage import WhitelistCheckStage

folder=ROOT/'plugins/astrbot_plugin_orangepi_roleplay'
pkg=types.ModuleType('whale_test');pkg.__path__=[str(folder)];sys.modules['whale_test']=pkg
spec=importlib.util.spec_from_file_location('whale_test.main',folder/'main.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)

class OpenHealth:
    def open(self,*args,**kwargs):return io.BytesIO(b'{"status":"ready","busy":false}')

class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests')
        self.main=module.Main.__new__(module.Main)
        self.main.policies={};self.main.data=Path(self.tmp.name);self.main.health_opener=OpenHealth()
        self.main.webs={}
        self.main.last_chat={}
        config=json.loads((folder/'activities.json').read_text(encoding='utf-8'))
        self.main.activities=module.Activities(config,self.main.data/'activities-state.json')
        self.adapter=AiocqhttpAdapter.__new__(AiocqhttpAdapter)
        self.adapter.metadata=PlatformMetadata(name='aiocqhttp',description='test',id='qq-local')
        self.adapter.bot=object()
    async def asyncTearDown(self):self.tmp.cleanup()
    async def event(self,post_type='message',text='今天是几号',mid=123):
        payload={'self_id':999800,'post_type':post_type,'message_type':'private','sub_type':'friend','notice_type':'notify','user_id':100000002,'sender':{'user_id':100000002,'nickname':'test'},'message_id':mid,'message':[{'type':'text','data':{'text':text}}] if text else []}
        obj=await self.adapter.convert_message(Event(payload))
        return self.adapter.create_event(obj)
    async def test_notices_never_consume_quota_or_inject_greeting(self):
        for _ in range(5):
            event=await self.event('notice',text='')
            self.assertFalse(self.main.check_guard(event))
            self.assertEqual(event.message_str,'')
        self.assertFalse(self.main.policies)
        event=await self.event()
        self.assertTrue(self.main.check_guard(event))
        self.assertEqual(event.message_str,'今天是几号')
        self.assertEqual(len(event.get_messages()),1)
    async def test_whitelist_precedes_history_isolation_and_replay_is_rejected(self):
        event=await self.event()
        self.assertTrue(self.main.check_guard(event))
        self.assertEqual(event.session_id,'100000002')
        stage=WhitelistCheckStage()
        config={'platform_settings': {'enable_id_white_list': True, 'id_whitelist': ['qq-local:FriendMessage:100000002'], 'wl_ignore_admin_on_friend': False, 'wl_ignore_admin_on_group': False, 'no_permission_reply': False, 'id_whitelist_log': False}, 'admins_id': []}
        await stage.initialize(types.SimpleNamespace(astrbot_config=config))
        await stage.process(event)
        self.assertFalse(event.is_stopped())
        await self.main.guard(event)
        self.assertEqual(event.session_id,'synthetic_999800_whale_v2_100000002')
        replay=await self.event()
        self.assertFalse(self.main.check_guard(replay))
        self.assertEqual(replay.get_extra('orangepi_policy_reason'),'duplicate')
    async def test_empty_message_is_not_a_greeting(self):
        event=await self.event(text='')
        self.assertFalse(self.main.check_guard(event))
        self.assertFalse(self.main.policies)

    async def test_keyword_stops_before_llm_even_when_model_is_offline(self):
        self.main.model_state=lambda:(_ for _ in ()).throw(AssertionError('keyword touched model'))
        event=await self.event(text=' 区 ')
        event.send=AsyncMock()
        self.assertTrue(self.main.check_guard(event))
        await self.main.guard(event)
        self.assertTrue(event.is_stopped())
        self.assertFalse(event.call_llm)
        event.send.assert_awaited_once()
        self.assertEqual(event.send.call_args.args[0].chain[0].text,'区')
        self.assertEqual(event.session_id,'100000002')

    async def test_keyword_does_not_bypass_private_authorization(self):
        event=await self.event(text='区')
        event.message_obj.sender.user_id='999'
        self.assertFalse(self.main.check_guard(event))
        self.assertEqual(event.get_extra('orangepi_policy_reason'),'private_not_allowed')

    async def test_owner_can_control_offline_without_chat_cooldown(self):
        self.main.model_state=lambda:(_ for _ in ()).throw(AssertionError('control touched model'))
        for mid,text in [(124,'关闭联网'),(125,'开启联网'),(126,'联网状态')]:
            event=await self.event(text=text,mid=mid)
            event.send=AsyncMock()
            self.assertTrue(self.main.check_guard(event))
            await self.main.guard(event)
            self.assertTrue(event.is_stopped())
            self.assertFalse(event.call_llm)
            event.send.assert_awaited_once()
        self.assertTrue(self.main.web_for('999800').state['enabled'])
        self.assertFalse(self.main.policy_for('999800').global_times)

    async def test_disabled_search_never_touches_model(self):
        self.main.web_for('999800').state['enabled']=False
        self.main.model_state=lambda:(_ for _ in ()).throw(AssertionError('disabled search touched model'))
        event=await self.event(text='搜一下 浙江大学')
        event.send=AsyncMock()
        self.assertTrue(self.main.check_guard(event))
        await self.main.guard(event)
        self.assertTrue(event.is_stopped())
        self.assertIn('联网没开',event.send.call_args.args[0].chain[0].text)

    async def test_search_quotes_evidence_without_rewriting_current_question(self):
        from astrbot.api.provider import ProviderRequest
        from astrbot.core.provider.entities import LLMResponse
        event=await self.event(text='搜一下 orchard')
        event.set_extra('orangepi_roleplay_allowed',True)
        evidence={'status':'ok','sources':[{'url':'https://example.com/article','title':'Orchard','body':'The orchard has seventeen apples.'}]}
        event.set_extra('orangepi_web_evidence',evidence)
        self.main.public='小鲸鱼';self.main.private='private role'
        self.main.context=types.SimpleNamespace(get_using_provider=lambda **_:None)
        req=ProviderRequest(prompt=event.message_str,contexts=[{'role':'user','content':'old irrelevant chat'}])
        await self.main.persona(event,req)
        self.assertEqual(req.prompt,'搜一下 orchard')
        self.assertIn('seventeen',req.contexts[0]['content'])
        self.assertNotIn('old irrelevant chat',json.dumps(req.contexts))
        self.assertIn('未受信任',req.system_prompt)
        response=LLMResponse(role='assistant',completion_text='有十七个苹果 https://fake.invalid/')
        await self.main.sources(event,response)
        self.assertIn('https://example.com/article',response.completion_text)
        self.assertNotIn('fake.invalid',response.completion_text)

    async def test_time_changes_leave_system_prefix_and_original_history_unchanged(self):
        from astrbot.api.provider import ProviderRequest
        from unittest.mock import patch
        actual_datetime=module.datetime
        stamps=iter([actual_datetime(2026,10,23,12,0),actual_datetime(2026,10,23,12,1)])
        self.main.public='固定公开人格';self.main.private='固定私聊人格'
        self.main.context=types.SimpleNamespace(get_using_provider=lambda **_:None)
        requests=[]
        history=[{'role':'user','content':'过去的问题'}]
        for text in ['最近怎么样','给我个建议']:
            event=await self.event(text=text)
            event.set_extra('orangepi_roleplay_allowed',True)
            req=ProviderRequest(prompt=text,contexts=history)
            with patch.object(module,'datetime',types.SimpleNamespace(now=lambda _:next(stamps))):
                await self.main.persona(event,req)
            self.assertEqual(req.prompt,text)
            requests.append(req)
        self.assertEqual(requests[0].system_prompt,requests[1].system_prompt)
        self.assertNotEqual(requests[0].contexts[-1],requests[1].contexts[-1])
        self.assertEqual(history,[{'role':'user','content':'过去的问题'}])

    async def test_length_cutoff_keeps_complete_prefix_and_records_reason(self):
        from astrbot.core.provider.entities import LLMResponse
        event=await self.event()
        response=LLMResponse(role='assistant',completion_text='先查资料再回答。后面还有一段没说',
            raw_completion=types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason='length')],usage=types.SimpleNamespace(completion_tokens=160)))
        await self.main.sources(event,response)
        self.assertEqual(response.completion_text,'先查资料再回答。')
        proof=json.loads((self.main.data/'reply-999800.json').read_text())
        self.assertTrue(proof['length_cutoff'])
        self.assertTrue(proof['unfinished_tail_removed'])
        self.assertFalse(proof['incomplete_marked'])

    async def test_length_cutoff_without_complete_sentence_is_marked(self):
        from astrbot.core.provider.entities import LLMResponse
        event=await self.event()
        response=LLMResponse(role='assistant',completion_text='预算3.5元，因为接下来还需',
            raw_completion={'choices':[{'finish_reason':'length'}],'usage':{'completion_tokens':160}})
        await self.main.sources(event,response)
        self.assertEqual(response.completion_text,'预算3.5元，因为接下来还需…（未完）')
        proof=json.loads((self.main.data/'reply-999800.json').read_text())
        self.assertTrue(proof['incomplete_marked'])

    async def test_normal_short_reply_needs_no_final_punctuation(self):
        from astrbot.core.provider.entities import LLMResponse
        event=await self.event()
        response=LLMResponse(role='assistant',completion_text='今天继续摸鱼',
            raw_completion={'choices':[{'finish_reason':'stop'}]})
        await self.main.sources(event,response)
        self.assertEqual(response.completion_text,'今天继续摸鱼')

    async def test_cutoff_keeps_verified_sources_and_only_one_body(self):
        from astrbot.core.provider.entities import LLMResponse
        event=await self.event()
        event.set_extra('orangepi_web_evidence',{'sources':[{'url':'https://example.com/article'}]})
        response=LLMResponse(role='assistant',completion_text='结论是十七个。还有没说完的',
            raw_completion={'choices':[{'finish_reason':'length'}]})
        await self.main.sources(event,response)
        self.assertEqual(response.completion_text,'结论是十七个。\n来源：https://example.com/article')

    async def test_image_only_uses_picture_question_and_prepared_payload(self):
        from astrbot.api.message_components import Image
        from astrbot.api.provider import ProviderRequest
        from unittest.mock import patch
        event=await self.event(text='')
        event.message_obj.message.append(Image.fromBase64('dGVzdA=='))
        self.main.model_state=lambda:{'status':'ready','busy':False,'modality':'text+image'}
        self.assertTrue(self.main.check_guard(event))
        self.assertEqual(event.message_str,'请描述这张图片。')
        with patch.object(module,'prepare_image',AsyncMock(return_value='data:image/jpeg;base64,dGVzdA==')):
            await self.main.guard(event)
        self.main.public='小鲸鱼';self.main.private='private role'
        self.main.context=types.SimpleNamespace(get_using_provider=lambda **_:None)
        req=ProviderRequest(prompt=event.message_str,contexts=[{'role':'user','content':[{'type':'text','text':'old question'},{'type':'image_url','image_url':{'url':'old'}}]}])
        await self.main.persona(event,req)
        self.assertEqual(req.image_urls,['data:image/jpeg;base64,dGVzdA=='])
        self.assertEqual(req.contexts[0]['content'],'old question')
        self.assertEqual(req.prompt,'请描述这张图片。')

    async def test_image_failure_stops_instead_of_hallucinating(self):
        from astrbot.api.message_components import Image
        event=await self.event()
        event.message_obj.message.append(Image.fromBase64('not image'))
        event.send=AsyncMock()
        self.main.model_state=lambda:{'status':'ready','busy':False,'modality':'text+image'}
        self.assertTrue(self.main.check_guard(event))
        await self.main.guard(event)
        self.assertTrue(event.is_stopped())
        self.assertFalse(event.call_llm)
        event.send.assert_awaited_once()

    async def test_sticker_attaches_to_same_result_without_an_extra_send(self):
        from astrbot.core.provider.entities import LLMResponse
        from astrbot.core.message.message_event_result import MessageChain
        from astrbot.api.message_components import Image
        event=await self.event(text='今天过得挺好')
        event.message_obj.group_id='100000003'
        event.set_extra('orangepi_roleplay_allowed',True)
        event.send=AsyncMock()
        from PIL import Image as Picture
        Picture.new('RGB',(8,8),'blue').save(self.main.data/'happy.gif')
        self.main.social_for=lambda _:types.SimpleNamespace(sticker=lambda *a,**k:self.main.data/'happy.gif')
        response=LLMResponse(role='assistant',result_chain=MessageChain().message('那不错嘛'),raw_completion={'choices':[{'finish_reason':'stop'}]})
        await self.main.sources(event,response)
        self.assertEqual(len(response.result_chain.chain),2)
        self.assertIsInstance(response.result_chain.chain[1],Image)
        event.send.assert_not_awaited()
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
        transport=types.SimpleNamespace(send_group_msg=AsyncMock())
        await AiocqhttpMessageEvent.send_message(transport,response.result_chain,event=Event({'self_id':999800}),is_group=True,session_id='100000003')
        transport.send_group_msg.assert_awaited_once()
        outgoing=transport.send_group_msg.call_args.kwargs
        self.assertEqual(outgoing['self_id'],999800)
        self.assertEqual(outgoing['group_id'],100000003)
        self.assertEqual([part['type'] for part in outgoing['message']],['text','image'])

    async def test_sampled_nonmention_wakes_once_and_keeps_normal_limits(self):
        from datetime import datetime,timezone
        class FixedRandom:
            def random(self):return 0
        clock=lambda:datetime(2026,10,23,6,tzinfo=timezone.utc).timestamp()
        social=module.Social(folder/'stickers',self.main.data/'social.json',clock=clock,rng=FixedRandom())
        self.main.social_for=lambda _:social
        event=await self.event(text='今天天气真不错啊')
        event.message_obj.group_id='100000003'
        self.assertTrue(self.main.check_guard(event))
        self.assertTrue(event.is_at_or_wake_command)
        self.assertTrue(event.get_extra('orangepi_passive'))
        second=await self.event(text='今天天气真不错啊',mid=124)
        second.message_obj.group_id='100000003'
        self.assertFalse(self.main.check_guard(second))

    async def test_disabled_vision_never_claims_to_read_an_image(self):
        from astrbot.api.message_components import Image
        from unittest.mock import patch
        event=await self.event(text='这张图是什么')
        event.message_obj.message.append(Image.fromBase64('dGVzdA=='))
        event.send=AsyncMock()
        self.main.model_state=lambda:{'status':'ready','busy':False,'modality':'text+image'}
        with patch.object(module,'VISION_ENABLED',False):
            self.assertTrue(self.main.check_guard(event))
            await self.main.guard(event)
        self.assertTrue(event.is_stopped())
        self.assertFalse(event.call_llm)
        event.send.assert_awaited_once()
        self.assertIsNone(event.get_extra('orangepi_image'))

    async def test_short_voice_replaces_reply_and_never_calls_model(self):
        event=await self.event(text='来句语音')
        event.message_obj.group_id='100000003';event.send=AsyncMock()
        from astrbot.api.message_components import At
        event.message_obj.message.insert(0,At(qq='999800'))
        controller=types.SimpleNamespace(pick=lambda *a,**k:{'path':self.main.data/'sample.wav','credit':None},receipt=lambda *a:None)
        self.main.voice_for=lambda _:controller
        self.main.model_state=lambda:(_ for _ in ()).throw(AssertionError('voice touched model'))
        self.assertTrue(self.main.check_guard(event))
        await self.main.guard(event)
        event.send.assert_awaited_once()
        self.assertEqual(event.send.call_args.args[0].chain[0].type.value,'Record')
        self.assertFalse(event.call_llm)
        self.assertTrue(event.is_stopped())

    async def test_voice_request_does_not_bypass_private_authorization(self):
        event=await self.event(text='来句语音');event.message_obj.sender.user_id='999'
        self.assertFalse(self.main.check_guard(event))
        self.assertEqual(event.get_extra('orangepi_policy_reason'),'private_not_allowed')

if __name__=='__main__':unittest.main(verbosity=2)
