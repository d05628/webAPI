// static/app.js —— 前端交互逻辑（纯浏览器端 JS，和后端 render 是两码事）

document.getElementById('settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const provider = document.getElementById('provider-input').value;
    const models = document.getElementById('models-input').value.split(',').map(s => s.trim()).filter(Boolean);
    const use_custom_api = document.getElementById('use-custom-api').checked;
    const custom_base_url = document.getElementById('custom-base-url').value;
    const custom_api_key = document.getElementById('custom-api-key').value;
    const custom_model = document.getElementById('custom-model').value;
    const status = document.getElementById('settings-status');
    try {
        const res = await fetch('/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({provider, models, use_custom_api, custom_base_url, custom_api_key, custom_model})
        });
        status.innerHTML = res.ok
            ? '<span class="ok">设置已保存！刷新页面查看最新模型列表。</span>'
            : '<span class="err">保存失败</span>';
    } catch (err) {
        status.innerHTML = `<span class="err">出错了：${err}</span>`;
    }
});

async function testAdd() {
    const a = document.getElementById('num-a').value;
    const b = document.getElementById('num-b').value;
    const res = await fetch(`/api/add?a=${a}&b=${b}`);
    const data = await res.json();
    document.getElementById('add-result').textContent = `= ${data.result}`;
}

async function checkStatus() {
    const el = document.getElementById('status-result');
    el.textContent = '检测中...';
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        el.innerHTML = data.ok
            ? `<span class="ok">✅ 通道可用（${data.channel}）</span>`
            : `<span class="err">❌ 不可用（${data.channel}）：${data.detail}</span>`;
    } catch (err) {
        el.innerHTML = `<span class="err">检测出错：${err}</span>`;
    }
}

async function runTest() {
    const model = document.getElementById('test-model').value;
    const message = document.getElementById('test-message').value;
    const stream = document.getElementById('test-stream').checked;
    const responseDiv = document.getElementById('response');
    const status = document.getElementById('test-status');
    status.textContent = '请求中...';
    responseDiv.textContent = '';
    try {
        const res = await fetch('/v1/chat/completions', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({model, messages: [{role: 'user', content: message}], stream})
        });
        if (stream) {
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let full = '';
            while (true) {
                const {done, value} = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value);
                for (const line of chunk.split('\n')) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        if (data === '[DONE]') continue;
                        try {
                            const parsed = JSON.parse(data);
                            const delta = parsed.choices?.[0]?.delta?.content;
                            if (delta) { full += delta; responseDiv.textContent = full; }
                            if (parsed.error) { responseDiv.textContent = '错误：' + parsed.error.message; }
                        } catch (e) {}
                    }
                }
            }
        } else {
            const data = await res.json();
            responseDiv.textContent = data.choices ? data.choices[0].message.content : JSON.stringify(data, null, 2);
        }
        status.textContent = '完成';
    } catch (err) {
        status.textContent = '出错了';
        responseDiv.textContent = err.message;
    }
}
