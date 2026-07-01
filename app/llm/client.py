# app/llm/client.py
import httpx
import json
import asyncio
from typing import AsyncGenerator, Optional
from abc import ABC, abstractmethod
from loguru import logger
from app.core.config import settings


class LLMClient(ABC):
    """LLM 客户端抽象基类"""
    @abstractmethod
    async def chat(self, messages: list[dict], temperature: float = 0.1) -> str:
        """非流式调用，返回完整回复"""
        pass

    @abstractmethod
    async def stream_chat(self, messages: list[dict], temperature: float = 0.3) -> AsyncGenerator[str, None]:
        """流式调用，逐 token 生成"""
        pass


class TongyiClient(LLMClient):
    """通义千问客户端（支持流式）"""

    def __init__(self, api_key: str, model: str = "qwen-plus"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"

    async def chat(self, messages: list[dict], temperature: float = 0.1) -> str:
        """非流式调用"""
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "input": {"messages": messages},
                    "parameters": {"temperature": temperature, "result_format": "message"}
                }
            )
            resp.raise_for_status()
            data = resp.json()
            return data["output"]["choices"][0]["message"]["content"]

    async def stream_chat(self, messages: list[dict], temperature: float = 0.3) -> AsyncGenerator[str, None]:
        """
        流式调用通义千问
        使用 SSE (Server-Sent Events) 协议，逐词返回
        """
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream"  # 明确告知期望流式
                },
                json={
                    "model": self.model,
                    "input": {"messages": messages},
                    "parameters": {
                        "temperature": temperature,
                        "result_format": "message",
                        "incremental_output": True  # 关键：启用增量输出
                    }
                }
            ) as response:
                response.raise_for_status()
                # 逐行读取 SSE 响应
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    # 处理 data: 开头的行
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        # 通义可能发送 [DONE] 结束
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            # 提取增量内容
                            if "output" in data and "choices" in data["output"]:
                                choice = data["output"]["choices"][0]
                                # 通义流式返回的 content 字段
                                delta = choice.get("message", {}).get("content")
                                if delta:
                                    yield delta
                            # 兼容某些版本可能直接返回 text
                            elif "text" in data:
                                if data["text"]:
                                    yield data["text"]
                        except json.JSONDecodeError as e:
                            # 如果某行不是有效 JSON，记录并跳过（防止中断）
                            logger.warning(f"通义流式 JSON 解析失败: {data_str}, 错误: {e}")
                            continue


class DeepSeekClient(LLMClient):
    """DeepSeek 客户端（OpenAI 兼容接口）"""

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.deepseek.com/v1/chat/completions"

    async def chat(self, messages: list[dict], temperature: float = 0.1) -> str:
        """非流式调用"""
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages, "temperature": temperature, "stream": False}
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def stream_chat(self, messages: list[dict], temperature: float = 0.3) -> AsyncGenerator[str, None]:
        """流式调用（OpenAI 格式）"""
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages, "temperature": temperature, "stream": True}
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                        except json.JSONDecodeError as e:
                            logger.warning(f"DeepSeek 流式 JSON 解析失败: {data_str}, 错误: {e}")
                            continue


def get_llm_client() -> LLMClient:
    """工厂函数，根据配置返回对应的 LLM 客户端"""
    provider = settings.llm_provider
    if provider == "tongyi":
        return TongyiClient(settings.tongyi_api_key, settings.tongyi_model)
    elif provider == "deepseek":
        return DeepSeekClient(settings.deepseek_api_key, settings.deepseek_model)
    else:
        raise ValueError(f"不支持的 LLM 提供商: {provider}")