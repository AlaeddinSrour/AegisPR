"""
GitHub operations: PR commenting, git commit/push, and auto-fix application.

Handles all interactions with the GitHub API and local git operations,
including token-safe logging to prevent credential leaks in CI output.
"""

import logging
import os
import shlex
import subprocess
import time
from typing import List, Optional

from .models import ReviewIssue
from .safety import is_suggested_fix_safe
from .fuzzy import fuzzy_replace

logger = logging.getLogger(__name__)


def run_cmd(cmd: str, redact: Optional[str] = None) -> tuple[bool, str]:
    """
    Execute a shell command safely (no shell interpolation).

    Args:
        cmd: The command string to execute.
        redact: Optional string to redact from error logs (e.g., tokens).

    Returns:
        (success, stdout_or_stderr)
    """
    result = subprocess.run(
        shlex.split(cmd), shell=False, text=True, capture_output=True
    )
    if result.returncode != 0:
        log_cmd = cmd.replace(redact, "***") if redact else cmd
        log_stderr = result.stderr.replace(redact, "***") if redact else result.stderr
        log_stdout = result.stdout.replace(redact, "***") if redact else result.stdout
        logger.error(
            f"Command failed: {log_cmd}\nStdout: {log_stdout}\nStderr: {log_stderr}"
        )
        return False, result.stderr
    return True, result.stdout


def apply_auto_fixes(issues: List[ReviewIssue]) -> bool:
    """
    Apply AI-suggested auto-fixes to local files using fuzzy matching.

    Each fix is validated by the safety validator before application.
    Workflow files under .github/workflows are skipped to prevent
    permission crashes.

    Returns:
        True if any fixes were applied.
    """
    fixed_any = False
    for issue in issues:
        if not issue.original_code or not issue.suggested_fix:
            continue

        file_path = issue.file
        if not os.path.exists(file_path):
            logger.warning(f"File {file_path} not found locally. Skipping auto-fix.")
            continue

        if ".github/workflows" in file_path:
            logger.warning(
                f"Skipping auto-fix for {file_path}. "
                "GitHub Actions tokens cannot push modifications to workflow files."
            )
            continue

        is_safe, reason = is_suggested_fix_safe(issue.suggested_fix)
        if not is_safe:
            logger.warning(
                f"Skipping auto-fix for {file_path} due to safety validation failure: {reason}"
            )
            continue

        try:
            with open(file_path, "r") as f:
                content = f.read()

            new_content, fixed = fuzzy_replace(
                content, issue.original_code, issue.suggested_fix
            )
            if fixed:
                logger.info(f"Applying fuzzy auto-fix to {file_path}...")
                with open(file_path, "w") as f:
                    f.write(new_content)
                fixed_any = True
            else:
                logger.warning(
                    f"Could not apply auto-fix to {file_path}: "
                    "original_code pattern not found via fuzzy match."
                )
        except Exception as e:
            logger.error(f"Error applying auto-fix to {file_path}: {e}")

    return fixed_any


def push_auto_fixes(
    github_token: str, repository: str, head_branch: str
) -> None:
    """
    Stage, commit, and push auto-fix changes back to the PR branch.

    The GitHub token is redacted from all log output to prevent
    credential leaks in CI console.
    """
    logger.info("Staging and committing auto-fixes...")
    run_cmd('git config --global --add safe.directory /github/workspace')
    run_cmd('git config user.name "github-actions[bot]"')
    run_cmd('git config user.email "github-actions[bot]@users.noreply.github.com"')

    run_cmd('git add .')

    success, stdout = run_cmd('git status --porcelain')
    if not stdout.strip():
        logger.info("No local modifications found to commit.")
        return

    commit_success, _ = run_cmd(
        'git commit -m "🤖 AI Auto-Fix: Mitigate vulnerabilities"'
    )
    if not commit_success:
        logger.error("Failed to commit changes.")
        return

    logger.info(f"Pushing changes to branch {head_branch}...")
    remote_url = f"https://x-access-token:{github_token}@github.com/{repository}.git"

    # Token is redacted from all error log output
    push_success, _ = run_cmd(
        f"git push {remote_url} HEAD:{head_branch}",
        redact=github_token,
    )
    if push_success:
        logger.info("Successfully pushed auto-fixes back to the repository branch!")
    else:
        logger.error("Failed to push auto-fixes to the remote repository.")


def post_inline_comments(pr, latest_commit, issues: List[ReviewIssue]) -> None:
    """
    Post inline review comments on the PR for each identified issue.

    Falls back to a general PR issue comment if the inline comment fails
    (e.g., the line is not part of the diff). Includes a small delay
    between comments to avoid hitting GitHub's secondary rate limits.
    """
    for i, issue in enumerate(issues):
        body = (
            f"### 🛡️ AegisPR [{issue.severity}]\n"
            f"**{issue.issue_name}**\n\n"
            f"{issue.description}"
        )
        if issue.suggested_fix:
            body += f"\n\n```suggestion\n{issue.suggested_fix}\n```"

        logger.info(f"Posting inline comment to {issue.file}:{issue.line}...")
        try:
            pr.create_review_comment(
                body=body,
                commit=latest_commit,
                path=issue.file,
                line=issue.line,
                side="RIGHT",
            )
            logger.info("Successfully posted inline comment.")
        except Exception as e:
            logger.warning(
                f"Failed to post inline comment on {issue.file}:{issue.line} "
                f"(possibly line not in diff): {e}"
            )
            # Fallback to general PR comment
            fallback_body = (
                f"### 🛡️ AegisPR [{issue.severity}] on `{issue.file}` line {issue.line}\n"
                f"**{issue.issue_name}**\n\n"
                f"{issue.description}"
            )
            if issue.suggested_fix:
                fallback_body += (
                    f"\n\n**Suggested Fix:**\n```\n{issue.suggested_fix}\n```"
                )
            try:
                pr.create_issue_comment(fallback_body)
                logger.info("Successfully posted fallback PR issue comment.")
            except Exception as fe:
                logger.error(f"Failed to post fallback PR comment: {fe}")

        # Small delay between comments to respect GitHub rate limits
        if i < len(issues) - 1:
            time.sleep(1)
