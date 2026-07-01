# API 接口文档

## 视频知识沉淀与智能问答系统

| 文档版本 | 日期 | 作者 | 变更说明 |
|---------|------|------|---------|
| v1.0 | 2026-06-30 | Codex | 初稿完成 |

---

## 1. 概述

### 1.1 基本信息

| 项目 | 值 |
|------|-----|
| 基础路径 | `http://localhost:8000/api/v1` |
| 数据格式 | JSON (Content-Type: application/json) |
| 流式输出 | Server-Sent Events (SSE) |
| 实时推送 | WebSocket (路径: `/ws/task/{task_id}`) |
| 文档地址 | `http://localhost:8000/docs` (FastAPI Auto-generated) |

### 1.2 通用响应格式

```json
{
    "code": 0,
    "message": "success",
    "data": { ... }
}
```

**错误响应：**

```json
{
    "code": 40001,
    "message": "视频链接解析失败",
    "detail": "...具体的错误原因..."
}
```

### 1.3 通用错误码

| code | message | HTTP Status | 说明 |
|------|---------|-------------|------|
| 0 | success | 200 | 请求成功 |
| 40000 | bad_request | 400 | 请求参数错误 |
| 40001 | invalid_url | 400 | 无效的视频链接 |
| 40002 | video_not_found | 404 | 视频不存在 |
| 40003 | note_not_found | 404 | 笔记不存在 |
| 40004 | task_not_found | 404 | 任务不存在 |
| 40005 | already_processing | 409 | 视频正在处理中 |
| 50000 | internal_error | 500 | 服务器内部错误 |
| 50001 | llm_api_error | 502 | LLM API 调用失败 |
| 50002 | transcriber_error | 502 | 语音转写失败 |
| 50003 | download_error | 502 | 视频下载失败 |
| 50004 | storage_error | 500 | 存储异常 |

---

## 2. 视频管理接口

### 2.1 解析视频链接

解析 B 站视频链接，返回视频元数据。

```
POST /api/v1/videos/parse
```

**请求体：**

```json
{
    "url": "https://www.bilibili.com/video/BV1xx411c7mD"
}
```

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "video_id": "b_BV1xx411c7mD",
        "title": "视频标题",
        "uploader": "UP主名称",
        "uploader_uid": "12345",
        "duration_seconds": 1800,
        "cover_url": "https://i0.hdslb.com/bfs/archive/xxx.jpg",
        "bvid": "BV1xx411c7mD",
        "avid": 1234567,
        "description": "视频简介...",
        "is_playlist": false,
        "playlist_title": null
    }
}
```

### 2.2 提交视频处理

提交视频链接到处理流水线。

```
POST /api/v1/videos/process
```

**请求体：**

```json
{
    "url": "https://www.bilibili.com/video/BV1xx411c7mD",
    "quality": "1080p",
    "transcriber": "auto",
    "keep_video": false
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| url | string | 是 | - | B 站视频链接 |
| quality | string | 否 | "1080p" | 下载画质: 360p/480p/720p/1080p |
| transcriber | string | 否 | "auto" | 转写方式: local/bjian/auto |
| keep_video | boolean | 否 | false | 处理后是否保留视频文件 |

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "video_id": "b_BV1xx411c7mD",
        "task_id": "uuid-xxxx",
        "status": "pending"
    }
}
```

### 2.3 获取视频列表

获取所有已处理/处理中的视频列表。

```
GET /api/v1/videos?page=1&page_size=20&status=completed&search=%E6%9C%BA%E5%99%A8%E5%AD%A6%E4%B9%A0
```

**查询参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| page | integer | 否 | 1 | 页码 |
| page_size | integer | 否 | 20 | 每页条数（最大 100） |
| status | string | 否 | - | 过滤状态: pending/downloading/transcribing/generating/storing/completed/failed |
| search | string | 否 | - | 搜索关键词（按标题搜索） |

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "items": [
            {
                "id": 1,
                "video_id": "b_BV1xx411c7mD",
                "title": "视频标题",
                "uploader": "UP主名称",
                "duration_seconds": 1800,
                "cover_url": "https://i0.hdslb.com/bfs/archive/xxx.jpg",
                "status": "completed",
                "has_note": true,
                "processed_at": "2026-06-30T12:00:00",
                "created_at": "2026-06-30T11:00:00"
            }
        ],
        "total": 42,
        "page": 1,
        "page_size": 20
    }
}
```

