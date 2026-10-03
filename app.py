import streamlit as st
import requests
import anthropic
import tiktoken

client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
CLAUDE_MODEL = "claude-sonnet-5-5"
# Thinking tokens count toward max_tokens and are billed as output tokens.
MAX_TOKENS = 16_000
# Claude Sonnet 5.5 prices in USD per million tokens.
INPUT_PRICE_PER_MILLION_TOKENS = 2
OUTPUT_PRICE_PER_MILLION_TOKENS = 10


def get_claude_suggestions(diff, guidelines, additional_info):
    prompt = generate_prompt(diff, guidelines, additional_info)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        return f"Failed to get suggestions: {str(e)}", prompt, None

    if response.stop_reason == "refusal":
        return (
            "Failed to get suggestions: Claude declined this request.",
            prompt,
            None,
        )

    # Responses can include thinking blocks, so read only the text blocks.
    suggestions = "".join(
        block.text for block in response.content if block.type == "text"
    )
    return suggestions, prompt, response.usage


def get_github_diff(owner, repo, pull_number, token):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff",
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.text
    else:
        st.error(f"Error fetching GitHub diff: {response.status_code}")
        return None


def get_contributor_guidelines(owner, repo, token):
    url = (
        f"https://api.github.com/repos/{owner}/{repo}/contents/CONTRIBUTING.md"
    )
    headers = {"Authorization": f"token {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        content = response.json()
        return requests.get(content["download_url"]).text
    else:
        st.error(
            f"Error fetching contributor guidelines: {response.status_code}"
        )
        return None


def estimate_token_count(text):
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def estimate_cost(input_tokens, output_tokens):
    input_cost = (input_tokens / 1_000_000) * INPUT_PRICE_PER_MILLION_TOKENS
    output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_MILLION_TOKENS
    return input_cost + output_cost


def generate_prompt(diff, guidelines, additional_info):
    return f"""You are an AI assistant providing specific suggestions for code improvements.
    Analyze this code diff:
    {diff}

    Consider these contributor guidelines:
    {guidelines}

    Additional context and information:
    {additional_info}

    Please provide 5-7 specific, actionable suggestions to improve this PR. Focus on:
    1. Clearer Python variable names (especially for non-native English speakers)
    2. More descriptive comments
    3. Improved code structure and readability
    4. Better test coverage or edge case handling

    For each suggestion:
    - Specify the file and line number(s) where the change should be made
    - Provide the exact code snippet to be changed
    - Explain why the change improves the code

    Do not comment on formatting or test coverage checks, which CI/CD will handle."""


def main():
    st.title("GitHub PR Reviewer")

    # Initialize session state
    if "suggestions" not in st.session_state:
        st.session_state.suggestions = ""
    if "prompt" not in st.session_state:
        st.session_state.prompt = ""
    if "estimated_cost" not in st.session_state:
        st.session_state.estimated_cost = 0

    pr_url = st.text_input("Enter the GitHub Pull Request URL")
    additional_info = st.text_area(
        "Enter additional information (e.g., relevant laws, tax forms, other feedback)",
        height=150,
        key="additional_info",
    )

    # Generate prompt and estimate cost in real-time
    if pr_url:
        github_token = st.secrets["GITHUB_TOKEN"]
        repo_info = pr_url.split("github.com/")[1].split("/pull/")
        repo = repo_info[0]
        pull_number = repo_info[1]
        owner, repo_name = repo.split("/")

        diff = get_github_diff(owner, repo_name, pull_number, github_token)
        guidelines = get_contributor_guidelines(owner, repo_name, github_token)

        if diff and guidelines:
            prompt = generate_prompt(diff, guidelines, additional_info)
            st.session_state.prompt = prompt

            estimated_input_tokens = estimate_token_count(prompt)
            estimated_output_tokens = MAX_TOKENS  # Max tokens in the API call
            st.session_state.estimated_cost = estimate_cost(
                estimated_input_tokens, estimated_output_tokens
            )

            with st.expander("View Generated Prompt"):
                st.code(prompt, language="markdown")

    # Update button text with estimated cost
    button_text = "Analyze PR"
    if st.session_state.estimated_cost > 0:
        button_text += (
            f" (costs up to {st.session_state.estimated_cost*100:.1f} cents)"
        )

    if st.button(button_text):
        if pr_url and "github.com/policyengine" in pr_url.lower():
            with st.spinner("Analyzing PR..."):
                suggestions, _, usage = get_claude_suggestions(
                    diff, guidelines, additional_info
                )

                if usage is None:
                    st.error(suggestions)
                elif suggestions:
                    st.session_state.suggestions = suggestions

                    st.subheader("Improvement Suggestions:")
                    st.markdown(suggestions)

                    with st.expander("View Copyable Suggestions"):
                        st.code(suggestions, language="markdown")

                    # Display the billed token counts and cost; output
                    # tokens include any thinking tokens.
                    input_tokens = usage.input_tokens
                    output_tokens = usage.output_tokens
                    actual_cost = estimate_cost(input_tokens, output_tokens)

                    st.info(
                        f"This analysis cost {actual_cost*100:.1f} cents "
                        f"({input_tokens:,} input tokens and {output_tokens:,} output tokens)"
                    )
                else:
                    st.error("Failed to generate suggestions.")
        else:
            st.error(
                "This tool only analyzes PolicyEngine GitHub repositories."
            )

    st.sidebar.markdown("### About")
    st.sidebar.info(
        "This tool uses Claude AI to analyze GitHub Pull Requests "
        "and provide suggestions for code improvements. It's designed "
        "specifically for PolicyEngine repositories."
    )


if __name__ == "__main__":
    main()
