"""
AegisPR — AI-Driven CI/CD Security Agent

Orchestrator entry point: reads the GitHub event, extracts the PR diff,
runs Semgrep + Gemini analysis, posts inline comments, applies auto-fixes,
and gates the build on CRITICAL/HIGH severity issues.
"""

import json
import logging
import os
import sys

from github import Github, Auth
from google import genai

from .diff import get_modified_lines
from .gemini_client import call_gemini_with_failover
from .github_ops import apply_auto_fixes, push_auto_fixes, post_inline_comments
from .prompt import build_review_prompt
from .semgrep_runner import run_semgrep_scan

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def main() -> None:
    if len(sys.argv) < 3:
        logger.error("Usage: main.py <github_token> <gemini_api_key>")
        sys.exit(1)

    github_token = sys.argv[1]
    gemini_api_key = sys.argv[2]

    event_path = os.getenv("GITHUB_EVENT_PATH")
    repository = os.getenv("GITHUB_REPOSITORY")

    if not event_path or not repository:
        logger.error("Missing GITHUB_EVENT_PATH or GITHUB_REPOSITORY environment variable.")
        sys.exit(1)

    with open(event_path, "r") as f:
        event_data = json.load(f)

    if "pull_request" not in event_data:
        logger.info("Not a pull request event. Exiting.")
        sys.exit(0)

    pr_number = event_data["pull_request"]["number"]
    head_branch = event_data["pull_request"]["head"]["ref"]
    is_fork = event_data["pull_request"]["head"]["repo"]["fork"]

    logger.info(f"Processing PR #{pr_number} in repo {repository} on branch {head_branch}")

    # ── GitHub client setup ──────────────────────────────────────────
    auth = Auth.Token(github_token)
    gh = Github(auth=auth)
    repo = gh.get_repo(repository)
    pr = repo.get_pull(pr_number)

    # ── Extract PR diff and modified line numbers ────────────────────
    files = pr.get_files()
    diff_text = ""
    changed_files_lines: dict[str, set[int]] = {}
    for file in files:
        if file.patch:
            diff_text += f"--- a/{file.filename}\n+++ b/{file.filename}\n{file.patch}\n\n"
            changed_files_lines[file.filename] = get_modified_lines(file.patch)

    if not diff_text:
        logger.info("No code changes found. Exiting.")
        sys.exit(0)

    logger.info(f"Extracted diff ({len(diff_text)} characters).")

    # ── Run Semgrep SAST scan ────────────────────────────────────────
    semgrep_findings = ""
    try:
        workspace = os.getenv("GITHUB_WORKSPACE", "/github/workspace")
        semgrep_findings = run_semgrep_scan(workspace, changed_files_lines)
        if semgrep_findings:
            logger.info("Semgrep findings extracted. Injecting into prompt for triage.")
    except Exception as e:
        logger.error(f"Failed to run Semgrep: {e}")

    # ── Initialize Gemini client ─────────────────────────────────────
    try:
        client = genai.Client(api_key=gemini_api_key)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        sys.exit(1)

    # ── Call Gemini for structured review ─────────────────────────────
    prompt = build_review_prompt(diff_text, semgrep_findings)

    try:
        report = call_gemini_with_failover(client, prompt)
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)

    # ── 1. Post inline comments on the PR ────────────────────────────
    if report.issues:
        commits = pr.get_commits()
        latest_commit = commits[commits.totalCount - 1]
        post_inline_comments(pr, latest_commit, report.issues)

    # ── 2. Apply and push auto-fixes ─────────────────────────────────
    if report.issues and not is_fork:
        fixed_any = apply_auto_fixes(report.issues)
        if fixed_any:
            push_auto_fixes(github_token, repository, head_branch)
    elif is_fork:
        logger.info("Skipping auto-fixing since PR is from a fork (write permissions restricted).")

    # ── 3. Gate the build on blocking severity ───────────────────────
    has_blocking_issues = any(
        issue.severity.upper() in ("CRITICAL", "HIGH")
        for issue in report.issues
    )

    if has_blocking_issues:
        for issue in report.issues:
            if issue.severity.upper() in ("CRITICAL", "HIGH"):
                logger.warning(f"Blocking issue found: {issue.issue_name} ({issue.severity})")
        logger.error("CI failed due to CRITICAL or HIGH severity security issues.")
        sys.exit(1)
    else:
        logger.info("No blocking issues found. Code review completed successfully.")


if __name__ == "__main__":
    main()