### 2.4 获取视频详情

获取单个视频的详细信息，包括处理状态和笔记概要。

```
GET /api/v1/videos/{video_id}
```

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "id": 1,
        "video_id": "b_BV1xx411c7mD",
        "url": "https://www.bilibili.com/video/BV1xx411c7mD",
        "title": "视频标题",
        "uploader": "UP主名称",
        "uploader_uid": "12345",
        "description": "视频简介...",
        "duration_seconds": 1800,
        "cover_url": "https://i0.hdslb.com/bfs/archive/xxx.jpg",
        "bvid": "BV1xx411c7mD",
        "avid": 1234567,
        "status": "completed",
        "file_size": 524288000,
        "note": {
            "id": 1,
            "summary": "笔记摘要...",
            "keywords": ["关键词1", "关键词2"],
            "total_chunks": 15,
            "section_count": 5,
            "char_count": 8500,
            "created_at": "2026-06-30T12:30:00"
        },
        "tasks": [
            {
                "task_id": "uuid-xxx",
                "type": "download",
                "status": "completed",
                "progress": 100
            },
            {
                "task_id": "uuid-yyy",
                "type": "transcribe",
                "status": "completed",
                "progress": 100
            },
            {
                "task_id": "uuid-zzz",
                "type": "generate",
                "status": "completed",
                "progress": 100
            }
        ],
        "processed_at": "2026-06-30T12:30:00",
        "created_at": "2026-06-30T11:00:00"
    }
}
```

### 2.5 删除视频

删除视频及其所有关联数据。

```
DELETE /api/v1/videos/{video_id}
```

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "deleted_video": true,
        "deleted_notes": true,
        "deleted_chunks": 15,
        "deleted_vectors": 15,
        "freed_space_bytes": 524288000
    }
}
```

---

## 3. 笔记接口

### 3.1 获取笔记详情

获取视频的结构化笔记内容。

```
GET /api/v1/notes/{video_id}
```

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "id": 1,
        "video_id": "b_BV1xx411c7mD",
        "video_title": "视频标题",
        "summary": "## 摘要\n\n本文主要介绍...",
        "keywords": ["机器学习", "深度学习", "神经网络"],
        "sections": [
            {
                "title": "引言",
                "start_time": 0,
                "end_time": 120,
                "content": "在本文中，我们将讨论...",
                "chunk_index": 0
            },
            {
                "title": "核心原理",
                "start_time": 120,
                "end_time": 600,
                "content": "该算法的核心思想是...",
                "chunk_index": 1
            }
        ],
        "total_chunks": 15,
        "section_count": 5,
        "char_count": 8500,
        "created_at": "2026-06-30T12:30:00"
    }
}
```

### 3.2 获取笔记原始 Markdown

获取笔记的原始 Markdown 文本。

```
GET /api/v1/notes/{video_id}/raw
```

**响应头：** `Content-Type: text/markdown; charset=utf-8`

**响应体：**

```markdown
# 视频标题

## 摘要
...

## 关键词
...

## 内容整理
...
```

---

## 4. 智能问答接口

### 4.1 单视频问答

针对特定视频内容进行问答。

```
POST /api/v1/qa/ask
```

**请求体：**

```json
{
    "video_id": "b_BV1xx411c7mD",
    "query": "文章中的核心算法是什么？",
    "stream": true,
    "top_k": 5
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| video_id | string | 是 | - | 视频 ID |
| query | string | 是 | - | 用户问题 |
| stream | boolean | 否 | true | 是否流式输出 |
| top_k | integer | 否 | 5 | 检索返回的片段数量 |

**非流式响应（stream=false）：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "answer": "该视频中介绍的核心算法是**Transformer**，它是一种基于自注意力机制的神经网络架构...",
        "references": [
            {
                "chunk_id": "b_BV1xx411c7mD_2",
                "video_id": "b_BV1xx411c7mD",
                "section_title": "核心算法讲解",
                "content": "Transformer 的核心是自注意力机制...",
                "start_time": 240,
                "end_time": 420,
                "relevance_score": 0.92
            }
        ],
        "token_usage": {
            "prompt_tokens": 1200,
            "completion_tokens": 350,
            "total_tokens": 1550
        }
    }
}
```

**流式响应（stream=true）：**

使用 SSE (Server-Sent Events) 格式：

```
event: token
data: {"token": "该", "finish_reason": null}

