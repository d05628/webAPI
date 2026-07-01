# -*- coding: utf-8 -*-
"""
main.py
=======
全老师的测试页 —— FastAPI 版

本文件演示两件事：
1）FastAPI 里"render"（模板渲染）的用法：
   Jinja2Templates().TemplateResponse() 等价于 Flask 里的 render_template()。
2）转接 G4F（免费/兼容 OpenAI 协议的对话服务），并留一条"自定义 API"
   备用通道，防止免费 provider 失效导致测试跑不通。

运行方式：
    pip install -r requirements.txt
    uvicorn main:app --reload
然后浏览器打开 http://127.0.0.1:8000
"""

import time
import random
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import httpx

# ------------------------------------------------------------------
# g4f 是第三方库，导入失败也不影响 render 部分的教学演示，
# 所以这里用 try/except 包一下，出错只是把 G4F 相关功能禁用掉。
# ------------------------------------------------------------------
try:
    import g4f
    G4F_AVAILABLE = True
except Exception as e:  # noqa: BLE001
    G4F_AVAILABLE = False
    G4F_IMPORT_ERROR = str(e)


app = FastAPI(title="全老师的测试页 —— FastAPI render + G4F 演示")

# ------------------------------------------------------------------
# ① render 的核心：Jinja2Templates
# ------------------------------------------------------------------
# FastAPI 官方推荐用法：
#   templates = Jinja2Templates(directory="templates")
#   return templates.TemplateResponse("xxx.html", {"request": request, ...})
#
# 注意：FastAPI（基于 Starlette）要求模板上下文里必须带上 "request" 这个键，
# 这是和 Flask render_template() 最大的用法差异，Flask 不需要手动传 request。
# ------------------------------------------------------------------
templates = Jinja2Templates(directory="templates")

# 静态文件（CSS/JS），如果你不需要可以删掉这一行
app.mount("/static", StaticFiles(directory="static"), name="static")


# ------------------------------------------------------------------
# 一个极简的"全局设置"，用来演示 provider / 自定义 API 的切换开关。
# 生产环境请换成数据库或环境变量，这里图教学简单，直接用内存字典。
# ------------------------------------------------------------------
SETTINGS: Dict[str, Any] = {
    # g4f 相关
    "g4f_provider": "",          # 留空 = 让 g4f 自动挑选可用 provider
    "g4f_model": "gpt-4o-mini",  # 默认模型，可在页面上改

    # 自定义 OpenAI 兼容 API（推荐，稳定性更好）
    "use_custom_api": False,
    "custom_api_base": "https://api.openai.com/v1",
    "custom_api_key": "",
    "custom_api_model": "gpt-4o-mini",
}


# ====================================================================
# 第一部分：render 教学演示
# ====================================================================

@app.get("/")
async def index(request: Request):
    """
    首页：完整的 render 教学示例。

    演示点：
    - 传变量（now、rand_num）
    - 传列表（feature_list），模板里用 {% for %} 循环渲染
    - 传布尔值（g4f_available），模板里用 {% if %} 条件渲染
    - 每次刷新页面，now / rand_num 都会变化，说明这是"服务器端渲染"，
      不是写死在 HTML 里的静态内容。
    """
    context = {
        "request": request,  # FastAPI 的 Jinja2Templates 必须带上这个 key
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rand_num": random.randint(1, 100),
        "feature_list": [
            "① render 演示：服务器端模板渲染",
            "② Provider / 模型设置：可视化切换 g4f 或自定义 API",
            "③ 计算器小工具：前端 fetch() 异步调用后端接口",
            "④ AI 对话测试区：流式 / 非流式 + 通道检测",
        ],
        "g4f_available": G4F_AVAILABLE,
        "settings": SETTINGS,
    }
    # 等价于 Flask 的：return render_template("index.html", **context)
    return templates.TemplateResponse("index.html", context)


@app.get("/render_demo")
async def render_demo(
    request: Request,
    name: str = Query(default="同学", description="你的名字"),
    mood: str = Query(default="开心", description="你现在的心情"),
):
    """
    一个更"纯粹"的 render 小例子：
    直接改浏览器地址栏的 URL 参数，就能看到页面内容跟着变化。

    试试访问：
      /render_demo?name=小明&mood=兴奋
      /render_demo?name=全老师&mood=淡定
    """
    context = {
        "request": request,
        "name": name,
        "mood": mood,
        "now": datetime.now().strftime("%H:%M:%S"),
        "tip": "把网址里 name= 和 mood= 后面的内容改一改，回车看看效果！",
    }
    return templates.TemplateResponse("render_demo.html", context)


# ====================================================================
# 第二部分：计算器小工具（对比 render 和 fetch 两种数据展示方式）
# ====================================================================

class CalcRequest(BaseModel):
    a: float
    b: float
    op: str  # + - * /


