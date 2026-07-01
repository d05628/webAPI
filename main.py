"""
======================================================================
 全老师的测试页 —— FastAPI + Jinja2 render 教学 & G4F 对话接口
======================================================================
这个文件是整个项目的入口，包含两个教学重点：

1.【render 的用法】
   Web 开发里说的"render"（渲染），指服务器把 Python 里的数据（变量、
   列表、字典……）"套"进一个 HTML 模板文件里，生成一份最终呈现给浏览器的
   完整网页。
     - 在 Flask 里，这个动作叫 render_template()
     - 在 FastAPI 里，由 Jinja2Templates().TemplateResponse() 完成，
       用法几乎一样，只是名字不同。
   本文件的 "/" 路由就是完整的 render 示例，模板文件在 templates/index.html，
   里面有详细中文注释讲解 {{ }}、{% if %}、{% for %} 等语法。

2.【G4F 对话接口的修复与优化】
   原代码把 provider 写死成 "You"，g4f 依赖的都是免费/非官方通道，随时
   可能被限流、下线，一旦硬编码的 provider 失效，整个对话功能就直接报错、
   "跑不通"。这里做了三点优化：
     a) provider 默认留空，让 g4f 自动挑选当前可用的免费 provider，
        并且失败时自动换下一个（参考 g4f 官方 RetryProvider 思路）；
     b) 加了超时保护（asyncio.wait_for），避免请求卡死；
     c) 增加"自定义 OpenAI 兼容 API"备用通道 —— 如果你有任何 OpenAI 兼容
        的 API Key（OpenAI 官方 / DeepSeek / Kimi / 通义千问兼容模式等），
        填进设置页后，AI 对话测试区就能稳定使用，不用再赌免费 provider
        今天能不能用。
======================================================================
"""

import asyncio
import json
import os
import random
import time
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from g4f.client import AsyncClient

app = FastAPI(title="全老师的测试页")

# ----------------------------------------------------------------------------
# 【render 用法讲解】：Jinja2Templates 就是 FastAPI 里做"渲染"的工具类。
# directory="templates" 告诉 FastAPI 去哪个文件夹找模板文件。
# 之后调用 templates.TemplateResponse(模板文件名, {"request": request, ...数据})
# FastAPI 会读取模板文件，把第二个参数里的数据替换进模板的 {{ }} 占位符，
# 生成完整 HTML 字符串返回给浏览器 —— 这整个过程就叫"渲染 (render)"。
# ----------------------------------------------------------------------------
templates = Jinja2Templates(directory="templates")

# 挂载 static 文件夹，存放独立的 CSS / JS（前端逻辑和后端 render 分开，方便对比教学）
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

client = AsyncClient()

SETTINGS_FILE = "settings.json"

DEFAULT_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-3.5-turbo",
    "gemini-1.5-flash",
    "claude-3-haiku",
    "llama-3.1-70b",
]

DEFAULT_SETTINGS = {
    "provider": "",  # 留空 = 让 g4f 自动挑选当前可用的免费 provider，更稳定
    "models": DEFAULT_MODELS,
    "use_custom_api": False,
    "custom_base_url": "",
    "custom_api_key": "",
    "custom_model": "",
}


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**DEFAULT_SETTINGS, **data}
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(data):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


settings = load_settings()


# =============================================================================
# 首页：render 的核心演示
# =============================================================================
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """
    本项目"render 用法"的主入口。

    看这一行 ↓↓↓
    templates.TemplateResponse("index.html", {"request": request, ...})
    这行代码会读取 templates/index.html，把下面 context 字典里的数据
    替换进模板的占位符里，生成最终 HTML 返回给浏览器。
    """
    context = {
        "request": request,
        "title": "全老师的测试页",
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "random_number": random.randint(1, 100),
        "settings": settings,
        "models": settings["models"],
    }
    return templates.TemplateResponse("index.html", context)


# =============================================================================
# render 的另一个演示：传统"表单提交 -> 服务器渲染新页面"的小例子
# 和首页里用 JS fetch 做异步交互的方式对比，帮助理解两种模式的区别
# =============================================================================
@app.get("/render_demo", response_class=HTMLResponse)
async def render_demo(request: Request, name: str = "同学", mood: str = "开心"):
    context = {
        "request": request,
        "name": name,
        "mood": mood,
        "now": datetime.now().strftime("%H:%M:%S"),
    }
    return templates.TemplateResponse("render_demo.html", context)


# =============================================================================
# 最简单的"前端 JS 调后端 API"演示：计算器（和 render 相反，不刷新页面）
# =============================================================================
@app.get("/api/add")
async def api_add(a: float, b: float):
    return {"a": a, "b": b, "result": a + b}


# =============================================================================
# provider / model 设置接口（沿用并扩展了原来的逻辑）
# =============================================================================
class SettingsRequest(BaseModel):
    provider: str = ""
    models: List[str]
    use_custom_api: bool = False
    custom_base_url: Optional[str] = ""
    custom_api_key: Optional[str] = ""
    custom_model: Optional[str] = ""


@app.get("/settings")
async def get_settings():
    safe = dict(settings)
    if safe.get("custom_api_key"):
        safe["custom_api_key"] = "*" * 6 + safe["custom_api_key"][-4:]
    return safe


