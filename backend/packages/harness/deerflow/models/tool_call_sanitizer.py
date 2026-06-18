"""Helpers for keeping OpenAI-compatible tool-call payloads valid."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

logger = logging.getLogger(__name__)

_FEEDBACK_MESSAGE_NAME = "tool_call_argument_feedback"


@dataclass(frozen=True)
class ToolCallSanitizationNotice:
    """Description of a malformed tool call removed from model history."""

    name: str
    tool_call_id: str | None
    reason: str


def normalize_function_arguments(arguments: Any) -> str | None:
    """Return a JSON-object string for OpenAI ``function.arguments``.

    OpenAI-compatible gateways are strict about assistant history: every
    ``function.arguments`` value must be JSON. Models occasionally emit a
    nearly-valid object with one extra or missing delimiter. We repair only
    delimiter balance outside strings, then require the result to decode to an
    object. Anything more ambiguous is rejected.
    """
    if isinstance(arguments, dict):
        return json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
    if not isinstance(arguments, str):
        return None

    parsed = _parse_json_object(arguments)
    if parsed is not None:
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))

    repaired = _repair_json_delimiters(arguments)
    if repaired == arguments:
        return None

    parsed = _parse_json_object(repaired)
    if parsed is None:
        return None
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


def sanitize_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize OpenAI-format messages before they are sent to a provider."""
    dropped_ids: set[str] = set()
    sanitized: list[dict[str, Any]] = []

    for message in messages:
        if message.get("role") == "tool" and message.get("tool_call_id") in dropped_ids:
            continue

        if message.get("role") != "assistant":
            sanitized.append(message)
            continue

        updated = dict(message)
        tool_calls = updated.get("tool_calls")
        if isinstance(tool_calls, list):
            kept_calls = []
            for tool_call in tool_calls:
                normalized = _sanitize_openai_tool_call(tool_call)
                if normalized is None:
                    tool_call_id = tool_call.get("id") if isinstance(tool_call, dict) else None
                    if isinstance(tool_call_id, str) and tool_call_id:
                        dropped_ids.add(tool_call_id)
                    logger.warning("Dropping malformed assistant tool call before provider request: %r", tool_call)
                    continue
                kept_calls.append(normalized)

            if kept_calls:
                updated["tool_calls"] = kept_calls
            else:
                updated.pop("tool_calls", None)
                if updated.get("content") is None:
                    updated["content"] = ""

        sanitized.append(updated)

    return sanitized


def sanitize_langchain_messages(messages: list[Any], *, inject_feedback: bool = False) -> list[Any]:
    """Remove invalid/raw malformed tool-call metadata from LangChain messages."""
    sanitized_messages: list[Any] = []
    notices: list[ToolCallSanitizationNotice] = []

    for message in messages:
        sanitized_message, message_notices = _sanitize_langchain_message(message)
        sanitized_messages.append(sanitized_message)
        notices.extend(message_notices)

    if inject_feedback and notices and not _has_feedback_message(sanitized_messages):
        sanitized_messages.append(_build_feedback_message(notices))

    return sanitized_messages


def repair_invalid_tool_calls(message: Any) -> Any:
    """Promote repairable ``invalid_tool_calls`` on an AIMessage to tool calls."""
    if not isinstance(message, AIMessage):
        return message

    invalid_tool_calls = list(getattr(message, "invalid_tool_calls", None) or [])
    if not invalid_tool_calls:
        return message

    repaired_tool_calls: list[dict[str, Any]] = []
    remaining_invalid: list[Any] = []
    for invalid_tool_call in invalid_tool_calls:
        repaired = _repair_invalid_tool_call(invalid_tool_call)
        if repaired is None:
            remaining_invalid.append(invalid_tool_call)
            continue
        repaired_tool_calls.append(repaired)

    if not repaired_tool_calls:
        return message

    logger.warning("Repaired %d malformed assistant tool call(s)", len(repaired_tool_calls))
    return message.model_copy(
        update={
            "tool_calls": [*(getattr(message, "tool_calls", None) or []), *repaired_tool_calls],
            "invalid_tool_calls": remaining_invalid,
        }
    )


