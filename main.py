import asyncio
import json
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

# 导入 g4f 最新的 Client
from g4f.client import Client
from g4f.errors import G4fError

# 初始化 FastAPI 应用
app = FastAPI()

# 初始化 G4F Client
# 这是官方推荐的、与 g4f 交互的最新方式
client = Client()

# --- 关于模型列表的说明 ---
# g4f 的 Client API 设计上不直接提供一个“获取所有可用模型”的函数。
# 模型名称（如 "gpt-4o"）是一个别名，Client 会自动为这个别名寻找一个当前可用的 Provider。
# 因此，最可靠的方式是提供一个基于官方文档和社区实践的“推荐模型列表”。
# 用户仍然可以尝试这个列表之外的模型名称，g4f Client 会尽力去解析。
RECOMMENDED_MODELS = [
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "gemini-pro",
    "claude-3-haiku-20240307",
    "mistral-large-latest",
    # g4f 自带的一些别名
    "command-r-plus",
    "llama3-70b-8192",
]

@app.get("/")
def read_root():
    return {"message": "G4F Provider is running with official Client API"}

# OpenAI 兼容的 Models 接口
@app.get("/v1/models")
async def list_models():
    """
    提供一个基于 g4f 官方文档和实践的推荐模型列表。
    """
    model_data = []
    created_time = int(time.time())
    for model_id in RECOMMENDED_MODELS:
        model_data.append({
            "id": model_id,
            "object": "model",
            "created": created_time,
            "owned_by": "g4f-client", # 标记这是通过新 Client 提供
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
        
        # 使用 Client API 来处理请求
        async def stream_generator():
            try:
                # Client 的 stream 返回的是完整的 OpenAI Chunk 对象，而不是纯文本
                async for chunk in client.chat.completions.create(
                    model=model,
                    messages=messages,
                    stream=True,
                ):
                    # 我们需要将 g4f 返回的 chunk 对象原样转为 JSON 字符串
                    # g4f 的 chunk 结构与 OpenAI 完全兼容
                    yield f"data: {chunk.model_dump_json()}\n\n"
                
                yield "data: [DONE]\n\n"
            except G4fError as e:
                print(f"An error occurred during g4f stream: {e}")
                error_response = {
                    "error": {"message": str(e), "type": "g4f_error"}
                }
                yield f"data: {json.dumps(error_response)}\n\n"
                yield "data: [DONE]\n\n"

        if stream:
            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        else:
            # 非流式请求
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False
            )
            # g4f Client 返回的对象结构与 OpenAI 的 Response 对象几乎完全一致
            # 我们可以直接将其转为字典返回
            return response.model_dump()

    except G4fError as e:
        print(f"An G4F error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"G4F Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