@app.post("/api/calc")
async def calc(payload: CalcRequest):
    """
    前端用 fetch() 异步调用这个接口，不刷新整个页面就能拿到计算结果。
    这是和"render 整页刷新"相对的另一种常见前后端交互方式。
    """
    a, b, op = payload.a, payload.b, payload.op
    try:
        if op == "+":
            result = a + b
        elif op == "-":
            result = a - b
        elif op == "*":
            result = a * b
        elif op == "/":
            if b == 0:
                return JSONResponse({"ok": False, "error": "除数不能为 0"}, status_code=400)
            result = a / b
        else:
            return JSONResponse({"ok": False, "error": f"不支持的运算符：{op}"}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    return {"ok": True, "result": result}


# ====================================================================
# 第三部分：Provider / 模型设置
# ====================================================================

class SettingsPayload(BaseModel):
    g4f_provider: Optional[str] = ""
    g4f_model: Optional[str] = "gpt-4o-mini"
    use_custom_api: Optional[bool] = False
    custom_api_base: Optional[str] = "https://api.openai.com/v1"
    custom_api_key: Optional[str] = ""
    custom_api_model: Optional[str] = "gpt-4o-mini"


@app.get("/api/settings")
async def get_settings():
    """返回当前设置（出于安全考虑，API Key 只回显掩码）"""
    safe = dict(SETTINGS)
    if safe.get("custom_api_key"):
        key = safe["custom_api_key"]
        safe["custom_api_key_masked"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
    else:
        safe["custom_api_key_masked"] = ""
    safe.pop("custom_api_key", None)
    return safe


@app.post("/api/settings")
async def update_settings(payload: SettingsPayload):
    """保存 provider / 模型 / 自定义 API 设置"""
    data = payload.model_dump()
    # 如果前端没填新 key（比如只改了模型名），保留原来的 key，不要清空
    if not data.get("custom_api_key"):
        data.pop("custom_api_key")
    SETTINGS.update(data)
    return {"ok": True, "settings": {**SETTINGS, "custom_api_key": "***已保存***" if SETTINGS["custom_api_key"] else ""}}


# ====================================================================
# 第四部分：AI 对话测试区（G4F + 自定义 OpenAI 兼容 API）
# ====================================================================

class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]  # [{"role": "user", "content": "..."}]
    stream: bool = False


async def call_g4f(messages: List[Dict[str, str]], stream: bool):
    """
    调用 g4f。

    g4f 依赖免费/非官方通道，本身不保证一直可用。
    这里做了两点优化：
    1. provider 默认留空，让 g4f 自动挑选当前可用的通道；
    2. 第一次失败自动重试一次（换个思路而不是直接报错）。
    """
    if not G4F_AVAILABLE:
        raise RuntimeError(f"g4f 未正确安装：{G4F_IMPORT_ERROR}")

    provider_name = SETTINGS.get("g4f_provider") or None
    model = SETTINGS.get("g4f_model") or "gpt-4o-mini"

    provider = None
    if provider_name:
        provider = getattr(g4f.Provider, provider_name, None)

    kwargs = dict(model=model, messages=messages, stream=stream)
    if provider is not None:
        kwargs["provider"] = provider

    last_err = None
    for attempt in range(2):  # 最多重试一次
        try:
            response = g4f.ChatCompletion.create(**kwargs)
            return response
        except Exception as e:  # noqa: BLE001
            last_err = e
            await asyncio.sleep(0.5)
    raise RuntimeError(f"g4f 调用失败（已重试）：{last_err}")


async def call_custom_api(messages: List[Dict[str, str]], stream: bool):
    """
    调用自定义 OpenAI 兼容 API。
    只要是遵循 OpenAI /chat/completions 协议的服务都可以填进来，
    比如 OpenAI 官方、DeepSeek、Kimi（Moonshot）、通义千问兼容模式等。
    """
    base = SETTINGS["custom_api_base"].rstrip("/")
    key = SETTINGS["custom_api_key"]
    model = SETTINGS["custom_api_model"]

    if not key:
        raise RuntimeError("未配置自定义 API Key，请先在「Provider / 模型设置」里填写")

    url = f"{base}/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"model": model, "messages": messages, "stream": stream}

    if not stream:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    else:
        # 流式：返回一个异步生成器，逐块 yield 文本内容
        async def gen():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", url, headers=headers, json=body) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[len("data:"):].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:  # noqa: BLE001
                            continue
        return gen()


@app.post("/api/chat")
async def chat(payload: ChatRequest):
    """
    统一对话入口：
    - SETTINGS["use_custom_api"] = True  → 走自定义 OpenAI 兼容 API
    - SETTINGS["use_custom_api"] = False → 走 g4f
    """
    messages = payload.messages
    stream = payload.stream

    try:
        if SETTINGS.get("use_custom_api"):
            result = await call_custom_api(messages, stream)
        else:
            result = await call_g4f(messages, stream)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    if not stream:
        # 非流式：一次性把完整回答返回
        text = result if isinstance(result, str) else "".join([c for c in result])
        return {"ok": True, "reply": text}

    # 流式：用 StreamingResponse 逐块吐字，前端配合 ReadableStream 读取
    async def event_stream():
        try:
            if hasattr(result, "__aiter__"):
                async for chunk in result:
                    yield chunk
            else:
                # g4f 的 stream=True 一般返回同步生成器
                for chunk in result:
                    yield chunk
        except Exception as e:  # noqa: BLE001
            yield f"\n\n[出错了：{e}]"

    return StreamingResponse(event_stream(), media_type="text/plain; charset=utf-8")


@app.get("/api/check_channel")
async def check_channel():
    """
    "通道检测"按钮背后的接口：
    发一条最简短的测试消息，看当前配置的对话通道能不能正常返回内容。
    """
    test_messages = [{"role": "user", "content": "请只回复两个字：正常"}]
    start = time.time()
    try:
        if SETTINGS.get("use_custom_api"):
            reply = await call_custom_api(test_messages, stream=False)
            channel = "自定义 OpenAI 兼容 API"
        else:
            reply = await call_g4f(test_messages, stream=False)
            reply = reply if isinstance(reply, str) else "".join([c for c in reply])
            channel = "G4F"
        elapsed = round(time.time() - start, 2)
        return {"ok": True, "channel": channel, "reply": reply, "elapsed_sec": elapsed}
    except Exception as e:  # noqa: BLE001
        elapsed = round(time.time() - start, 2)
        return JSONResponse(
            {"ok": False, "channel": "自定义 OpenAI 兼容 API" if SETTINGS.get("use_custom_api") else "G4F",
             "error": str(e), "elapsed_sec": elapsed},
            status_code=500,
        )
