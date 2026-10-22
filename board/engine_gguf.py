"""Local CPU GGUF runner behind the existing bounded streaming API."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import urllib.error
import urllib.request

from model_settings import MODEL_PATH, CONTEXT_LENGTH

log=logging.getLogger(__name__)

@dataclass
class GenerationJob:
    events: queue.Queue=field(default_factory=queue.Queue)
    cancel: threading.Event=field(default_factory=threading.Event)

class ModelEngine:
    def __init__(self):
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='gguf')
        self.busy=threading.Lock()
        self.status,self.error='loading',None
        self.load_seconds,self.last_metrics,self.npu_memory=None,None,None
        self.process=None
        self.stopping=threading.Event()
        self.base='http://127.0.0.1:18080'
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _json(self,path,body=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        with self.opener.open(req,timeout=30) as response:return json.load(response)

    def start(self):
        self.executor.submit(self._load)

    def _load(self):
        started=time.perf_counter()
        try:
            binary=os.environ['GGUF_SERVER_BIN']
            threads=int(os.environ.get('GGUF_THREADS','3'))
            assert 1<=threads<=4,'CPU thread count must fit this4-core board'
            model=Path(MODEL_PATH)/os.environ['GGUF_FILENAME']
            assert model.is_file(),'GGUF weight file missing'
            args=[binary,'-m',str(model),'--host','127.0.0.1','--port','18080',
                  '--cors-origins','localhost',
                  '--alias','local','-ngl','0','-t',str(threads),'-tb',str(threads),'-c',str(CONTEXT_LENGTH),
                  '-np','1','-b','256','-ub','128','--flash-attn','off',
                  '--cache-ram','1024','--ctx-checkpoints','4','--checkpoint-min-step','256',
                  '--reasoning','off','--chat-template-kwargs','{"enable_thinking":false}',
                  '--sse-ping-interval','1','--offline','--no-context-shift','--no-webui']
            if template_name:=os.environ.get('GGUF_CHAT_TEMPLATE_FILE'):
                template=Path(template_name).resolve()
                assert template.is_relative_to(Path('/opt/orangepi-rpg-aichat/templates')) and template.is_file()
                args.extend(['--chat-template-file',str(template)])
            with open('/opt/orangepi-rpg-aichat/logs/gguf-server.log','ab',buffering=0) as output:
                self.process=subprocess.Popen(args,stdout=output,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+240
            while time.monotonic()<deadline:
                if self.process.poll() is not None:raise RuntimeError('GGUF server exited; inspect gguf-server.log')
                try:
                    if self._json('/health').get('status')=='ok':break
                except (OSError,ValueError):pass
                time.sleep(1)
            else:raise TimeoutError('GGUF server did not become ready in240s')
            self.load_seconds=round(time.perf_counter()-started,3)
            self.status='ready'
            log.info('CPU GGUF ready after %.3fs',self.load_seconds)
            threading.Thread(target=self._monitor,daemon=True,name='gguf-monitor').start()
        except Exception as exc:
            self.status,self.error='error',str(exc)
            self.shutdown()
            log.exception('GGUF initialization failed')

    def shutdown(self):
        self.stopping.set()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()

    def _monitor(self):
        code=self.process.wait()
        if not self.stopping.is_set():
            log.error('GGUF worker exited with code%s; exiting so systemd restarts the service',code)
            os._exit(1)

    def submit(self,messages,max_tokens,temperature,top_p,top_k,thinking):
        if self.status!='ready':raise RuntimeError('模型尚未就绪：'+(self.error or self.status))
        if self.process.poll() is not None:
            self.status,self.error='error','GGUF worker exited'
            raise RuntimeError(self.error)
        if not self.busy.acquire(blocking=False):raise BlockingIOError('开发板正在生成另一条回答，请稍后再试。')
        try:
            template=self._json('/apply-template',{'messages':messages,'chat_template_kwargs':{'enable_thinking':thinking}})
            tokens=self._json('/tokenize',{'content':template['prompt'],'add_special':True,'parse_special':True})['tokens']
            if len(tokens)+max_tokens>CONTEXT_LENGTH:
                raise ValueError(f'输入 {len(tokens)} tokens，加上输出预算 {max_tokens} 超过 {CONTEXT_LENGTH}。请清空历史或减少输出长度。')
            job=GenerationJob()
            self.executor.submit(self._generate,job,messages,max_tokens,temperature,top_p,top_k,thinking,len(tokens))
            return job
        except Exception:
            self.busy.release()
            raise

    def _generate(self,job,messages,maximum,temperature,top_p,top_k,thinking,prompt_tokens):
        started,first=time.perf_counter(),None
        usage,timings,finish={},{},'stop'
        body={'model':'local','messages':messages,'max_tokens':maximum,'temperature':temperature,
              'top_p':top_p,'top_k':top_k,'stream':True,'stream_options':{'include_usage':True},
              'chat_template_kwargs':{'enable_thinking':thinking},'cache_prompt':True,
              'timings_per_token':True,'sse_ping_interval':1}
        try:
            req=urllib.request.Request(self.base+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            with self.opener.open(req,timeout=600) as response:
                for line in response:
                    if job.cancel.is_set():break
                    if line.startswith(b':'):
                        job.events.put(('heartbeat',None))
                        continue
                    if not line.startswith(b'data:'):continue
                    payload=line[5:].strip()
                    if payload==b'[DONE]':break
                    data=json.loads(payload)
                    if data.get('error'):raise RuntimeError(str(data['error']))
                    if data.get('usage'):usage=data['usage']
                    if data.get('timings'):timings=data['timings']
                    for choice in data.get('choices',[]):
                        text=choice.get('delta',{}).get('content') or ''
                        if text:
                            if first is None:first=time.perf_counter()
                            job.events.put(('token',text))
                        if choice.get('finish_reason'):finish=choice['finish_reason']
            metrics={'prompt_tokens':usage.get('prompt_tokens',prompt_tokens),
                     'completion_tokens':usage.get('completion_tokens',timings.get('predicted_n',0)),
                     'total_seconds':round(time.perf_counter()-started,3),
                     'first_token_seconds':round(first-started,3) if first else None,
                     'decode_tokens_per_second':timings.get('predicted_per_second'),
                     'npu_peak_allocated_mib':None,'cancelled':job.cancel.is_set(),
                     'finish_reason':finish,'backend':'llama.cpp / ARM CPU','native_timings':timings}
            self.last_metrics=metrics
            job.events.put(('metrics',metrics))
        except Exception as exc:
            log.exception('GGUF generation failed')
            job.events.put(('error',str(exc)))
        finally:
            self.busy.release()
            job.events.put(('done',None))
