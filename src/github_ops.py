"""
GitHub operations: PR commenting, git commit/push, and auto-fix application.

Handles all interactions with the GitHub API and local git operations,
including token-safe logging to prevent credential leaks in CI output.
"""

import ast
import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

from .fuzzy import fuzzy_replace
from .models import ReviewIssue
from .safety import is_suggested_fix_safe

logger = logging.getLogger(__name__)


def auto_fix_eligibility(issue: ReviewIssue) -> tuple[bool, str]:
    """Keep ambiguous and high-risk remediations out of the automatic path."""
    if issue.remediation_type != "AUTOMATIC":
        return False, "This finding requires manual remediation."
    if issue.code_role not in {"RUNTIME", "UNKNOWN"}:
        return False, f"{issue.code_role.title()} code cannot be patched automatically."
    if issue.confidence == "LOW":
        return False, "Low-confidence findings require manual review."
    if not issue.original_code or not issue.suggested_fix:
        return False, "No complete replacement patch is available."
    if issue.original_code == issue.suggested_fix:
        return False, "The suggested patch does not change the reviewed code."
    if issue.line < 1:
        return False, "The patch has no valid line anchor."
    safe, reason = is_suggested_fix_safe(issue.suggested_fix)
    if not safe:
        return False, f"Safety policy rejected this patch: {reason}"
    return True, "Patch passed deterministic eligibility checks."


def run_cmd(cmd: list[str], redact: str | None = None) -> tuple[bool, str]:
    """
    Execute a shell command safely.

    Args:
        cmd: The command as a list of arguments.
        redact: Optional string to redact from error logs (e.g., tokens).

    Returns:
        (success, stdout_or_stderr)
    """
    result = subprocess.run(cmd, shell=False, text=True, capture_output=True)
    if result.returncode != 0:
        display_cmd = " ".join(cmd)
        if redact:
            display_cmd = display_cmd.replace(redact, "***")
        log_stderr = result.stderr.replace(redact, "***") if redact else result.stderr
        log_stdout = result.stdout.replace(redact, "***") if redact else result.stdout
        logger.error(f"Command failed: {display_cmd}\nStdout: {log_stdout}\nStderr: {log_stderr}")
        return False, result.stderr
    return True, result.stdout


def _validate_patched_content(file_path: Path, content: str) -> tuple[bool, str]:
    try:
        if file_path.suffix.casefold() == ".py":
            ast.parse(content, filename=str(file_path))
        elif file_path.suffix.casefold() == ".json":
            json.loads(content)
    except (SyntaxError, json.JSONDecodeError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, ""


def _atomic_write_text(file_path: Path, content: str) -> None:
    mode = file_path.stat().st_mode
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=file_path.parent,
            prefix=f".{file_path.name}.aegispr-",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = temporary.name
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, file_path)
        temporary_path = None
    finally:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def apply_auto_fixes_with_paths(issues: list[ReviewIssue], repo_path: str = ".") -> list[str]:
    """Apply only contained, eligible patches and return exactly the changed paths."""
    root = Path(repo_path).resolve()
    grouped: dict[Path, list[ReviewIssue]] = {}
    for issue in issues:
        eligible, reason = auto_fix_eligibility(issue)
        if not eligible:
            logger.warning("Skipping auto-fix for %s:%s: %s", issue.file, issue.line, reason)
            continue
        relative = issue.file.replace("\\", "/")
        file_path = (root / relative).resolve()
        try:
            file_path.relative_to(root)
        except ValueError:
            logger.warning("Skipping path outside the repository: %s", relative)
            continue
        if relative.startswith(".github/workflows/") or not file_path.is_file():
            logger.warning("Skipping non-patchable file: %s", relative)
            continue
        grouped.setdefault(file_path, []).append(issue)

    changed: list[str] = []
    for file_path, file_issues in grouped.items():
        relative = file_path.relative_to(root).as_posix()
        try:
            original = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            logger.warning("Could not read %s as UTF-8: %s", relative, exc)
            continue
        candidate = original
        for issue in sorted(file_issues, key=lambda item: item.line, reverse=True):
            replacement, applied = fuzzy_replace(
                candidate,
                issue.original_code,
                issue.suggested_fix,
                target_line=issue.line,
            )
            if not applied:
                logger.warning("Patch for %s:%s was missing or ambiguous.", relative, issue.line)
                continue
            valid, reason = _validate_patched_content(file_path, replacement)
            if not valid:
                logger.warning("Rejected invalid patch for %s:%s: %s", relative, issue.line, reason)
                continue
            candidate = replacement
        if candidate != original:
            try:
                _atomic_write_text(file_path, candidate)
            except OSError as exc:
                logger.error("Could not atomically update %s: %s", relative, exc)
                continue
            changed.append(relative)
    return changed


