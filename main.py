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
#
# 注意（重要 bug 修复）：
#   旧版代码用 getattr(g4f.Provider, provider_name) 取 Provider 类，
#   但在新版 g4f（7.x）里 g4f.Provider.XXX 顶层拿到的其实是"子模块"
#   而不是真正的 Provider 类，传给 ChatCompletion.create() 会静默失败
#   或直接报错 —— 这是之前"G4F 调用无法正常使用"的根本原因之一。
#   正确姿势是从 g4f.Provider.ProviderUtils.convert 这个字典里按名字取真正的类。
#   同时改用官方现在推荐的 g4f.client.Client（OpenAI 风格客户端），
#   而不是旧版、行为不太稳定的 g4f.ChatCompletion.create()。
#   参考：https://g4f.dev/docs/
# ------------------------------------------------------------------
try:
    import g4f
    from g4f.client import Client as G4FClient
    from g4f.Provider import ProviderUtils
    G4F_AVAILABLE = True
    G4F_IMPORT_ERROR = ""
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
    # provider 留空 = 让 g4f 自动挑选可用 provider（内部会做 fallback / 重试）
    # model 也建议留空 = 用该 provider 自己的 default_model，
    # 强行指定一个该 provider 不支持的模型名是 g4f 报错的常见原因之一。
    "g4f_provider": "",
    "g4f_model": "",

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
    g4f_model: Optional[str] = ""
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


# --------------------------------------------------------------
# G4F Provider / 模型的"实时"发现逻辑
# --------------------------------------------------------------
# g4f 内置了 100 多个 Provider（对接不同的免费/第三方对话服务），
# 但同一时刻能用的、需要 API Key 的、支不支持流式，都会变。
# ProviderUtils.convert 是 {Provider名字: Provider类} 的字典，
# 每个类上都带着 working / needs_auth / supports_stream / default_model
# 等"实时状态位"（g4f 仓库会持续更新这些标记）。
# --------------------------------------------------------------

def _resolve_provider_cls(provider_name: str):
    """按名字从 g4f 里找到真正的 Provider 类（不是子模块！）"""
    if not provider_name:
        return None
    cls = ProviderUtils.convert.get(provider_name)
    if cls is None:
        raise RuntimeError(f"未知的 Provider 名字：{provider_name}（点击「刷新 Provider 列表」看看当前可用的名字）")
    return cls


def _list_working_providers() -> List[Dict[str, Any]]:
    """列出 g4f 当前标记为 working=True 的 Provider（同步函数，放线程池里跑）"""
    result = []
    for name, cls in ProviderUtils.convert.items():
        if not getattr(cls, "working", False):
            continue
        result.append({
            "name": name,
            "label": getattr(cls, "label", None) or name,
            "needs_auth": bool(getattr(cls, "needs_auth", False)),
            "supports_stream": bool(getattr(cls, "supports_stream", True)),
            "default_model": getattr(cls, "default_model", "") or "",
        })
    # 免费、不需要 Key 的排前面，最省心
    result.sort(key=lambda p: (p["needs_auth"], p["label"]))
    return result


def _list_models_for_provider(provider_name: str) -> List[str]:
    """
    获取某个 Provider 当前"实时"支持的模型列表（同步函数，放线程池里跑）。
    优先调用 Provider.get_models()（很多 Provider 会向官方接口实时拉取模型表），
    拿不到就退回该 Provider 自带的静态 models 列表 / default_model。
    """
    cls = _resolve_provider_cls(provider_name)
    if cls is None:
        return []

    models: List[str] = []
    try:
        live = cls.get_models()
        if live:
            models = [str(m) for m in live]
    except Exception:
        pass  # 部分 Provider 的 get_models() 需要联网/鉴权，拿不到就算了

    if not models:
        static_models = getattr(cls, "models", None) or []
        models = [str(m) for m in static_models]

    default_model = getattr(cls, "default_model", "") or ""
    if default_model and default_model not in models:
        models.insert(0, default_model)

    # 去重保序，并限制数量避免前端下拉框太长
    seen, uniq = set(), []
    for m in models:
        if m and m not in seen:
            uniq.append(m)
            seen.add(m)
    return uniq[:80]


