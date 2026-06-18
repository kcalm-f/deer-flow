"""Tests for provider tool-call argument sanitization."""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from deerflow.models.tool_call_sanitizer import (
    normalize_function_arguments,
    repair_invalid_tool_calls,
    sanitize_langchain_messages,
    sanitize_model_request,
    sanitize_openai_messages,
)


def test_normalize_function_arguments_repairs_extra_closing_bracket():
    raw = '{"phase":"discovery","content":{"rejected_alternatives":"未选择省级下钻，因用户未指定省份"}]}'

    assert normalize_function_arguments(raw) == ('{"phase":"discovery","content":{"rejected_alternatives":"未选择省级下钻，因用户未指定省份"}}')


def test_sanitize_openai_messages_drops_unrepairable_tool_call():
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "bad-call",
                    "type": "function",
                    "function": {"name": "record_reasoning", "arguments": '{"phase": '},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "bad-call", "content": "orphan"},
    ]

    sanitized = sanitize_openai_messages(messages)

    assert sanitized == [{"role": "assistant", "content": ""}]


def test_repair_invalid_tool_calls_promotes_repairable_call():
    msg = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "type": "invalid_tool_call",
                "id": "call_record",
                "name": "record_reasoning",
                "args": '{"phase":"discovery","content":{"decision":"ok"}]}',
                "error": None,
            }
        ],
    )

    repaired = repair_invalid_tool_calls(msg)

    assert repaired.invalid_tool_calls == []
    assert repaired.tool_calls == [
        {
            "name": "record_reasoning",
            "args": {"phase": "discovery", "content": {"decision": "ok"}},
            "id": "call_record",
            "type": "tool_call",
        }
    ]


def test_sanitize_langchain_messages_clears_invalid_tool_calls_from_history():
    msg = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "type": "invalid_tool_call",
                "id": "bad",
                "name": "record_reasoning",
                "args": '{"phase": ',
                "error": "parse failed",
            }
        ],
    )

    sanitized = sanitize_langchain_messages([msg])

    assert sanitized[0].invalid_tool_calls == []


def test_sanitize_model_request_adds_hidden_feedback_for_unrepairable_invalid_call():
    request = SimpleNamespace(
        messages=[
            AIMessage(
                content="",
                invalid_tool_calls=[
                    {
                        "type": "invalid_tool_call",
                        "id": "bad",
                        "name": "record_reasoning",
                        "args": '{"phase": ',
                        "error": "Failed to parse tool arguments",
                    }
                ],
            )
        ]
    )

    sanitize_model_request(request)

    assert request.messages[0].invalid_tool_calls == []
    assert isinstance(request.messages[1], HumanMessage)
    assert request.messages[1].name == "tool_call_argument_feedback"
    assert request.messages[1].additional_kwargs["hide_from_ui"] is True
    assert "record_reasoning (bad)" in request.messages[1].content
    assert "strict JSON object" in request.messages[1].content
