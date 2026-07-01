# VideoNote - 视频知识沉淀与智能问答系统

基于大语言模型的视频知识沉淀与智能问答 Web 系统。

## 功能

- 输入 B 站链接，自动下载 -> 转写 -> 生成结构化笔记
- 单视频精准问答
- 跨视频知识库检索问答

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
