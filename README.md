# 全老师的测试页 —— FastAPI 版

用 FastAPI 部署的中文教学/测试页面，演示两件事：

1. **render 的用法**：FastAPI 用 `Jinja2Templates().TemplateResponse()` 做模板渲染
   （等价于 Flask 的 `render_template`）。首页和 `/render_demo` 都是完整的
   render 教学示例，模板文件在 `templates/` 目录，代码里有详细中文注释。
2. **G4F 对话接口测试**：转接 G4F 等免费/兼容 OpenAI 协议的对话服务，并留了
   "自定义 API" 备用通道，防止免费 provider 失效导致测试跑不通。

## 项目结构

```
g4f-render-demo/
├── main.py                  # FastAPI 主程序（render + calc + settings + chat 接口）
├── requirements.txt
├── templates/
│   ├── index.html            # 首页：render 演示 + 设置 + 计算器 + AI 对话
│   └── render_demo.html      # 纯粹的 render 小例子（URL 参数驱动）
└── static/
    └── style.css
```

## 本地运行

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

打开浏览器访问 http://127.0.0.1:8000 即可看到测试页。

## 页面功能

- **① render 演示**：展示服务器端模板渲染（变量、循环、条件），刷新页面
  可看到时间/随机数变化；`/render_demo?name=xxx&mood=xxx` 是一个可以直接改
  URL 参数体验 render 的小例子。
- **② Provider / 模型设置**：g4f Provider / 模型下拉框都是**实时拉取**的（不是写死的文本框），
  支持一键"🔄 刷新列表"、"🧪 测试这个 Provider"、"⚡ 自动选择可用 Provider"；
  也可以切换到自定义 OpenAI 兼容 API（推荐，稳定性更好）。
- **③ 计算器小工具**：演示前端 JS `fetch()` 异步调用后端接口，与 render 做对比。
- **④ AI 对话测试区**：可选流式/非流式输出，附带"通道检测"按钮，
  一键测试当前对话通道是否可用。
- **⑤ 图片生成**：文生图，Provider/模型实时发现，默认推荐 `AnyProvider`
  （它自己会在背后依次尝试几十个免费图片后端，成功率最高）。
- **⑥ 语音生成**：文字转语音，可填音色（不同 Provider 音色名不同，比如
  OpenAIFM 是 alloy/ash/coral 这种）和输出格式。
- **⑦ 视频生成**：文生视频，免费视频 Provider 本来就不多，同样推荐用 `AnyProvider`；
  视频生成通常比较慢，耐心等 1~3 分钟。

生成出来的图片/语音/视频，要么是 Provider 给的外部直链，要么会自动存到项目目录下的
`generated_media/` 文件夹，并通过 `/media/xxx` 这个路径直接在页面上播放/展示
（这个目录就是 g4f 库自己默认的媒体缓存目录，不用额外配置）。

## 关于 G4F Provider / 模型的实时发现（重要）

早期版本有个 bug：用 `getattr(g4f.Provider, provider_name)` 取 Provider 类，
但在新版 g4f（7.x）里这个路径拿到的其实是"子模块"而不是真正的 Provider 类，
导致调用静默失败。现在已经改成从 `g4f.Provider.ProviderUtils.convert` 这个字典
按名字取真正的类，并且统一用官方现在推荐的 `g4f.client.Client`（OpenAI 风格）。

图片/语音/视频三种能力的 Provider 和模型，优先从 Provider 类自带的
`image_models` / `audio_models` / `video_models` 属性里读（不用额外发请求，
速度快）；拿不到就去 `g4f.models.ModelUtils` 这个全局"模型 → Provider 兜底链"
注册表里找同类型、且兜底链里包含这个 Provider 的模型。

`AnyProvider` 是 g4f 内置的聚合器，背后接了几十个图片/视频/语音后端，
免登录、覆盖面最广，所以页面上每种媒体能力都默认选中它——不知道选哪个
就用它，它自己会依次尝试直到成功。

## 关于 G4F 不稳定的说明

g4f 依赖的是免费/非官方通道，本身并不保证一直可用。本项目做了两点优化：

1. provider 默认留空，让 g4f 自动选择当前可用的通道，失败时再自动重试一次；
2. 提供"自定义 OpenAI 兼容 API"开关 —— 只要填入任意 OpenAI 兼容的 API Key
   （OpenAI 官方 / DeepSeek / Kimi / 通义千问兼容模式等），AI 对话测试区就能
   稳定使用，不再依赖免费 provider 当天是否可用。

## 部署到 Render

1. 把这个仓库连接到 Render，新建一个 Web Service；
2. Build Command：`pip install -r requirements.txt`
3. Start Command：`uvicorn main:app --host 0.0.0.0 --port $PORT`
4. 部署完成后即可通过 `xxx.onrender.com` 访问。

注意：Render 免费套餐闲置一段时间会自动休眠，下一次请求需要 30~60 秒冷启动，
属于正常现象，升级付费套餐可避免。

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 首页，render 教学 + 全部功能入口 |
| GET | `/render_demo?name=&mood=` | render 小例子 |
| POST | `/api/calc` | 计算器接口，`{a, b, op}` |
| GET | `/api/settings` | 获取当前 provider / API 设置 |
| POST | `/api/settings` | 保存 provider / API 设置 |
| GET | `/api/g4f/providers` | 实时列出可用的聊天 Provider |
| GET | `/api/g4f/models?provider=` | 实时列出某聊天 Provider 支持的模型 |
| POST | `/api/g4f/test_provider` | 单独测试某个聊天 Provider+模型 |
| GET | `/api/g4f/auto_pick` | 自动挑一个当前可用的免费聊天 Provider |
| GET | `/api/g4f/capability_providers?capability=` | 实时列出某种能力（image/audio/video）的 Provider |
| GET | `/api/g4f/capability_models?provider=&capability=` | 实时列出某 Provider 在某能力下的模型 |
| POST | `/api/g4f/media/generate` | 统一的图片/语音/视频生成入口 |
| POST | `/api/chat` | 对话接口，`{messages, stream}` |
| GET | `/api/check_channel` | 通道检测 |
