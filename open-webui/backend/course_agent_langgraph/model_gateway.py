from __future__ import annotations

import json
from typing import Any

from starlette.responses import Response, StreamingResponse


def _response_payload(response: Any) -> dict[str, Any]:
    if isinstance(response, StreamingResponse):
        raise RuntimeError('课程智能体内部模型调用意外返回了流式响应')
    if isinstance(response, Response):
        body = response.body.decode('utf-8') if isinstance(response.body, bytes) else str(response.body)
        return json.loads(body)
    if isinstance(response, dict):
        return response
    if hasattr(response, 'model_dump'):
        return response.model_dump()
    raise RuntimeError(f'无法识别的模型响应类型：{type(response).__name__}')


async def invoke_base_model(
    request: Any,
    user: Any,
    *,
    model_id: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.2,
) -> str:
    """Call an existing Open WebUI model without duplicating provider credentials."""
    from open_webui.utils.chat import generate_chat_completion

    response = await generate_chat_completion(
        request,
        form_data={
            'model': model_id,
            'messages': messages,
            'stream': False,
            'temperature': temperature,
        },
        user=user,
        bypass_filter=True,
        bypass_system_prompt=True,
    )
    payload = _response_payload(response)
    if payload.get('error'):
        raise RuntimeError(f'基础模型调用失败：{payload["error"]}')
    choices = payload.get('choices') or []
    if not choices:
        raise RuntimeError('基础模型没有返回候选回答')
    message = choices[0].get('message') or {}
    content = message.get('content')
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError('基础模型返回了空回答')
    return content.strip()
