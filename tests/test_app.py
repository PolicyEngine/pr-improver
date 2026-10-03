import json
from unittest.mock import MagicMock

import anthropic
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import app

try:
    import httpx2 as httpx
except ImportError:
    import httpx
else:
    # Older supported SDKs use httpx, even if httpx2 is also installed.
    if not issubclass(anthropic.DefaultHttpxClient, httpx.Client):
        import httpx

DIFF = "diff --git a/rates.py b/rates.py\n+rate = 0.2\n"
GUIDELINES = "Use descriptive variable names."
ADDITIONAL_INFO = "See 26 USC 32 for the credit rate."
TOKENS = st.integers(min_value=0, max_value=2_000_000)


def mock_client(status_code, response_body, sent_bodies):
    """Real SDK client whose HTTP requests are recorded and answered locally."""

    def handler(request):
        sent_bodies.append(json.loads(request.content))
        return httpx.Response(status_code, json=response_body)

    return anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def message(content, stop_reason, **fields):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": app.CLAUDE_MODEL,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1_234, "output_tokens": 567},
        **fields,
    }


def get_suggestions(monkeypatch, status_code, response_body):
    sent_bodies = []
    monkeypatch.setattr(
        app, "client", mock_client(status_code, response_body, sent_bodies)
    )
    result = app.get_claude_suggestions(DIFF, GUIDELINES, ADDITIONAL_INFO)
    return result, sent_bodies


def test_request_is_valid_for_claude_sonnet_5_5(monkeypatch):
    _, sent_bodies = get_suggestions(
        monkeypatch, 200, message([{"type": "text", "text": "Hi"}], "end_turn")
    )

    (body,) = sent_bodies
    assert body["model"] == "claude-sonnet-5-5"
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"] == {"effort": "low"}
    # Thinking counts toward max_tokens, so leave room beyond the reply.
    assert body["max_tokens"] >= 16_000
    # Claude Sonnet 5.5 rejects non-default sampling parameters and
    # disabled thinking, and the API rejects assistant prefill.
    assert not {
        "temperature", "top_p", "top_k", "tool_choice"
    } & body.keys()
    assert [m["role"] for m in body["messages"]] == ["user"]
    # The prompt sent is the prompt shown in "View Generated Prompt".
    assert body["messages"][0]["content"] == app.generate_prompt(
        DIFF, GUIDELINES, ADDITIONAL_INFO
    )


def test_reads_only_text_blocks(monkeypatch):
    content = [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "1. Rename `rate`."},
        {"type": "text", "text": "\n2. Cite the statute."},
    ]
    (suggestions, prompt, usage), _ = get_suggestions(
        monkeypatch, 200, message(content, "end_turn")
    )

    assert suggestions == "1. Rename `rate`.\n2. Cite the statute."
    assert prompt == app.generate_prompt(DIFF, GUIDELINES, ADDITIONAL_INFO)
    assert (usage.input_tokens, usage.output_tokens) == (1_234, 567)


def test_refusal_is_reported_as_failure(monkeypatch):
    refusal = message(
        [],
        "refusal",
        stop_details={
            "type": "refusal",
            "category": "cyber",
            "explanation": None,
        },
    )
    (suggestions, _, usage), _ = get_suggestions(monkeypatch, 200, refusal)

    assert suggestions == (
        "Failed to get suggestions: Claude declined this request."
    )
    assert usage is None


def test_api_error_is_reported_as_failure(monkeypatch):
    error = {
        "type": "error",
        "error": {"type": "not_found_error", "message": "model not found"},
    }
    (suggestions, _, usage), _ = get_suggestions(monkeypatch, 404, error)

    assert suggestions.startswith("Failed to get suggestions:")
    assert "model not found" in suggestions
    assert usage is None


