import streamlit as st
import requests
import anthropic

client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
CLAUDE_MODEL = "claude-3-5-sonnet-20240620"


def get_claude_suggestions(diff, guidelines):
    prompt = f"""{anthropic.HUMAN_PROMPT} You are an AI assistant providing specific suggestions for code improvements. 
    Analyze this code diff:
    {diff}

    Consider these contributor guidelines:
    {guidelines}

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
            max_tokens=1_500,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        return f"Failed to get suggestions: {str(e)}"


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


def main():
    st.title("PolicyEngine GitHub PR Reviewer")

    pr_url = st.text_input("Enter the PolicyEngine GitHub Pull Request URL")

    if pr_url and "github.com/policyengine" not in pr_url.lower():
        st.error("This tool only works for PolicyEngine GitHub repositories.")
        return

    if st.button("Analyze PR"):
        if pr_url:
            github_token = st.secrets["GITHUB_TOKEN"]
            repo_info = pr_url.split("github.com/")[1].split("/pull/")
            repo = repo_info[0]
            pull_number = repo_info[1]
            owner, repo_name = repo.split("/")

            with st.spinner("Fetching PR details..."):
                diff = get_github_diff(
                    owner, repo_name, pull_number, github_token
                )
                guidelines = get_contributor_guidelines(
                    owner, repo_name, github_token
                )

            if diff and guidelines:
                with st.spinner(
                    "Analyzing code and generating suggestions..."
                ):
                    suggestions = get_claude_suggestions(diff, guidelines)

                if suggestions:
                    st.subheader("Improvement Suggestions:")
                    st.markdown(suggestions)
                else:
                    st.error("Failed to generate suggestions.")
        else:
            st.error("Please enter a valid PolicyEngine GitHub PR URL.")


if __name__ == "__main__":
    main()
