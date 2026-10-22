import asyncio
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
import queue
import time
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
import psutil

from model_settings import MODEL_ID, MODEL_LABEL, MODEL_PRECISION, CONTEXT_LENGTH, THINKING_SUPPORTED, MODEL_BACKEND, BACKEND_LABEL
from engine_gguf import ModelEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')

engine = ModelEngine()
DEFAULT_SYSTEM = (
    f'你是运行在用户香橙派 Orange Pi AIpro 20T 开发板上的 {MODEL_LABEL} 本地助手。'
    '本服务在本机进行模型推理，不调用云端模型。你没有联网、读取文件或执行命令的工具。'
    '请用中文简明回答；不确定的事实请如实说明。'
)


@asynccontextmanager
async def lifespan(app):
    engine.start()
    try:
        yield
    finally:
        if hasattr(engine, 'shutdown'):
            engine.shutdown()


app = FastAPI(title='Orange Pi 本地模型', lifespan=lifespan)


class Message(BaseModel):
    role: Literal['system', 'user', 'assistant']
    content: str = Field(min_length=1, max_length=16000)

    @field_validator('content', mode='before')
    @classmethod
    def normalize_text_parts(cls, value):
        if isinstance(value, list):
            if any(not isinstance(part, dict) or part.get('type') != 'text'
                   or not isinstance(part.get('text'), str) for part in value):
                raise ValueError('仅支持文字内容分段，不支持图片、音频或其他内容类型。')
            return ''.join(part['text'] for part in value)
        return value


class TemplateOptions(BaseModel):
    enable_thinking: bool = False


class ChatRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[Message] = Field(min_length=1, max_length=64)
    max_tokens: int = Field(default=256, ge=1, le=1024)
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.8, gt=0, le=1)
    top_k: int = Field(default=20, ge=1, le=100)
    stream: bool = True
    chat_template_kwargs: TemplateOptions = Field(default_factory=TemplateOptions)


@app.get('/')
def home():
    return FileResponse(Path(__file__).with_name('index.html'))


@app.get('/health')
def health():
    memory = psutil.virtual_memory()
    return {'status': engine.status, 'error': engine.error, 'model': MODEL_ID,
            'model_label': MODEL_LABEL, 'precision': MODEL_PRECISION, 'modality': 'text', 'thinking_supported': THINKING_SUPPORTED,
            'backend': BACKEND_LABEL, 'context_length': CONTEXT_LENGTH,
            'busy': engine.busy.locked(), 'load_seconds': engine.load_seconds,
            'npu_memory_after_loading': engine.npu_memory,
            'available_memory_gib': round(memory.available/1024**3, 2),
            'last_metrics': engine.last_metrics}


@app.get('/ready')
def ready():
    if engine.status != 'ready':
        raise HTTPException(status_code=503, detail=engine.error or '模型正在加载')
    return {'ready': True}


@app.get('/v1/models')
def models():
    return {'object': 'list', 'data': [{'id': MODEL_ID, 'object': 'model', 'owned_by': 'local'},
                                     {'id': 'local', 'object': 'model', 'owned_by': 'local'}]}


@app.post('/v1/chat/completions')
async def chat(body: ChatRequest):
    if body.model not in (MODEL_ID, 'local'):
        raise HTTPException(status_code=404, detail=f'当前模型名为 {MODEL_ID}；可用 local 跟随当前模型。')
    if body.chat_template_kwargs.enable_thinking and not THINKING_SUPPORTED:
        raise HTTPException(status_code=400, detail='当前模型没有可切换的思考模式。')
    if sum(len(message.content) for message in body.messages) > 48000:
        raise HTTPException(status_code=413, detail='对话内容过长，请清空历史后重试。')
    try:
        messages = [item.model_dump() for item in body.messages]
        if not any(item['role'] == 'system' for item in messages):
            messages.insert(0, {'role': 'system', 'content': DEFAULT_SYSTEM})
        job = engine.submit(messages, body.max_tokens,
                            body.temperature, body.top_p, body.top_k,
                            body.chat_template_kwargs.enable_thinking)
    except BlockingIOError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    response_id = 'chatcmpl-' + uuid.uuid4().hex
    created = int(time.time())

    def chunk(delta, finish=None):
        return {'id': response_id, 'object': 'chat.completion.chunk', 'created': created,
                'model': MODEL_ID, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}

    def sse():
        try:
            yield 'data: ' + json.dumps(chunk({'role': 'assistant'})) + '\n\n'
            while True:
                try:
                    kind, value = job.events.get(timeout=15)
                except queue.Empty:
                    yield ': keepalive\n\n'
                    continue
                if kind == 'token':
                    yield 'data: ' + json.dumps(chunk({'content': value}), ensure_ascii=False) + '\n\n'
                elif kind == 'heartbeat':
                    yield ': keepalive\n\n'
                elif kind == 'metrics':
                    data = chunk({}, value['finish_reason'])
                    data['timings'] = value
                    data['usage'] = {key: value[key] for key in ('prompt_tokens', 'completion_tokens')}
                    data['usage']['total_tokens'] = value['prompt_tokens'] + value['completion_tokens']
                    yield 'data: ' + json.dumps(data) + '\n\n'
                elif kind == 'error':
                    yield 'data: ' + json.dumps({'error': {'message': value}}, ensure_ascii=False) + '\n\n'
                elif kind == 'done':
                    yield 'data: [DONE]\n\n'
                    break
        finally:
            job.cancel.set()

    if body.stream:
        return StreamingResponse(sse(), media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    def collect():
        text, metrics, error = [], {}, None
        while True:
            kind, value = job.events.get()
            if kind == 'token': text.append(value)
            elif kind == 'metrics': metrics = value
            elif kind == 'error': error = value
            elif kind == 'done': break
        return ''.join(text), metrics, error

    try:
        text, metrics, error = await asyncio.to_thread(collect)
    except asyncio.CancelledError:
        job.cancel.set()
        raise
    if error:
        raise HTTPException(status_code=500, detail=error)
    return {'id': response_id, 'object': 'chat.completion', 'created': created, 'model': MODEL_ID,
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text},
                         'finish_reason': metrics.get('finish_reason', 'stop')}],
            'usage': {'prompt_tokens': metrics['prompt_tokens'],
                      'completion_tokens': metrics['completion_tokens'],
                      'total_tokens': metrics['prompt_tokens']+metrics['completion_tokens']},
            'timings': metrics}
