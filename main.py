import asyncio
import json
import os
import time
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

# Import the g4f AsyncClient for asynchronous compatibility
from g4f.client import AsyncClient

# Initialize the FastAPI app
app = FastAPI()

# Initialize the G4F AsyncClient
client = AsyncClient()

# Settings file path
SETTINGS_FILE = "settings.json"

# Default settings
DEFAULT_PROVIDER = "You"
DEFAULT_MODELS = [
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

def load_settings():
    """Load settings from JSON file."""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {"provider": DEFAULT_PROVIDER, "models": DEFAULT_MODELS}

def save_settings(settings):
    """Save settings to JSON file."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

# Load initial settings
settings = load_settings()

@app.get("/")
async def read_root():
    """Return an interactive HTML settings and testing page."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>G4F Provider Settings & Test</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            section { margin-bottom: 30px; border: 1px solid #ddd; padding: 20px; border-radius: 8px; }
            input, select, textarea { width: 100%; padding: 8px; margin: 5px 0; }
            button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0056b3; }
            #response { background: #f8f9fa; padding: 10px; border-radius: 4px; white-space: pre-wrap; min-height: 100px; }
            .error { color: red; }
            .success { color: green; }
        </style>
    </head>
    <body>
        <h1>G4F Provider: Settings & Testing</h1>
        
        <section>
            <h2>Current Settings</h2>
            <p><strong>Provider:</strong> <span id="current-provider">{provider}</span></p>
            <p><strong>Models:</strong> <span id="current-models">{models}</span></p>
            <button onclick="loadSettings()">Refresh</button>
        </section>
        
        <section>
            <h2>Update Settings</h2>
            <form id="settings-form">
                <label>Provider (e.g., You, Bing):</label>
                <input type="text" id="provider-input" value="{provider}">
                
                <label>Models (comma-separated, e.g., gpt-4o,gpt-3.5-turbo):</label>
                <textarea id="models-input" rows="3">{models_str}</textarea>
                
                <button type="submit">Save Settings</button>
            </form>
            <div id="settings-status"></div>
        </section>
        
        <section>
            <h2>Simple Test</h2>
            <label>Model:</label>
            <select id="test-model">
                {model_options}
            </select>
            
            <label>Message:</label>
            <textarea id="test-message" rows="2">Hello, please respond with a short summary of yourself.</textarea>
            
            <label>Stream:</label>
            <input type="checkbox" id="test-stream">
            
            <button onclick="runTest()">Run Test</button>
            <div id="test-status"></div>
            <div id="response"></div>
        </section>
        
        <script>
            const API_BASE = '/';
            const currentProvider = '{provider}';
            const currentModels = {models_json};
            
            function loadSettings() {{
                fetch('/settings')
                    .then(r => r.json())
                    .then(data => {{
                        document.getElementById('current-provider').textContent = data.provider;
                        document.getElementById('current-models').textContent = data.models.join(', ');
                        updateModelOptions(data.models);
                    }});
            }}
            
            function updateModelOptions(models) {{
                const select = document.getElementById('test-model');
                select.innerHTML = models.map(m => `<option value="${{m}}">${{m}}</option>`).join('');
            }}
            
            document.getElementById('settings-form').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const provider = document.getElementById('provider-input').value;
                const models = document.getElementById('models-input').value.split(',').map(m => m.trim()).filter(m => m);
                const status = document.getElementById('settings-status');
                try {{
                    const res = await fetch('/settings', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{provider, models}}) }});
                    if (res.ok) {{
                        status.innerHTML = '<span class="success">Settings saved!</span>';
                        loadSettings();
                    }} else {{
                        status.innerHTML = '<span class="error">Save failed.</span>';
                    }}
                }} catch (err) {{
                    status.innerHTML = `<span class="error">Error: ${{err}}</span>`;
                }}
            }});
            
            async function runTest() {{
                const model = document.getElementById('test-model').value;
                const message = document.getElementById('test-message').value;
                const stream = document.getElementById('test-stream').checked;
                const responseDiv = document.getElementById('response');
                const status = document.getElementById('test-status');
                status.innerHTML = 'Testing...';
                responseDiv.innerHTML = '';
                try {{
                    const res = await fetch('/v1/chat/completions', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            model, messages: [{{role: 'user', content: message}}], stream
                        }})
                    }});
                    if (stream) {{
                        const reader = res.body.getReader();
                        const decoder = new TextDecoder();
                        let fullResponse = '';
                        while (true) {{
                            const {{done, value}} = await reader.read();
                            if (done) break;
                            const chunk = decoder.decode(value);
                            const lines = chunk.split('\\n');
                            for (const line of lines) {{
                                if (line.startsWith('data: ')) {{
                                    const data = line.slice(6);
                                    if (data === '[DONE]') break;
                                    try {{
                                        const parsed = JSON.parse(data);
                                        if (parsed.choices && parsed.choices[0].delta && parsed.choices[0].delta.content) {{
                                            fullResponse += parsed.choices[0].delta.content;
                                            responseDiv.innerHTML = fullResponse;
                                        }}
                                    }} catch (e) {{ /* Ignore invalid chunks */ }}
                                }}
                            }}
                        }}
                    }} else {{
                        const data = await res.json();
                        if (data.choices) {{
                            responseDiv.innerHTML = data.choices[0].message.content;
                        }} else {{
                            responseDiv.innerHTML = JSON.stringify(data, null, 2);
                        }}
                    }}
                    status.innerHTML = '<span class="success">Test complete.</span>';
                }} catch (err) {{
                    status.innerHTML = `<span class="error">Test error: ${{err}}</span>`;
                    responseDiv.innerHTML = err.message;
                }}
            }}
            
            // Initialize
            updateModelOptions(currentModels);
            loadSettings();
        </script>
    </body>
    </html>
    """.format(
        provider=settings["provider"],
        models=", ".join(settings["models"]),
        models_str=",\n".join(settings["models"]),
        models_json=json.dumps(settings["models"]),
        model_options="\n".join([f'<option value="{m}">{m}</option>' for m in settings["models"]])
    )
    return HTMLResponse(content=html_content)

class ProviderRequest(BaseModel):
    provider: str

class SettingsRequest(BaseModel):
    provider: str
    models: list[str]

@app.get("/provider")
async def get_provider():
    """Query current provider."""
    return {"provider": settings["provider"]}

@app.post("/provider")
async def set_provider(request: ProviderRequest):
    """Set provider and persist."""
    settings["provider"] = request.provider
    save_settings(settings)
    return {"message": "Provider updated", "provider": request.provider}

@app.get("/settings")
async def get_settings():
    """Query full settings."""
    return settings

@app.post("/settings")
async def set_settings(request: SettingsRequest):
    """Set provider and models, persist."""
    settings["provider"] = request.provider
    settings["models"] = request.models
    save_settings(settings)
    return {"message": "Settings updated", "settings": settings}

@app.get("/v1/models")
async def list_models():
    """List available models from settings."""
    model_data = []
    created_time = int(time.time())
    for model_id in settings["models"]:
        model_data.append({
            "id": model_id,
            "object": "model",
            "created": created_time,
            "owned_by": "g4f-client",
        })
    return {"object": "list", "data": model_data}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
        model = body.get("model", "gpt-3.5-turbo")
        messages = body.get("messages")
        stream = body.get("stream", False)

        if not messages:
            raise HTTPException(status_code=400, detail="'messages' field is required.")
        
        # Use persisted provider, fallback to default
        provider = settings.get("provider", DEFAULT_PROVIDER)
        
        async def stream_generator():
            try:
                async for chunk in client.chat.completions.stream(
                    model=model,
                    messages=messages,
                    provider=provider,
                ):
                    yield f"data: {chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                print(f"g4f stream error: {e}")
                error_response = {"error": {"message": str(e), "type": "g4f_error"}}
                yield f"data: {json.dumps(error_response)}\n\n"
                yield "data: [DONE]\n\n"

        if stream:
            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        else:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                provider=provider,
            )
            return response.model_dump()

    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
