# pr-improver
AI suggestions on improving pull requests

The Streamlit app uses `claude-sonnet-5-5` with adaptive thinking, low effort,
and a 16,000-token output budget, including thinking tokens. Cost estimates
use $2 per million input tokens and $10 per million output tokens. The
pre-analysis estimate uses an approximate input token count and the full
output budget; the cost shown after a successful analysis uses the API's
reported token usage. The button labels the approximate amount as an
estimated cost.

Install dependencies with `uv pip install -r requirements.txt` in a virtual
environment, configure `ANTHROPIC_API_KEY` and `GITHUB_TOKEN` in Streamlit
secrets, and run `streamlit run app.py`. The model is set in `app.py` and has no
environment-variable override.

For offline tests, install `requirements-dev.txt` and run `python -m pytest -q`.
Tests use dummy credentials and mocked HTTP responses; no provider calls are
needed.