def _sync_g4f_create(messages: List[Dict[str, str]], provider_name: str, model: str, stream: bool):
    """
    真正发起 g4f 请求（同步函数，塞进线程池跑，避免堵住 FastAPI 的事件循环）。
    用官方推荐的 g4f.client.Client，风格和 OpenAI SDK 一致：
        client.chat.completions.create(messages=..., model=..., provider=...)
    """
    client = G4FClient()
    kwargs: Dict[str, Any] = {"messages": messages, "stream": stream}
    if model:
        kwargs["model"] = model
    provider_cls = _resolve_provider_cls(provider_name)
    if provider_cls is not None:
        kwargs["provider"] = provider_cls
    return client.chat.completions.create(**kwargs)


async def _bridge_sync_stream(sync_gen):
    """
    把 g4f 返回的"同步生成器"桥接成异步生成器：
    开一个后台线程消费同步生成器，把每个 chunk 塞进 asyncio.Queue，
    这样才不会在 await 的时候卡住整个事件循环（这也是流式输出的关键点）。
    """
    import threading

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    SENTINEL = object()

    def worker():
        try:
            for chunk in sync_gen:
                # g4f.client 的流式 chunk 是 ChatCompletionChunk 对象，
                # 真正的文字在 chunk.choices[0].delta.content 里；
                # 也兼容极少数 Provider 直接吐字符串的情况。
                text = ""
                try:
                    text = chunk.choices[0].delta.content or ""
                except Exception:  # noqa: BLE001
                    text = chunk if isinstance(chunk, str) else ""
                if text:
                    loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception as e:  # noqa: BLE001
            loop.call_soon_threadsafe(queue.put_nowait, ("__error__", str(e)))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, SENTINEL)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        item = await queue.get()
        if item is SENTINEL:
            break
        if isinstance(item, tuple) and item and item[0] == "__error__":
            raise RuntimeError(item[1])
        yield item


async def call_g4f(messages: List[Dict[str, str]], stream: bool):
    """
    调用 g4f。

    g4f 依赖免费/非官方通道，本身不保证一直可用。这里做了几点优化：
    1. Provider 从 ProviderUtils.convert 按名字取真正的类（修复了旧版取到
       "子模块"而不是"类"的 bug，这是之前调用失败的主要原因）；
    2. provider / model 都可以留空，交给 g4f.client.Client 自动选择；
    3. 用官方现在推荐的 g4f.client.Client，而不是旧版 ChatCompletion.create；
    4. 第一次失败自动重试一次；
    5. 同步调用统一丢进线程池执行，不阻塞 FastAPI 的事件循环。
    """
    if not G4F_AVAILABLE:
        raise RuntimeError(f"g4f 未正确安装：{G4F_IMPORT_ERROR}")

    provider_name = SETTINGS.get("g4f_provider") or ""
    model = SETTINGS.get("g4f_model") or ""

    last_err = None
    for attempt in range(2):  # 最多重试一次
        try:
            response = await asyncio.to_thread(
                _sync_g4f_create, messages, provider_name, model, stream
            )
            if stream:
                return _bridge_sync_stream(response)
            # 非流式：g4f.client 返回的是 ChatCompletion 对象
            return response.choices[0].message.content
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


# --------------------------------------------------------------
# 实时 Provider / 模型发现接口 —— 对应页面上的下拉框
# --------------------------------------------------------------

@app.get("/api/g4f/providers")
async def g4f_providers():
    """
    实时列出 g4f 当前标记为可用（working=True）的 Provider。
    「需要 Key」的 Provider 也会列出来（比如你自己有 OpenAI/Anthropic 官方 Key
    也可以配置在 g4f 里），但默认排在后面，优先展示免费、免登录的通道。
    """
    if not G4F_AVAILABLE:
        return JSONResponse({"ok": False, "error": f"g4f 未正确安装：{G4F_IMPORT_ERROR}"}, status_code=500)
    try:
        providers = await asyncio.to_thread(_list_working_providers)
        return {"ok": True, "count": len(providers), "providers": providers}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/g4f/models")