def apply_auto_fixes(issues: list[ReviewIssue], repo_path: str = ".") -> bool:
    """Compatibility wrapper for callers that only need a boolean result."""
    return bool(apply_auto_fixes_with_paths(issues, repo_path))


def push_auto_fixes(
    github_token: str,
    repository: str,
    head_branch: str,
    *,
    changed_files: list[str] | None = None,
    repo_path: str = ".",
) -> None:
    """
    Stage, commit, and push auto-fix changes back to the PR branch.

    The GitHub token is redacted from all log output to prevent
    credential leaks in CI console.
    """
    logger.info("Staging and committing auto-fixes...")
    root = str(Path(repo_path).resolve())

    def git(*args: str, redact: str | None = None) -> tuple[bool, str]:
        return run_cmd(
            ["git", "-c", f"safe.directory={root}", "-C", root, *args],
            redact=redact,
        )

    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "github-actions[bot]@users.noreply.github.com")

    paths = list(dict.fromkeys(changed_files or []))
    if not paths:
        logger.info("No validated auto-fix paths were supplied for staging.")
        return
    git("add", "--", *paths)

    success, stdout = git("status", "--porcelain", "--", *paths)
    if not stdout.strip():
        logger.info("No local modifications found to commit.")
        return

    commit_success, _ = git("commit", "-m", "AegisPR: apply validated security fixes")
    if not commit_success:
        logger.error("Failed to commit changes.")
        return

    logger.info(f"Pushing changes to branch {head_branch}...")
    remote_url = f"https://x-access-token:{github_token}@github.com/{repository}.git"

    # Token is redacted from all error log output
    push_success, _ = git("push", remote_url, f"HEAD:{head_branch}", redact=github_token)
    if push_success:
        logger.info("Successfully pushed auto-fixes back to the repository branch!")
    else:
        logger.error("Failed to push auto-fixes to the remote repository.")


def post_inline_comments(pr, latest_commit, issues: list[ReviewIssue]) -> None:
    """
    Post inline review comments on the PR for each identified issue.

    Falls back to a general PR issue comment if the inline comment fails
    (e.g., the line is not part of the diff). Includes a small delay
    between comments to avoid hitting GitHub's secondary rate limits.
    """
    for i, issue in enumerate(issues):
        body = f"### 🛡️ AegisPR [{issue.severity}]\n**{issue.issue_name}**\n\n{issue.description}"
        if issue.suggested_fix:
            body += f"\n\n```suggestion\n{issue.suggested_fix}\n```"
        elif issue.remediation_guidance:
            body += f"\n\n**Manual remediation:** {issue.remediation_guidance}"

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
                fallback_body += f"\n\n**Suggested Fix:**\n```\n{issue.suggested_fix}\n```"
            elif issue.remediation_guidance:
                fallback_body += f"\n\n**Manual remediation:** {issue.remediation_guidance}"
            try:
                pr.create_issue_comment(fallback_body)
                logger.info("Successfully posted fallback PR issue comment.")
            except Exception as fe:
                logger.error(f"Failed to post fallback PR comment: {fe}")

        # Small delay between comments to respect GitHub rate limits
        if i < len(issues) - 1:
            time.sleep(1)
