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


## 快速开始

本项目使用 **uv** 管理依赖，Python 版本锁定在 **3.13.3**（见 `.python-version`）。

```bash
# 安装 uv（如果没有）
pip install uv

# 创建虚拟环境并安装依赖
uv sync

# 启动开发服务器
uv run uvicorn app.main:app --reload
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

项目根目录提供了 PowerShell 启动脚本，可以根据参数选择真实后端或 mock 后端，并自动同时启动后端与前端。脚本会优先使用 `uv run uvicorn`；如果当前环境没有 `uv`，会自动回退到 `python -m uvicorn` 或 `py -m uvicorn`。

脚本会在启动前检查端口：

- 如果后端端口已经有服务并且 `/health` 可访问，会复用这个后端，不再重复启动。
- 如果后端端口被其它程序占用，默认自动寻找下一个可用端口，并同步修改前端 `VITE_API_BASE_URL`。
- 如果前端端口被占用，默认自动寻找下一个可用端口。
- 如果希望端口被占用时直接报错，可加 `-StrictPorts`。

使用 mock 后端：

```powershell
cd D:\code\github-pgm\AI_NOTE
.\start-dev.ps1 -Backend mock
```

mock 后端默认会预置固定样例 `https://www.bilibili.com/video/BV1aeLqzUE6L`，用于稳定验证笔记、字幕脚本和原文细读。除此之外，mock 生成的任务只保存在内存里，不会作为真实知识库数据长期保留。如需启动完全空的 mock 后端，可显式加 `-NoSeedMockFixture`：

```powershell
.\start-dev.ps1 -Backend mock -NoSeedMockFixture
```

使用真实后端：

```powershell
cd D:\code\github-pgm\AI_NOTE
.\start-dev.ps1 -Backend real
```

常用可选参数：

```powershell
.\start-dev.ps1 -Backend mock -MockBackendPort 8010 -FrontendPort 5173
.\start-dev.ps1 -Backend real -RealBackendPort 8000 -FrontendPort 5173
.\start-dev.ps1 -Backend real -RealBackendPort 8001 -FrontendPort 5174
.\start-dev.ps1 -Backend real -StrictPorts
```

脚本会打开两个 PowerShell 窗口：一个运行后端，一个运行前端。mock 模式会启动 `mock_backend.app:app`，真实模式会启动 `app.main:app`；前端会自动设置 `VITE_API_BASE_URL` 指向所选后端。

