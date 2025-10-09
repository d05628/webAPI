import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
import g4f
import json

# 初始化 FastAPI 应用
app = FastAPI()

# G4F 可用模型列表 (可以根据需要自行增删)
# 你可以通过 g4f.Provider.main.get_models() 获取更多
SUPPORTED_MODELS = [
    "gpt-3.5-turbo",
    "gpt-4",
    "gpt-4-turbo",
    "gpt-4o",
    "gemini-pro",
    "claude-3-haiku-20240307"
]

@app.get("/")
def read_root():
    return {"message": "G4F Provider is running"}

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
        
        # 确认模型是否受支持
        # g4f 会自动选择一个能用这个模型的 provider
        if model not in SUPPORTED_MODELS:
            print(f"Warning: Model '{model}' not in explicitly supported list, but attempting to proceed.")

        # 定义 g4f 的响应函数
        async def stream_response():
            try:
                # 使用 g4f 创建响应
                response_stream = await g4f.ChatCompletion.create_async(
                    model=model,
                    messages=messages,
                    stream=True,
                )
                
                # 流式响应
                chunk_id = 0
                for chunk in response_stream:
                    # 构建 SSE (Server-Sent Events) 格式
                    response_json = {
                        "id": f"chatcmpl-{chunk_id}",
                        "object": "chat.completion.chunk",
                        "created": asyncio.get_event_loop().time(),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": chunk},
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(response_json)}\n\n"
                    chunk_id += 1

                # 发送结束标志
                finish_json = {
                    "id": f"chatcmpl-{chunk_id}",
                    "object": "chat.completion.chunk",
                    "created": asyncio.get_event_loop().time(),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(finish_json)}\n\n"
                yield "data: [DONE]\n\n"

            except Exception as e:
                error_detail = f"Error during g4f stream: {str(e)}"
                print(error_detail)
                # 在流中发送错误信息可能比较困难，这里主要是在服务端打印
                # 也可以尝试发送一个错误格式的 SSE
                error_json = {"error": error_detail}
                yield f"data: {json.dumps(error_json)}\n\n"


        # 根据 stream 参数决定返回类型
        if stream:
            return StreamingResponse(stream_response(), media_type="text/event-stream")
        else:
            # 非流式响应
            response = await g4f.ChatCompletion.create_async(
                model=model,
                messages=messages,
                stream=False
            )
            return {
                "id": f"chatcmpl-{asyncio.get_event_loop().time()}",
                "object": "chat.completion",
                "created": int(asyncio.get_event_loop().time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response,
                    },
                    "finish_reason": "stop",
                }],
                "usage": {
                    "prompt_tokens": 0, # g4f 不提供 token 计数
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            }

    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# OpenAI 兼容的 Models 接口
@app.get("/v1/models")
async def list_models():
    model_data = []
    current_time = int(asyncio.get_event_loop().time())
    for model_id in SUPPORTED_MODELS:
        model_data.append({
            "id": model_id,
            "object": "model",
            "created": current_time,
            "owned_by": "g4f",
        })
    return {"object": "list", "data": model_data}