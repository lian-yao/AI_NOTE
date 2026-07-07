# VideoNote - 视频知识沉淀与智能问答系统

基于大语言模型的视频知识沉淀与智能问答 Web 系统。

## 功能

- 输入 B 站链接，自动下载 -> 转写 -> 生成结构化笔记
- 单视频精准问答
- 跨视频知识库检索问答

## 开始工作

在阿里云百炼平台和DeepSeek开发平台获取api-key(ds一般要充值才能正常使用)

执行:

copy .env.example .env

再打开env文件，设置：

VN_TONGYI_API_KEY=sk-你的通义 api-key

VN_DEEPSEEK_API_KEY=sk-你的DeepSeek api-key

获取B站cookie:

登录B站，按下Ctrl+shift+i,点击“+”里的应用程序，左侧列表的cookie,点击cookie前面的倒三角符号，会有链接，点击https://bilibili.com,就会有各类信息，复制给ai，让其整理成cookie链接，复制该链接保存到到设置里的平台数据里


## 一键启动前后端

```powershell
.\start-dev.ps1 -Backend real
```

脚本会自动启动后端（uvicorn）和前端（Vite），并打开两个 PowerShell 窗口。
后端默认运行在 http://127.0.0.1:8000，前端默认运行在 http://localhost:5173。

如果只想分别手动启动：

```bash
# 后端
uv run uvicorn app.main:app --reload

# 前端（新终端）
cd frontend && npm run dev
```

## 快速开始

本项目使用 **uv** 管理依赖，Python 版本锁定在 **3.13.3**（见 `.python-version`）。

```bash
# 安装 uv（如果没有）
pip install uv

# 创建虚拟环境并安装依赖
uv sync
```

## 环境准备

首次 clone 项目后，需要额外安装两个运行时依赖：

**1. 安装 ffmpeg**（音频提取，选一个即可）

```bash
winget install ffmpeg              # Windows
brew install ffmpeg                # macOS
sudo apt install ffmpeg            # Linux
```

**2. 配置环境变量**

```bash
cp .env.example .env              # 复制模板，按需修改 API Key 等
```

**3. 预下载 Whisper 模型**（避免首次转写时等待）

```bash
uv run python scripts/setup_models.py   # 读取 .env 里的 WHISPER_MODEL_SIZE
```

## 前端启动

前端项目在 `frontend/` 目录下，使用 **npm** 安装依赖并启动：

```bash
cd frontend
npm install
npm run dev
```

默认访问地址为 `http://localhost:5173`。如需指定端口：

```bash
VITE_FRONTEND_PORT=5190 npm run dev
```

Windows PowerShell：

```powershell
$env:VITE_FRONTEND_PORT=5190; npm run dev
```

如果 `npm install` 遇到 peer dependency / ERESOLVE 问题，可尝试：

```bash
npm install --legacy-peer-deps
```

详细说明见 [环境搭建与快速启动指南](docs/环境搭建与快速启动指南.md)。

## 开发启动脚本

项目根目录提供了 `start-dev.ps1`，可一次性启动前后端。脚本会打开两个 PowerShell 窗口，分别运行后端和前端。

```powershell
.\start-dev.ps1 -Backend real
```

脚本功能：
- 优先使用 `uv run uvicorn`，回退到 `python -m uvicorn`
- 端口被占用时自动寻找下一个可用端口
- 自动设置前端环境变量 `VITE_API_BASE_URL` 指向后端地址
- 后端已启动时自动复用（检查 `/health`）

常用参数：

```powershell
.\start-dev.ps1 -Backend real -RealBackendPort 8000 -FrontendPort 5173
.\start-dev.ps1 -Backend real -RealBackendPort 8001 -FrontendPort 5174
.\start-dev.ps1 -Backend real -StrictPorts
.\start-dev.ps1 -Backend real -NoReload
```