event: token
data: {"token": "视频", "finish_reason": null}

event: token
data: {"token": "中", "finish_reason": null}

...

event: done
data: {"references": [...], "token_usage": {...}}
```

### 4.2 跨视频知识库问答

在全部已处理视频的知识库中进行检索问答。

```
POST /api/v1/qa/ask-global
```

**请求体：**

```json
{
    "query": "什么是Transformer？",
    "stream": true,
    "top_k": 5,
    "video_ids": ["b_BV1xxx", "b_BV2yyy"]
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| query | string | 是 | - | 用户问题 |
| stream | boolean | 否 | true | 是否流式输出 |
| top_k | integer | 否 | 5 | 每个视频返回的片段数量 |
| video_ids | array[string] | 否 | - | 限定检索范围（不传则检索全部视频） |

**响应格式同单视频问答**，引用来源中的 `video_id` 和 `video_title` 会标明来自哪个视频。

---

## 5. 任务管理接口

### 5.1 获取任务状态

获取单个处理任务的实时状态。

```
GET /api/v1/tasks/{task_id}
```

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "task_id": "uuid-xxxx",
        "video_id": "b_BV1xx411c7mD",
        "type": "transcribe",
        "status": "running",
        "progress": 65,
        "error_message": null,
        "retry_count": 0,
        "started_at": "2026-06-30T12:00:00",
        "completed_at": null,
        "created_at": "2026-06-30T11:55:00"
    }
}
```

### 5.2 获取任务日志

获取处理任务的详细日志。

```
GET /api/v1/tasks/{task_id}/logs?level=WARN&page=1&page_size=50
```

**查询参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| level | string | 否 | - | 过滤级别: DEBUG/INFO/WARN/ERROR |
| page | integer | 否 | 1 | 页码 |
| page_size | integer | 否 | 50 | 每页条数 |

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "items": [
            {
                "level": "INFO",
                "message": "开始音频转写",
                "detail": "{\"audio_path\": \"...\", \"model\": \"medium\"}",
                "created_at": "2026-06-30T12:05:30"
            },
            {
                "level": "INFO",
                "message": "转写进度: 50%",
                "detail": "{\"processed_seconds\": 900, \"total_seconds\": 1800}",
                "created_at": "2026-06-30T12:10:00"
            }
        ],
        "total": 25,
        "page": 1,
        "page_size": 50
    }
}
```

### 5.3 重试失败任务

重试一个失败的处理任务。

```
POST /api/v1/tasks/{task_id}/retry
```

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "task_id": "uuid-xxxx",
        "status": "pending",
        "retry_count": 1
    }
}
```

---

## 6. WebSocket 实时进度

### 6.1 连接

```
WebSocket: ws://localhost:8000/api/v1/ws/task/{task_id}
```

### 6.2 消息格式

服务端推送消息：

```json
{
    "event": "progress",
    "data": {
        "task_id": "uuid-xxxx",
        "video_id": "b_BV1xx411c7mD",
        "type": "transcribe",
        "status": "running",
        "progress": 65,
        "message": "正在转写音频...（65%）"
    }
}
```

```json
{
    "event": "completed",
    "data": {
        "task_id": "uuid-xxxx",
        "video_id": "b_BV1xx411c7mD",
        "type": "transcribe",
        "status": "completed",
        "progress": 100,
        "message": "音频转写完成"
    }
}
```

```json
{
    "event": "error",
    "data": {
        "task_id": "uuid-xxxx",
        "video_id": "b_BV1xx411c7mD",
        "type": "transcribe",
        "status": "failed",
        "error_message": "Whisper 模型加载失败",
        "retryable": true
    }
}
```

---

## 7. 系统管理接口

### 7.1 获取系统配置

获取当前系统的配置信息（不包含敏感字段如 API Key）。

```
GET /api/v1/system/config
```

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "llm_provider": "tongyi",
        "llm_model": "qwen-plus",
        "transcriber_mode": "local",
        "whisper_model_size": "medium",
        "whisper_device": "auto",
        "embedding_model": "text-embedding-v3",
        "retrieval_top_k": 5,
        "data_dir": "./data",
        "video_retention": "processed"
    }
}
```

