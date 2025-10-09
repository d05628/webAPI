import asyncio
import json
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
import g4f

# 导入 g4f 的基础模型类，以便查询它的所有子类
from g4f.models import Model

# 初始化 FastAPI 应用
app = FastAPI()

# 存放动态获取的模型列表的缓存
# { "models": [...], "last_updated": timestamp }
model_cache = {
    "models": [],
    "last_updated": 0
}
CACHE_DURATION = 3600 # 缓存1小时 (3600秒)

def get_dynamic_models():
    """
    动态获取 g4f 支持的模型列表，并进行缓存。
    使用 g4f.Model.__subclasses__() 的方式来获取所有模型类。
    """
    global model_cache
    current_time = time.time()

    # 如果缓存有效，则直接返回缓存数据
    if model_cache["models"] and (current_time - model_cache["last_updated"] < CACHE_DURATION):
        return model_cache["models"]

    print("Cache expired or empty. Fetching new model list from g4f...")
    try:
        # --- 主要修改点 ---
        # 旧代码 (错误): all_models = g4f.models.ModelUtils.get_models()
        # 新代码 (正确): 直接获取所有继承了 g4f.models.Model 的子类
        all_model_classes = Model.__subclasses__()
        
        # 我们需要模型的名称 (__name__)
        model_names = [model.__name__ for model in all_model_classes if hasattr(model, '__name__')]
        
        # 更新缓存
        model_cache["models"] = sorted(list(set(model_names))) # 排序并去重
        model_cache["last_updated"] = current_time
        print(f"Successfully fetched and cached {len(model_cache['models'])} models.")
        return model_cache["models"]
    except Exception as e:
        print(f"Error fetching dynamic models: {e}")
        # 如果获取失败，返回一个保底的基础模型列表
        return ["gpt-3.5-turbo", "gpt-4", "gpt-4o", "gemini-pro"]

@app.get("/")
def read_root():
    return {"message": "G4F Provider is running"}

# OpenAI 兼容的 Models 接口
@app.get("/v1/models")
async def list_models():
    """
    提供兼容 OpenAI 的模型列表接口，数据源于动态获取的 g4f 模型。
    """
    model_names = get_dynamic_models()
    model_data = []
    created_time = int(time.time())

    for model_id in model_names:
        model_data.append({
            "id": model_id,
            "object": "model",
            "created": created_time,
            "owned_by": "g4f",
        })
    return {"object": "list", "data": model_data}

# OpenAI 兼容的 Chat Completions 接口
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
        model = body.get("model", "gpt-3.5-turbo")
        messages = body.get("messages")
        stream = body.get("stream", False)

        if not messages:
            raise HTTPException(status_code=400, detail="'messages' field is required.")
        
        async def stream_generator():
            try:
                async for chunk in g4f.ChatCompletion.create_async(
                    model=model,
                    messages=messages,
                    stream=True,
                ):
                    response_json = {
                        "id": f"chatcmpl-{int(time.time())}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": chunk},
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(response_json)}\n\n"

                finish_json = {
                    "id": f"chatcmpl-{int(time.time())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(finish_json)}\n\n"
                yield "data: [DONE]\n\n"

            except Exception as e:
                print(f"Error during g4f stream: {e}")
                error_response = {
                    "error": {
                        "message": f"An error occurred during the stream: {str(e)}",
                        "type": "g4f_error",
                    }
                }
                yield f"data: {json.dumps(error_response)}\n\n"
                yield "data: [DONE]\n\n"

        if stream:
            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        else:
            response_content = await g4f.ChatCompletion.create_async(
                model=model,
                messages=messages,
                stream=False
            )
            return {
                "id": f"chatcmpl-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": response_content},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }

    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))
