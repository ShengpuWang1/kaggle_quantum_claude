"""Provider-neutral LLM calls with provider-specific conversation serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import AgentConfig


class ProviderError(RuntimeError):
    """Raised for a malformed or unsuccessful provider response."""


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderTurn:
    text: str
    tool_calls: list[ToolCall]
    assistant_message: dict[str, Any]
    stop_reason: str
    usage: dict[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
    ) -> ProviderTurn: ...

    def tool_result_messages(
        self, results: list[tuple[ToolCall, str, bool]]
    ) -> list[dict[str, Any]]: ...


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return value
    raise ProviderError(f"Cannot serialize provider value of type {type(value)!r}")


def _usage(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    return _dump(value)


class AnthropicProvider:
    def __init__(self, config: AgentConfig):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - dependency error path
            raise ProviderError("Install the anthropic package to use this role") from exc
        kwargs: dict[str, Any] = {
            "timeout": config.timeout_seconds,
            "max_retries": config.max_retries,
        }
        if config.auth_token or config.auth_token_env:
            kwargs["auth_token"] = config.require_auth_token()
        else:
            kwargs["api_key"] = config.require_api_key()
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self.client = anthropic.Anthropic(**kwargs)
        self.config = config

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
    ) -> ProviderTurn:
        request: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "system": system,
            "messages": messages,
            "thinking": {"type": "adaptive"},
        }
        if self.config.effort:
            request["output_config"] = {"effort": self.config.effort}
        if tools:
            request["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in tools
            ]
        request.update(self.config.options)
        if self.config.stream:
            with self.client.messages.stream(**request) as stream:
                response = stream.get_final_message()
        else:
            response = self.client.messages.create(**request)
        if response.stop_reason in {"max_tokens", "refusal"}:
            raise ProviderError(f"Anthropic response stopped with {response.stop_reason}")
        content = [_dump(block) for block in response.content]
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                if not isinstance(block.input, dict):
                    raise ProviderError("Anthropic tool input is not an object")
                calls.append(ToolCall(block.id, block.name, block.input))
        return ProviderTurn(
            text="\n".join(text_parts),
            tool_calls=calls,
            assistant_message={"role": "assistant", "content": content},
            stop_reason=response.stop_reason,
            usage=_usage(response.usage),
        )

    def tool_result_messages(
        self, results: list[tuple[ToolCall, str, bool]]
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": content,
                        "is_error": is_error,
                    }
                    for call, content, is_error in results
                ],
            }
        ]


class OpenAIProvider:
    """OpenAI Chat Completions, including compatible third-party endpoints."""

    def __init__(self, config: AgentConfig):
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - dependency error path
            raise ProviderError("Install the openai package to use this role") from exc
        kwargs: dict[str, Any] = {
            "api_key": config.require_api_key(),
            "timeout": config.timeout_seconds,
            "max_retries": config.max_retries,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self.client = openai.OpenAI(**kwargs)
        self.config = config

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
    ) -> ProviderTurn:
        request: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        if self.config.effort:
            request["reasoning_effort"] = self.config.effort
        if tools:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in tools
            ]
        request.update(self.config.options)
        response = self.client.chat.completions.create(**request)
        if not response.choices:
            raise ProviderError("OpenAI response contains no choices")
        choice = response.choices[0]
        if choice.finish_reason in {"length", "content_filter"}:
            raise ProviderError(f"OpenAI response stopped with {choice.finish_reason}")
        message = choice.message
        calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    f"Invalid JSON arguments for tool {call.function.name}"
                ) from exc
            if not isinstance(arguments, dict):
                raise ProviderError("OpenAI tool arguments are not an object")
            calls.append(ToolCall(call.id, call.function.name, arguments))
        content = message.content or ""
        if not isinstance(content, str):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            content = "".join(text_parts)
        return ProviderTurn(
            text=content,
            tool_calls=calls,
            assistant_message=_dump(message),
            stop_reason=choice.finish_reason or "stop",
            usage=_usage(response.usage),
        )

    def tool_result_messages(
        self, results: list[tuple[ToolCall, str, bool]]
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": ("ERROR: " if is_error else "") + content,
            }
            for call, content, is_error in results
        ]


class FakeProvider:
    """Deterministic scripted provider used by tests and offline demonstrations."""

    def __init__(self, config: AgentConfig):
        self.responses = list(config.options.get("responses", []))
        if not self.responses:
            raise ProviderError("fake provider requires options.responses")

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
    ) -> ProviderTurn:
        if not self.responses:
            raise ProviderError("fake provider script is exhausted")
        response = self.responses.pop(0)
        calls = [
            ToolCall(
                id=str(call.get("id", f"fake-{index}")),
                name=call["name"],
                arguments=call.get("arguments", {}),
            )
            for index, call in enumerate(response.get("tool_calls", []))
        ]
        return ProviderTurn(
            text=response.get("text", ""),
            tool_calls=calls,
            assistant_message={"role": "assistant", "content": response.get("text", "")},
            stop_reason=response.get("stop_reason", "end_turn"),
            usage={"fake": True},
        )

    def tool_result_messages(
        self, results: list[tuple[ToolCall, str, bool]]
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "user",
                "content": "\n".join(content for _, content, _ in results),
            }
        ]


def make_provider(config: AgentConfig) -> Provider:
    if config.provider == "anthropic":
        return AnthropicProvider(config)
    if config.provider == "openai":
        return OpenAIProvider(config)
    if config.provider == "fake":
        return FakeProvider(config)
    raise ProviderError(f"Unsupported provider: {config.provider}")