def sanitize_model_request(request: Any) -> Any:
    """Sanitize a LangChain ModelRequest in place and return it."""
    messages = getattr(request, "messages", None)
    if isinstance(messages, list):
        request.messages = sanitize_langchain_messages(messages, inject_feedback=True)
    return request


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _repair_json_delimiters(text: str) -> str:
    stack: list[str] = []
    chars: list[str] = []
    in_string = False
    escaped = False
    pairs = {"{": "}", "[": "]"}
    openers = set(pairs)
    closers = {value: key for key, value in pairs.items()}

    for char in text.strip():
        chars.append(char)

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char in openers:
            stack.append(char)
            continue

        if char in closers:
            if stack and stack[-1] == closers[char]:
                stack.pop()
            else:
                chars.pop()

    if in_string:
        return text

    while stack:
        chars.append(pairs[stack.pop()])

    return "".join(chars)


def _sanitize_openai_tool_call(tool_call: Any) -> dict[str, Any] | None:
    if not isinstance(tool_call, dict):
        return None

    function = tool_call.get("function")
    if not isinstance(function, dict):
        return None

    normalized_args = normalize_function_arguments(function.get("arguments", "{}"))
    if normalized_args is None:
        return None

    sanitized = dict(tool_call)
    sanitized_function = dict(function)
    sanitized_function["arguments"] = normalized_args
    sanitized["function"] = sanitized_function
    return sanitized


def _sanitize_raw_tool_call(tool_call: Any) -> dict[str, Any] | None:
    return _sanitize_openai_tool_call(tool_call)


def _sanitize_function_call(function_call: Any) -> dict[str, Any] | None:
    if not isinstance(function_call, dict):
        return None
    normalized_args = normalize_function_arguments(function_call.get("arguments", "{}"))
    if normalized_args is None:
        return None
    sanitized = dict(function_call)
    sanitized["arguments"] = normalized_args
    return sanitized


def _repair_invalid_tool_call(invalid_tool_call: Any) -> dict[str, Any] | None:
    if not isinstance(invalid_tool_call, dict):
        return None

    name = invalid_tool_call.get("name")
    if not isinstance(name, str) or not name:
        return None

    normalized_args = normalize_function_arguments(invalid_tool_call.get("args", "{}"))
    if normalized_args is None:
        return None

    try:
        parsed_args = json.loads(normalized_args)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_args, dict):
        return None

    repaired = {
        "name": name,
        "args": parsed_args,
        "id": invalid_tool_call.get("id") or "",
        "type": "tool_call",
    }
    return repaired


def _sanitize_langchain_message(message: Any) -> tuple[Any, list[ToolCallSanitizationNotice]]:
    if not isinstance(message, AIMessage):
        return message, []

    additional_kwargs = dict(getattr(message, "additional_kwargs", {}) or {})
    changed = False
    notices: list[ToolCallSanitizationNotice] = []

    raw_tool_calls = additional_kwargs.get("tool_calls")
    if isinstance(raw_tool_calls, list):
        sanitized_raw_calls = []
        for raw_tool_call in raw_tool_calls:
            sanitized = _sanitize_raw_tool_call(raw_tool_call)
            if sanitized is None:
                changed = True
                logger.warning("Dropping malformed raw assistant tool call from message history: %r", raw_tool_call)
                notices.append(_notice_from_openai_tool_call(raw_tool_call, "raw tool call arguments were not a JSON object"))
                continue
            sanitized_raw_calls.append(sanitized)
            if sanitized != raw_tool_call:
                changed = True

        if sanitized_raw_calls:
            additional_kwargs["tool_calls"] = sanitized_raw_calls
        else:
            additional_kwargs.pop("tool_calls", None)
            changed = True

    function_call = additional_kwargs.get("function_call")
    if function_call is not None:
        sanitized_function_call = _sanitize_function_call(function_call)
        if sanitized_function_call is None:
            additional_kwargs.pop("function_call", None)
            changed = True
            notices.append(_notice_from_function_call(function_call, "legacy function_call arguments were not a JSON object"))
        elif sanitized_function_call != function_call:
            additional_kwargs["function_call"] = sanitized_function_call
            changed = True

    invalid_tool_calls = getattr(message, "invalid_tool_calls", None) or []
    if invalid_tool_calls:
        changed = True
        for invalid_tool_call in invalid_tool_calls:
            notices.append(_notice_from_invalid_tool_call(invalid_tool_call))

    if not changed:
        return message, []

    sanitized_message = message.model_copy(update={"additional_kwargs": additional_kwargs, "invalid_tool_calls": []})
    return sanitized_message, notices