### 7.2 更新系统配置

更新系统运行时配置（临时生效，下次重启恢复 config.yaml 值）。

```
PUT /api/v1/system/config
```

**请求体：**

```json
{
    "llm_provider": "deepseek",
    "transcriber_mode": "bjian",
    "retrieval_top_k": 10
}
```

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "updated_fields": ["llm_provider", "transcriber_mode", "retrieval_top_k"]
    }
}
```

### 7.3 保存系统配置

将当前运行时配置持久化到 config.yaml。

```
POST /api/v1/system/config/save
```

**响应：**

```json
{
    "code": 0,
    "message": "配置已保存到 config.yaml",
    "data": {}
}
```

### 7.4 获取系统统计

```
GET /api/v1/system/stats
```

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "total_videos": 42,
        "completed_videos": 38,
        "total_notes": 38,
        "total_chunks": 570,
        "total_duration_hours": 380,
        "storage_usage_bytes": 1073741824,
        "disk_free_bytes": 53687091200
    }
}
```

### 7.5 检查系统健康

```
GET /api/v1/system/health
```

**响应：**

```json
{
    "code": 0,
    "message": "success",
    "data": {
        "status": "healthy",
        "database": "ok",
        "vector_store": "ok",
        "llm_api": "ok",
        "embedding_api": "ok",
        "disk_space": "ok",
        "uptime_seconds": 86400
    }
}
```

---

## 8. 数据模型定义

### 8.1 通用类型

```typescript
// VideoInfo - 视频基本信息
interface VideoInfo {
    id: number;
    video_id: string;
    title: string;
    uploader: string | null;
    duration_seconds: number | null;
    cover_url: string | null;
    status: VideoStatus;
    has_note: boolean;
    processed_at: string | null;
    created_at: string;
}

// VideoStatus - 视频处理状态
type VideoStatus =
    | "pending"
    | "downloading"
    | "transcribing"
    | "generating"
    | "storing"
    | "completed"
    | "failed";

// TaskInfo - 任务信息
interface TaskInfo {
    task_id: string;
    video_id: string;
    type: "download" | "transcribe" | "generate" | "store";
    status: "pending" | "running" | "completed" | "failed" | "retrying";
    progress: number;
    error_message: string | null;
    retry_count: number;
    started_at: string | null;
    completed_at: string | null;
    created_at: string;
}

// Reference - 引用来源
interface Reference {
    chunk_id: string;
    video_id: string;
    video_title?: string;
    section_title: string;
    content: string;
    start_time: number;
    end_time: number;
    relevance_score: number;
}

// QAAnswer - 问答结果
interface QAAnswer {
    answer: string;
    references: Reference[];
    token_usage?: {
        prompt_tokens: number;
        completion_tokens: number;
        total_tokens: number;
    };
}

// NoteSection - 笔记章节
interface NoteSection {
    title: string;
    start_time: number;
    end_time: number;
    content: string;
    chunk_index: number;
}
```

---

## 9. 接口速查表

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | /api/v1/videos/parse | 解析视频链接 | - |
| POST | /api/v1/videos/process | 提交视频处理 | - |
| GET | /api/v1/videos | 获取视频列表 | - |
| GET | /api/v1/videos/{video_id} | 获取视频详情 | - |
| DELETE | /api/v1/videos/{video_id} | 删除视频 | - |
| GET | /api/v1/notes/{video_id} | 获取笔记详情 | - |
| GET | /api/v1/notes/{video_id}/raw | 获取原始 Markdown | - |
| POST | /api/v1/qa/ask | 单视频问答 | - |
| POST | /api/v1/qa/ask-global | 跨视频问答 | - |
| GET | /api/v1/tasks/{task_id} | 获取任务状态 | - |
| GET | /api/v1/tasks/{task_id}/logs | 获取任务日志 | - |
| POST | /api/v1/tasks/{task_id}/retry | 重试失败任务 | - |
| WS | /api/v1/ws/task/{task_id} | 实时进度推送 | - |
| GET | /api/v1/system/config | 获取系统配置 | - |
| PUT | /api/v1/system/config | 更新配置 | - |
| POST | /api/v1/system/config/save | 保存配置 | - |
| GET | /api/v1/system/stats | 系统统计 | - |
| GET | /api/v1/system/health | 健康检查 | - |

---

*文档结束*
