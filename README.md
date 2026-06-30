# VideoNote - 视频知识沉淀与智能问答系统

基于大语言模型的视频知识沉淀与智能问答 Web 系统。

## 功能

- 输入 B 站链接，自动下载 -> 转写 -> 生成结构化笔记
- 单视频精准问答
- 跨视频知识库检索问答

## 快速开始

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

详细说明见 [环境搭建与快速启动指南](docs/环境搭建与快速启动指南.md)。
