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
- **② Provider / 模型设置**：可视化修改 g4f provider、模型列表，或者切换到
  自定义 OpenAI 兼容 API（推荐，稳定性更好）。
- **③ 计算器小工具**：演示前端 JS `fetch()` 异步调用后端接口，与 render 做对比。
- **④ AI 对话测试区**：可选流式/非流式输出，附带"通道检测"按钮，
  一键测试当前对话通道是否可用。

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
| POST | `/api/chat` | 对话接口，`{messages, stream}` |
| GET | `/api/check_channel` | 通道检测 |
