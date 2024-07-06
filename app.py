import streamlit as st
import requests
import anthropic
import pyperclip
from custom_components import copy_button

import tiktoken

client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
CLAUDE_MODEL = "claude-3-5-sonnet-20240620"


def get_claude_suggestions(diff, guidelines, additional_info):
    prompt = f"""{anthropic.HUMAN_PROMPT} You are an AI assistant providing specific suggestions for code improvements. 
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

    Do not comment on formatting or test coverage checks, which CI/CD will handle.

    {anthropic.AI_PROMPT}"""

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1_000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text, prompt
    except Exception as e:
        return f"Failed to get suggestions: {str(e)}", prompt


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
    input_cost = (input_tokens / 1_000_000) * 3
    output_cost = (output_tokens / 1_000_000) * 15
    return input_cost + output_cost


def main():
    st.title("PolicyEngine GitHub PR Reviewer")

    # Initialize session state
    if "suggestions" not in st.session_state:
        st.session_state.suggestions = ""
    if "prompt" not in st.session_state:
        st.session_state.prompt = ""

    pr_url = st.text_input("Enter the PolicyEngine GitHub Pull Request URL")
    additional_info = st.text_area(
        "Enter additional information (e.g., relevant laws, tax forms, other feedback)",
        height=150,
    )

    if pr_url and "github.com/policyengine" not in pr_url.lower():
        st.error("This tool only works for PolicyEngine GitHub repositories.")
        return

    # Estimate cost before clicking the button
    if pr_url:
        github_token = st.secrets["GITHUB_TOKEN"]
        repo_info = pr_url.split("github.com/")[1].split("/pull/")
        repo = repo_info[0]
        pull_number = repo_info[1]
        owner, repo_name = repo.split("/")

        diff = get_github_diff(owner, repo_name, pull_number, github_token)
        guidelines = get_contributor_guidelines(owner, repo_name, github_token)

        if diff and guidelines:
            estimated_input = diff + guidelines + additional_info
            estimated_input_tokens = estimate_token_count(estimated_input)
            estimated_output_tokens = 1500  # Max tokens set in the API call
            estimated_cost = estimate_cost(
                estimated_input_tokens, estimated_output_tokens
            )

            st.info(f"Estimated cost for this analysis: ${estimated_cost:.4f}")

    if st.button("Analyze PR"):
        if pr_url:
            with st.spinner("Fetching PR details and analyzing..."):
                diff = get_github_diff(
                    owner, repo_name, pull_number, github_token
                )
                guidelines = get_contributor_guidelines(
                    owner, repo_name, github_token
                )

                if diff and guidelines:
                    suggestions, prompt = get_claude_suggestions(
                        diff, guidelines, additional_info
                    )

                    if suggestions:
                        st.session_state.suggestions = suggestions
                        st.session_state.prompt = prompt

                        st.subheader("Improvement Suggestions:")
                        st.markdown(suggestions)
                        st.text_area(
                            "Suggestions (copy from here)",
                            suggestions,
                            height=300,
                        )

                        with st.expander("View Full Prompt"):
                            st.text_area("Full Prompt", prompt, height=300)

                        # Calculate and display actual token count and cost
                        input_tokens = estimate_token_count(prompt)
                        output_tokens = estimate_token_count(suggestions)
                        actual_cost = estimate_cost(
                            input_tokens, output_tokens
                        )

                        st.info(
                            f"Actual token count: {input_tokens} (input), {output_tokens} (output)"
                        )
                        st.info(f"Actual cost: ${actual_cost:.4f}")
                    else:
                        st.error("Failed to generate suggestions.")
        else:
            st.error("Please enter a valid PolicyEngine GitHub PR URL.")

    st.sidebar.markdown("### About")
    st.sidebar.info(
        "This tool uses Claude AI to analyze GitHub Pull Requests "
        "and provide suggestions for code improvements. It's designed "
        "specifically for PolicyEngine repositories."
    )


if __name__ == "__main__":
    main()