async def g4f_models(provider: str = Query(default="", description="Provider 名字，留空则返回空列表")):
    """
    实时获取某个 Provider 当前支持的模型列表。
    优先调用该 Provider 的 get_models()（很多 Provider 会实时向源站拉取模型表），
    拿不到再退回该 Provider 自带的静态模型清单 / 默认模型。
    """
    if not G4F_AVAILABLE:
        return JSONResponse({"ok": False, "error": f"g4f 未正确安装：{G4F_IMPORT_ERROR}"}, status_code=500)
    if not provider:
        return {"ok": True, "provider": "", "models": []}
    try:
        # 有些 Provider 的 get_models() 内部请求没设超时，这里在外层兜底一个超时，
        # 避免某个 Provider 抽风时把整个请求卡死。
        models = await asyncio.wait_for(
            asyncio.to_thread(_list_models_for_provider, provider), timeout=12
        )
        return {"ok": True, "provider": provider, "models": models}
    except asyncio.TimeoutError:
        return JSONResponse({"ok": False, "error": "获取模型列表超时，该 Provider 可能暂不可用"}, status_code=504)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


class TestProviderPayload(BaseModel):
    provider: str = ""
    model: str = ""


@app.post("/api/g4f/test_provider")
async def g4f_test_provider(payload: TestProviderPayload):
    """
    单独测试"某一个" Provider + 模型组合是否当前能用，不依赖已保存的全局设置。
    用于页面上「测试这个 Provider」按钮 —— 选完就能马上验证，不用先保存。
    """
    if not G4F_AVAILABLE:
        return JSONResponse({"ok": False, "error": f"g4f 未正确安装：{G4F_IMPORT_ERROR}"}, status_code=500)

    test_messages = [{"role": "user", "content": "请只回复两个字：正常"}]
    start = time.time()
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(_sync_g4f_create, test_messages, payload.provider, payload.model, False),
            timeout=25,
        )
        reply = response.choices[0].message.content
        elapsed = round(time.time() - start, 2)
        return {"ok": True, "provider": payload.provider or "(自动)", "model": payload.model or "(默认)",
                "reply": reply, "elapsed_sec": elapsed}
    except Exception as e:  # noqa: BLE001
        elapsed = round(time.time() - start, 2)
        return JSONResponse(
            {"ok": False, "provider": payload.provider or "(自动)", "model": payload.model or "(默认)",
             "error": str(e), "elapsed_sec": elapsed},
            status_code=500,
        )


@app.get("/api/g4f/auto_pick")
async def g4f_auto_pick():
    """
    "自动选择可用 Provider"：依次尝试几个免费、免登录、口碑较好的 Provider，
    每个给 15 秒超时，第一个测试成功的会被直接写入 SETTINGS 并返回。
    这样就不用一个个手动试了 —— 对应页面上的「⚡ 自动选择可用 Provider」按钮。
    """
    if not G4F_AVAILABLE:
        return JSONResponse({"ok": False, "error": f"g4f 未正确安装：{G4F_IMPORT_ERROR}"}, status_code=500)

    try:
        candidates = await asyncio.to_thread(_list_working_providers)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    # 免 Key 的排前面；过滤掉明显是图片/音频/搜索类的 Provider（名字里带这些关键词的
    # 大概率不支持普通文字对话），最多试 12 个，避免整体检测耗时太久
    NON_CHAT_HINTS = ("Image", "Flux", "Audio", "TTS", "Search", "Video", "Vision", "Dalle")
    no_auth = [
        p for p in candidates
        if not p["needs_auth"] and not any(h in p["name"] for h in NON_CHAT_HINTS)
    ][:12]
    test_messages = [{"role": "user", "content": "请只回复两个字：正常"}]

    tried = []
    for p in no_auth:
        start = time.time()
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(_sync_g4f_create, test_messages, p["name"], "", False),
                timeout=15,
            )
            reply = response.choices[0].message.content
            elapsed = round(time.time() - start, 2)
            SETTINGS["g4f_provider"] = p["name"]
            SETTINGS["g4f_model"] = ""  # 用该 provider 的默认模型
            return {
                "ok": True, "provider": p["name"], "label": p["label"],
                "reply": reply, "elapsed_sec": elapsed, "tried": tried,
            }
        except Exception as e:  # noqa: BLE001
            tried.append({"provider": p["name"], "error": str(e)[:120]})
            continue

    return JSONResponse(
        {"ok": False, "error": "试了一圈免费 Provider 都没成功，建议改用「自定义 OpenAI 兼容 API」", "tried": tried},
        status_code=500,
    )


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
