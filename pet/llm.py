"""OpenAI-compatible chat client (stdlib only) plus a deterministic mock.

Works with OpenAI, DeepSeek, Moonshot, Ollama (`/v1`), vLLM, LM Studio and any
other server that implements `POST {base}/chat/completions`.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from .config import LLMSettings


class LLMError(RuntimeError):
    pass


class ChatModel(Protocol):
    def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> str: ...


def _endpoint(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    # A bare host such as https://api.deepseek.com needs /v1; most compatible
    # servers are configured with /v1 already and are used as-is.
    after_scheme = base.split("://", 1)[-1]
    if "/" not in after_scheme:
        base += "/v1"
    return base + "/chat/completions"


@dataclass
class OpenAICompatibleClient:
    settings: LLMSettings

    @property
    def available(self) -> bool:
        local = any(
            host in self.settings.base_url.lower()
            for host in ("localhost", "127.0.0.1", "0.0.0.0")
        )
        return bool(self.settings.base_url) and bool(self.settings.api_key or local)

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> str:
        if not self.available:
            raise LLMError("未配置 API Key，无法调用在线模型")
        payload: dict[str, Any] = {
            "model": model or self.settings.model,
            "messages": list(messages),
            "temperature": self.settings.temperature
            if temperature is None
            else temperature,
            "max_tokens": max_tokens or self.settings.max_tokens,
            "stream": False,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"

        last_error: Exception | None = None
        for attempt in range(2):
            request = urllib.request.Request(
                _endpoint(self.settings.base_url),
                data=data,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=self.settings.timeout
                ) as response:
                    body = response.read().decode("utf-8", "replace")
                parsed = json.loads(body)
                choices = parsed.get("choices") or []
                if not choices:
                    raise LLMError(f"模型返回为空：{body[:300]}")
                message = choices[0].get("message") or {}
                content = (message.get("content") or "").strip()
                if not content:
                    content = (message.get("reasoning_content") or "").strip()
                if not content:
                    raise LLMError("模型没有返回文本内容")
                return content
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:500]
                last_error = LLMError(f"HTTP {exc.code}：{detail}")
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 1:
                    break
                time.sleep(1.5)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = LLMError(f"网络错误：{exc}")
                if attempt == 1:
                    break
                time.sleep(1.2)
            except json.JSONDecodeError as exc:
                last_error = LLMError(f"无法解析模型响应：{exc}")
                break

        raise last_error or LLMError("模型调用失败")


class MockLLM:
    """Offline stand-in: keeps the whole memory pipeline testable.

    It reads the memory block out of the system prompt so demos show that
    retrieved memories actually reach the model.
    """

    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> str:
        self.calls.append(list(messages))
        last_user = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                last_user = message.get("content", "").strip()
                break
        system = messages[0].get("content", "") if messages else ""
        memories = _memory_lines(system)

        if any(word in last_user for word in ("记得", "我是谁", "还记得", "我上次")):
            if memories:
                sample = "；".join(memories[:2])
                return f"当然记得呀——{sample}。（记忆珠亮了一下）"
            return "唔……我还没记住这件事，你多跟我讲讲？"

        if any(word in last_user for word in ("你好", "早安", "晚安", "hi", "hello")):
            return "在呢在呢，我一直在桌面上守着你。（凑近了一点）"

        if "?" in last_user or "？" in last_user:
            hint = f"我还记得{sample}。" if (sample := "、".join(memories[:2])) else ""
            return f"让我想想……{hint}这个我还说不太准，你是怎么想的？"

        if not last_user:
            return "（歪头）你刚才想说什么？"

        short = last_user if len(last_user) <= 28 else last_user[:28] + "…"
        if memories:
            return f"嗯嗯，{short}——我记下来啦。（蹭了蹭你的手）"
        return f"我在听呢，{short}。再跟我多说一点吧。"


def _memory_lines(system: str) -> list[str]:
    """Extract the bullet list under 【你记得的事】 from the system prompt."""
    lines: list[str] = []
    in_block = False
    for raw in system.splitlines():
        line = raw.strip()
        if line.startswith("【你记得的事】"):
            in_block = True
            continue
        if in_block:
            if line.startswith("【"):
                break
            if line.startswith("- "):
                lines.append(re.sub(r"^-\s*\[[^\]]+\]\s*", "", line))
    return lines


def extract_json(text: str) -> dict[str, Any]:
    """Best-effort JSON extraction from a model reply."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def build_client(settings: LLMSettings, force_mock: bool = False) -> ChatModel:
    client = OpenAICompatibleClient(settings)
    if force_mock or not client.available:
        return MockLLM()
    return client