def _notice_from_invalid_tool_call(invalid_tool_call: Any) -> ToolCallSanitizationNotice:
    if not isinstance(invalid_tool_call, dict):
        return ToolCallSanitizationNotice(name="unknown", tool_call_id=None, reason="invalid tool call was not a mapping")

    name = invalid_tool_call.get("name")
    tool_call_id = invalid_tool_call.get("id")
    error = invalid_tool_call.get("error")
    return ToolCallSanitizationNotice(
        name=name if isinstance(name, str) and name else "unknown",
        tool_call_id=tool_call_id if isinstance(tool_call_id, str) and tool_call_id else None,
        reason=str(error) if error else "tool call arguments were not valid JSON",
    )


def _notice_from_openai_tool_call(tool_call: Any, reason: str) -> ToolCallSanitizationNotice:
    if not isinstance(tool_call, dict):
        return ToolCallSanitizationNotice(name="unknown", tool_call_id=None, reason=reason)

    function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
    name = function.get("name") if isinstance(function, dict) else None
    tool_call_id = tool_call.get("id")
    return ToolCallSanitizationNotice(
        name=name if isinstance(name, str) and name else "unknown",
        tool_call_id=tool_call_id if isinstance(tool_call_id, str) and tool_call_id else None,
        reason=reason,
    )


def _notice_from_function_call(function_call: Any, reason: str) -> ToolCallSanitizationNotice:
    if not isinstance(function_call, dict):
        return ToolCallSanitizationNotice(name="unknown", tool_call_id=None, reason=reason)

    name = function_call.get("name")
    return ToolCallSanitizationNotice(
        name=name if isinstance(name, str) and name else "unknown",
        tool_call_id=None,
        reason=reason,
    )


def _has_feedback_message(messages: list[Any]) -> bool:
    return any(isinstance(message, HumanMessage) and message.name == _FEEDBACK_MESSAGE_NAME for message in messages)


def _build_feedback_message(notices: list[ToolCallSanitizationNotice]) -> HumanMessage:
    unique: list[ToolCallSanitizationNotice] = []
    seen: set[tuple[str, str | None, str]] = set()
    for notice in notices:
        key = (notice.name, notice.tool_call_id, notice.reason)
        if key in seen:
            continue
        seen.add(key)
        unique.append(notice)

    lines = [
        "<system-reminder>",
        "Previous assistant tool-call arguments failed validation and were not executed.",
        "Regenerate the affected tool call with function.arguments as a strict JSON object. Do not reuse malformed arguments.",
    ]
    for notice in unique[:5]:
        call_ref = f"{notice.name} ({notice.tool_call_id})" if notice.tool_call_id else notice.name
        lines.append(f"- {call_ref}: {notice.reason}")
    if len(unique) > 5:
        lines.append(f"- plus {len(unique) - 5} more malformed tool call(s)")
    lines.append("</system-reminder>")

    return HumanMessage(
        content="\n".join(lines),
        name=_FEEDBACK_MESSAGE_NAME,
        additional_kwargs={
            "hide_from_ui": True,
            "tool_call_sanitization_feedback": True,
            "notice_count": len(unique),
        },
    )
