# VideoNote - 视频知识沉淀与智能问答系统

基于大语言模型的视频知识沉淀与智能问答系统。输入 B 站视频链接，自动完成下载 → 转写 → 生成结构化笔记，并支持基于知识库的智能问答。

---

## 目录

- [功能一览](#功能一览)
- [快速开始（用户）](#快速开始用户)
- [使用指南](#使用指南)
- [文档格式模板](#文档格式模板)
- [开发者指南](#开发者指南)
- [项目结构](#项目结构)
- [环境变量](#环境变量)
- [常见问题](#常见问题)

---

## 功能一览

| 功能 | 说明 |
|------|------|
| 视频处理 | 输入 B 站链接，自动下载 → 语音转写 → 生成结构化笔记 |
| 笔记风格 | 支持精简、详细、教程、学术、小红书、商业等多种风格 |
| 文档格式模板 | 内置 5 套预制模板，支持切换输出结构 |
| 智能问答 | 基于笔记内容的单视频 / 跨视频知识库问答 |
| 本地 Whisper | 支持本地语音转写，也可接入 Bijian 云端服务 |
| 嵌入向量检索 | ChromaDB + DashScope Embedding，支持混合检索 |
| 多 LLM 支持 | 通义千问、DeepSeek 等 OpenAI 兼容接口 |

---

## 快速开始（用户）

### 1. 获取 API Key

- **通义千问**：在[阿里云百炼平台](https://bailian.console.aliyun.com/)获取
- **DeepSeek**：在[DeepSeek 开发平台](https://platform.deepseek.com/)获取

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

```env
VN_TONGYI_API_KEY=sk-你的通义 api-key
VN_DEEPSEEK_API_KEY=sk-你的DeepSeek api-key
```

### 3. 安装依赖

```bash
# 安装 uv（如果没有）
pip install uv

# 安装 Python 依赖
uv sync

# 安装 ffmpeg（音频提取用）
winget install ffmpeg              # Windows
brew install ffmpeg                # macOS
sudo apt install ffmpeg            # Linux

# 安装前端依赖
cd frontend
npm install
cd ..
```

### 4. 获取 B 站 Cookie（可选，用于下载高清视频）


登录 B 站，按 F12 打开开发者工具 →app应用 → http.blibli.com->复制 Cookie：



将返回值保存到设置页的「平台数据」中，或写入 `data/cookies.txt`。
写入 `data/cookies.txt` 注意格式，可以直接让AI帮生成对应的格式

### 5. 一键启动

```powershell
.\start-dev.ps1 -Backend real
```

脚本会自动启动后端（默认 `http://127.0.0.1:8000`）和前端（默认 `http://localhost:5173`）。

或分别手动启动：

```bash
# 后端
uv run uvicorn app.main:app --reload

# 前端（新终端）
cd frontend && npm run dev
```

### 6. 使用

1. 浏览器打开前端地址（默认 `http://localhost:5173`）
2. 在输入框粘贴 B 站视频链接
3. 点击「一键总结」，等待处理完成
4. 在左侧笔记列表查看生成的笔记

---

## 使用指南

### 视频处理流程

```
粘贴 B 站链接 → 解析视频信息 → 下载视频 → 语音转写 → 生成笔记 → 向量索引
```

每个阶段的状态会在前端实时显示。

### 笔记风格

在「具体配置」中可选择笔记风格，影响生成笔记的详略和语气：

| 风格 | 适用场景 |
|------|---------|
| 精简 | 快速浏览核心要点 |
| 详细 | 完整记录知识点 |
| 教程 | 教学/实操步骤 |
| 学术 | 论文/讲座整理 |
| 小红书 | 自媒体文案风格 |
| 生活向 | Vlog/生活记录 |
| 任务导向 | 行动清单式整理 |
| 商业风格 | 商业模式/市场分析 |
| 会议纪要 | 会议/讨论记录 |

### 文档格式模板

在「具体配置 → 文档格式」中可选择输出格式模板，决定笔记的**整体结构**：

| 模板 | 适用场景 |
|------|---------|
| 默认格式 | 通用总结型笔记 |
| 知识课程结构化笔记 | 网课、教程、科普视频 |
| 影视解说文案 | 电影解说、纪录片、故事类 |
| 访谈对话整理 | 人物采访、圆桌对话 |
| 短视频结构化文案 | 抖音/视频号/B站口播 |

选择模板后可在预览区查看格式内容。

### 智能问答

生成笔记后，可在问答页面对笔记内容进行提问。
系统会自动从相关的笔记中查找答案。

---

## 文档格式模板

### 模板管理

模板存储在 `data/note_format_templates.json`，格式为 `{模板名: 格式内容}`。

系统内置 5 套预制模板，可通过 API 管理：

```bash
# 列出所有模板
curl http://localhost:8000/api/v1/system/note-format/templates

# 保存新模板
curl -X POST http://localhost:8000/api/v1/system/note-format/templates \
  -H "Content-Type: application/json" \
  -d '{"name": "模板名", "format": "## 输出格式\n..."}'

# 应用模板为默认
curl -X POST http://localhost:8000/api/v1/system/note-format/templates/{name}/apply

# 删除模板
curl -X DELETE http://localhost:8000/api/v1/system/note-format/templates/{name}
```

### 模板编写规则

格式模板以 `## 输出格式` 开头，章节标题支持以下格式：

```markdown
## 输出格式
# {video_title}

## 章节名
### 子章节（MM:SS - MM:SS）
内容说明
```

- `{video_title}` — 模型会自动替换为视频标题
- `（MM:SS - MM:SS）` — 加在章节标题末尾，前端时间线视图依赖此格式解析
- 章节内容描述要清晰，告诉模型应该在对应位置输出什么

---

## 开发者指南

### 项目结构

```
AI_NOTE/
├── app/                    # 后端 Python 代码
│   ├── api/v1/             # FastAPI 路由
│   ├── core/               # 配置、数据库、工具
│   ├── llm/                # LLM 客户端（通义、DeepSeek、OpenAI 兼容）
│   ├── note/               # 笔记生成器 + 时间线解析
│   ├── pipeline/           # 视频处理流水线编排
│   ├── processor/          # 视频下载、音频提取
│   ├── qa/                 # 智能问答引擎
│   ├── retriever/          # 混合检索（向量+关键词）
│   ├── schemas/            # Pydantic 数据模型
│   ├── store/              # 向量存储 + 嵌入 + 切片
│   └── transcriber/        # 语音转写（Whisper/Bjian）
├── frontend/               # React + Vite + TypeScript 前端
├── data/                   # 运行时数据（DB、视频、笔记、配置）
├── tests/                  # 后端测试
├── docs/                   # 项目文档
└── .env                    # 环境变量配置
```

### 开发环境设置

```bash
# 克隆项目
git clone <repo-url>
cd AI_NOTE

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 安装 Python 依赖
uv sync

# 安装前端依赖
cd frontend && npm install && cd ..

# 预下载 Whisper 模型
uv run python scripts/setup_models.py

# 启动开发服务器
.\start-dev.ps1 -Backend real
```

### 扩展开发

#### 添加新的笔记风格

在 `app/note/generator.py` 的 `_STYLE_INSTRUCTIONS` 字典中添加：

```python
"my_style": (
    "## 风格要求：你的风格名\n"
    "- 描述风格的具体要求\n"
)
```

然后在 `frontend/src/constant/note.ts` 的 `noteStyles` 中添加对应选项。

#### 添加新的 LLM Provider

1. 在前端设置页面配置 Provider（名称、Base URL、API Key）
2. 在 Provider 下启用对应模型
3. 选择模型即可使用

系统默认支持 OpenAI 兼容接口的任意 Provider。

#### 添加新的格式模板

通过 API 添加：

```bash
curl -X POST http://localhost:8000/api/v1/system/note-format/templates \
  -H "Content-Type: application/json" \
  -d '{"name": "我的模板", "format": "## 输出格式\n# {video_title}\n\n..."}'
```

或直接编辑 `data/note_format_templates.json` 后重启后端。

### 运行测试

```bash
uv run pytest tests/ -x
```

### 数据库迁移

项目使用 Alembic 管理数据库迁移：

```bash
uv run alembic revision --autogenerate -m "描述"
uv run alembic upgrade head
```

### 前端开发

```bash
cd frontend

# 启动开发服务器（默认 5173）
npm run dev

# 构建生产版本
npm run build

# 预览生产构建
npm run preview
```

---

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `VN_TONGYI_API_KEY` | 是 | - | 通义千问 API Key |
| `VN_DEEPSEEK_API_KEY` | 否 | - | DeepSeek API Key |
| `VN_LLM_PROVIDER` | 否 | `tongyi` | 默认 LLM 提供商 |
| `VN_TONGYI_MODEL` | 否 | `qwen-plus` | 通义模型名 |
| `VN_DEEPSEEK_MODEL` | 否 | `deepseek-chat` | DeepSeek 模型名 |
| `VN_EMBEDDING_API_KEY` | 否 | 复用 TONGYI | 专用 embedding API Key |
| `VN_EMBEDDING_MODEL` | 否 | `text-embedding-v3` | embedding 模型名 |
| `VN_WHISPER_MODEL_SIZE` | 否 | `medium` | Whisper 模型大小 |
| `VN_WHISPER_DEVICE` | 否 | `auto` | Whisper 运行设备（cpu/cuda/auto） |
| `VN_BILIBILI_COOKIE_SOURCE` | 否 | `string` | Cookie 来源（string/file/browser/none） |
| `VN_BILIBILI_COOKIE_FILE` | 否 | `data/cookies.txt` | Cookie 文件路径 |
| `HF_ENDPOINT` | 否 | - | HuggingFace 镜像地址 |

---

## 常见问题

**笔记用了默认格式，没按选择的模板输出？** 
选择了模板后提交任务才会生效，检查「具体配置」里是否已选中对应模板。

**前端看不到格式模板？** 
确保后端已启动，模板文件存在。页面加载时会自动拉取模板列表。

**视频转写太慢？** 
Whisper 模型越大越慢越准。在 .env 中调整 VN_WHISPER_MODEL_SIZE（tiny 最快，large-v3 最准）。

**如何更换 LLM 模型？** 
提交前在「具体配置 → 大语言模型」中选择已启用的模型。如需添加新模型，先在设置页配置 Provider 并启用对应的模型。