class SessionState(dict):
    """Attribute access used by Streamlit's session state in main()."""

    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def run_main(monkeypatch, status_code, response_body):
    """Exercise the UI with local SDK responses and no external lookups."""
    ui = MagicMock()
    ui.session_state = SessionState()
    ui.secrets = {"GITHUB_TOKEN": "test-token"}
    ui.text_input.return_value = "https://github.com/PolicyEngine/repo/pull/1"
    ui.text_area.return_value = ADDITIONAL_INFO
    ui.button.return_value = True
    monkeypatch.setattr(app, "st", ui)
    monkeypatch.setattr(app, "get_github_diff", lambda *args: DIFF)
    monkeypatch.setattr(
        app, "get_contributor_guidelines", lambda *args: GUIDELINES
    )
    # Avoid downloading tiktoken's encoding; only the preflight estimate
    # should use this approximate count.
    estimate_tokens = MagicMock(return_value=100)
    monkeypatch.setattr(app, "estimate_token_count", estimate_tokens)
    monkeypatch.setattr(
        app, "client", mock_client(status_code, response_body, [])
    )

    app.main()

    return ui, estimate_tokens


def test_ui_displays_billed_usage_including_hidden_thinking(monkeypatch):
    suggestions = "1. Rename `rate`."
    ui, estimate_tokens = run_main(
        monkeypatch,
        200,
        message(
            [
                {"type": "thinking", "thinking": "Hidden", "signature": "sig"},
                {"type": "text", "text": suggestions},
            ],
            "end_turn",
        ),
    )

    ui.markdown.assert_called_once_with(suggestions)
    ui.button.assert_called_once_with("Analyze PR (estimated cost: 16.0 cents)")
    ui.info.assert_called_once_with(
        "This analysis cost 0.8 cents "
        "(1,234 input tokens and 567 output tokens)"
    )
    ui.error.assert_not_called()
    assert ui.session_state.suggestions == suggestions
    # Billed output includes thinking; retokenizing the visible reply
    # would understate its cost.
    estimate_tokens.assert_called_once_with(
        app.generate_prompt(DIFF, GUIDELINES, ADDITIONAL_INFO)
    )


@pytest.mark.parametrize(
    "status_code,response_body,error_text",
    [
        (
            200,
            message([], "refusal"),
            "Claude declined this request.",
        ),
        (
            404,
            {
                "type": "error",
                "error": {
                    "type": "not_found_error", "message": "model not found"
                },
            },
            "model not found",
        ),
    ],
)
def test_ui_reports_failures_without_suggestions_or_cost(
    monkeypatch, status_code, response_body, error_text
):
    ui, _ = run_main(monkeypatch, status_code, response_body)

    ui.error.assert_called_once()
    assert error_text in ui.error.call_args.args[0]
    ui.markdown.assert_not_called()
    ui.subheader.assert_not_called()
    ui.info.assert_not_called()
    assert ui.session_state.suggestions == ""


def test_prompt_has_no_text_completions_markers():
    prompt = app.generate_prompt(DIFF, GUIDELINES, ADDITIONAL_INFO)

    assert "Human:" not in prompt
    assert "Assistant:" not in prompt
    assert prompt.startswith("You are an AI assistant")
    for part in (DIFF, GUIDELINES, ADDITIONAL_INFO):
        assert part in prompt


def test_prices_are_claude_sonnet_5_5_rates():
    assert app.estimate_cost(1_000_000, 0) == pytest.approx(2.0)
    assert app.estimate_cost(0, 1_000_000) == pytest.approx(10.0)


@settings(deadline=None)
@given(TOKENS, TOKENS)
def test_cost_is_nonnegative(input_tokens, output_tokens):
    assert app.estimate_cost(input_tokens, output_tokens) >= 0


@settings(deadline=None)
@given(TOKENS, TOKENS, TOKENS, TOKENS)
def test_cost_is_additive(input_a, output_a, input_b, output_b):
    assert app.estimate_cost(
        input_a + input_b, output_a + output_b
    ) == pytest.approx(
        app.estimate_cost(input_a, output_a)
        + app.estimate_cost(input_b, output_b)
    )


@settings(deadline=None)
@given(TOKENS, st.integers(min_value=0, max_value=app.MAX_TOKENS))
def test_max_tokens_estimate_bounds_billed_output(input_tokens, output_tokens):
    # For a fixed input count, the full output budget bounds output cost;
    # the app's approximate input count makes its total only an estimate.
    assert app.estimate_cost(input_tokens, output_tokens) <= app.estimate_cost(
        input_tokens, app.MAX_TOKENS
    )