@app.post("/settings")
async def set_settings(payload: SettingsRequest):
    data = payload.dict()
    # 如果前端没填新的 key（比如只是想改模型列表），就保留旧的 key，避免被清空
    if not data.get("custom_api_key"):
        data["custom_api_key"] = settings.get("custom_api_key", "")
    settings.update(data)
    save_settings(settings)
    return {"message": "设置已保存", "settings": settings}


@app.get("/v1/models")
async def list_models():
    created_time = int(time.time())
    return {
        "object": "list",
        "data": [
            {"id": m, "object": "model", "created": created_time, "owned_by": "g4f-or-custom"}
            for m in settings["models"]
        ],
    }


# =============================================================================
# G4F 兜底重试逻辑：原代码把 provider 写死成 "You"，一旦这个免费通道失效，
# 请求就直接报错。这里做自动兜底：先试用户指定的 provider，不行的话
# 再让 g4f 自动挑选可用的 provider（参考官方 RetryProvider 思路）。
# =============================================================================
async def g4f_chat_with_fallback(model, messages):
    provider = settings.get("provider") or None
    attempts = [provider, None] if provider else [None]
    last_error = None
    for p in attempts:
        try:
            kwargs = {"provider": p} if p else {}
            return await asyncio.wait_for(
                client.chat.completions.create(model=model, messages=messages, **kwargs),
                timeout=45,
            )
        except Exception as e:
            last_error = e
            continue
    raise last_error or RuntimeError("g4f 没有可用的 provider")


async def g4f_stream_with_fallback(model, messages):
    provider = settings.get("provider") or None
    attempts = [provider, None] if provider else [None]
    last_error = None
    for p in attempts:
        try:
            kwargs = {"provider": p} if p else {}
            async for chunk in client.chat.completions.stream(model=model, messages=messages, **kwargs):
                yield chunk
            return
        except Exception as e:
            last_error = e
            continue
    raise last_error or RuntimeError("g4f 没有可用的 provider")


async def call_custom_api(model, messages, stream):
    """走用户自己配置的、真正稳定的 OpenAI 兼容 API（作为 g4f 的备用/替代通道）"""
    base_url = settings.get("custom_base_url", "").rstrip("/")
    api_key = settings.get("custom_api_key", "")
    if not base_url or not api_key:
        raise HTTPException(status_code=400, detail="请先在设置里填写自定义 API 的 base_url 和 api_key")
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "stream": stream}

    if stream:
        async def gen():
            async with httpx.AsyncClient(timeout=60) as hc:
                async with hc.stream("POST", url, headers=headers, json=payload) as r:
                    async for line in r.aiter_lines():
                        if line:
                            yield line + "\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient(timeout=60) as hc:
            r = await hc.post(url, headers=headers, json=payload)
            return JSONResponse(content=r.json(), status_code=r.status_code)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model = body.get("model") or (settings["models"][0] if settings["models"] else "gpt-3.5-turbo")
    messages = body.get("messages")
    stream = body.get("stream", False)

    if not messages:
        raise HTTPException(status_code=400, detail="'messages' 字段是必须的")

    # 优先用自定义 OpenAI 兼容 API（如果配置了），保证 AI 对话测试一定能跑通
    if settings.get("use_custom_api") and settings.get("custom_api_key"):
        real_model = settings.get("custom_model") or model
        return await call_custom_api(real_model, messages, stream)

    # 否则走 g4f 免费通道（带自动兜底重试）
    if stream:
        async def stream_generator():
            try:
                async for chunk in g4f_stream_with_fallback(model, messages):
                    yield f"data: {chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                error_response = {"error": {"message": f"g4f 请求失败：{e}", "type": "g4f_error"}}
                yield f"data: {json.dumps(error_response, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        try:
            response = await g4f_chat_with_fallback(model, messages)
            return response.model_dump()
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"g4f 所有 provider 都失败了：{e}。建议在设置里换个模型，或者配置自定义 API 作为备用通道。",
            )


@app.get("/api/status")
async def api_status():
    """给测试页用的探测接口：快速检查当前 g4f / 自定义 API 通道是否可用"""
    test_messages = [{"role": "user", "content": "ping"}]
    model = settings["models"][0] if settings["models"] else "gpt-3.5-turbo"
    try:
        if settings.get("use_custom_api") and settings.get("custom_api_key"):
            base_url = settings.get("custom_base_url", "").rstrip("/")
            headers = {"Authorization": f"Bearer {settings['custom_api_key']}"}
            async with httpx.AsyncClient(timeout=15) as hc:
                r = await hc.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json={"model": settings.get("custom_model") or model, "messages": test_messages},
                )
            return {"ok": r.status_code == 200, "channel": "custom_api", "detail": r.status_code}
        else:
            await asyncio.wait_for(g4f_chat_with_fallback(model, test_messages), timeout=20)
            return {"ok": True, "channel": "g4f"}
    except Exception as e:
        return {
            "ok": False,
            "channel": "custom_api" if settings.get("use_custom_api") else "g4f",
            "detail": str(e),
        }
