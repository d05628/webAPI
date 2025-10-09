import asyncio
import json
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

# Import the g4f AsyncClient for asynchronous compatibility
from g4f.client import AsyncClient

# Initialize the FastAPI app
app = FastAPI()

# Initialize the G4F AsyncClient
client = AsyncClient()

# As g4f's Client API doesn't provide a direct function to get all model names,
# the most reliable approach is to provide a curated list of recommended models
# based on official documentation and community practice.
RECOMMENDED_MODELS = [
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "gemini-pro",
    "claude-3-haiku-20240307",
    "mistral-large-latest",
    "command-r-plus",
    "llama3-70b-8192",
]

@app.get("/")
def read_root():
    return {"message": "G4F Provider is running with official AsyncClient API"}

# OpenAI-compatible Models endpoint
@app.get("/v1/models")
async def list_models():
    """
    Provides a recommended list of models based on g4f documentation.
    """
    model_data = []
    created_time = int(time.time())
    for model_id in RECOMMENDED_MODELS:
        model_data.append({
            "id": model_id,
            "object": "model",
            "created": created_time,
            "owned_by": "g4f-client",
        })
    return {"object": "list", "data": model_data}

# OpenAI-compatible Chat Completions endpoint
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
        model = body.get("model", "gpt-3.5-turbo")
        messages = body.get("messages")
        stream = body.get("stream", False)

        if not messages:
            raise HTTPException(status_code=400, detail="'messages' field is required.")
        
        # --- KEY CHANGE: Use AsyncClient for streaming and non-streaming ---
        async def stream_generator():
            try:
                # Use .stream() method for asynchronous streaming
                async for chunk in client.chat.completions.stream(
                    model=model,
                    messages=messages,
                ):
                    # Directly yield the chunk as JSON (compatible with OpenAI format)
                    yield f"data: {chunk.model_dump_json()}\n\n"
                
                yield "data: [DONE]\n\n"
            except Exception as e:
                print(f"An error occurred during g4f stream: {e}")
                error_response = {
                    "error": {"message": str(e), "type": "g4f_error"}
                }
                yield f"data: {json.dumps(error_response)}\n\n"
                yield "data: [DONE]\n\n"

        if stream:
            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        else:
            # For non-streamed requests, await the .create() method
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
            )
            # Return the dumped response (OpenAI-compatible)
            return response.model_dump()

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
