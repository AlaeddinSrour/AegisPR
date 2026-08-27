"""AegisPR GitHub Action orchestration."""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path

from github import Auth, Github
from google import genai

from .ast_context import build_ast_context
from .diff import get_modified_lines
from .gemini_client import call_gemini_with_failover
from .github_ops import apply_auto_fixes_with_paths, post_inline_comments, push_auto_fixes
from .models import ReviewIssue, ReviewReport
from .openrouter_client import call_openrouter_with_failover
from .related_context import build_related_context
from .semgrep_runner import SemgrepScanOutput, bundled_rules_sha256, run_semgrep_scan
from .triage import TriageOutcome, run_batched_triage

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _enabled(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _positive_int(name: str, default: int, *, maximum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if value < 1 or (maximum is not None and value > maximum):
        bound = f" between 1 and {maximum}" if maximum is not None else " greater than zero"
        raise RuntimeError(f"{name} must be{bound}.")
    return value


def _repository_workspace() -> Path:
    root = Path(os.environ.get("GITHUB_WORKSPACE", "/github/workspace")).resolve()
    subdirectory = os.environ.get("INPUT_WORKSPACE_SUBDIRECTORY", ".").strip() or "."
    repository = (root / subdirectory).resolve()
    try:
        repository.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("workspace_subdirectory must stay inside GITHUB_WORKSPACE.") from exc
    if not repository.is_dir():
        raise RuntimeError(f"Configured repository workspace does not exist: {repository}")
    return repository


def _provider(
    gemini_api_key: str,
    openrouter_api_key: str,
) -> tuple[str, Callable[[str], ReviewReport]]:
    requested = os.environ.get("INPUT_AI_PROVIDER", "auto").strip().casefold()
    if requested not in {"auto", "gemini", "openrouter"}:
        raise RuntimeError("INPUT_AI_PROVIDER must be auto, gemini, or openrouter.")

    available: list[tuple[str, Callable[[str], ReviewReport]]] = []
    if gemini_api_key:
        client = genai.Client(api_key=gemini_api_key)
        available.append(("gemini", lambda prompt: call_gemini_with_failover(client, prompt)))
    if openrouter_api_key:
        allow_collection = _enabled("INPUT_OPENROUTER_ALLOW_DATA_COLLECTION")
        available.append(
            (
                "openrouter",
                lambda prompt: call_openrouter_with_failover(
                    openrouter_api_key,
                    prompt,
                    allow_data_collection=allow_collection,
                ),
            )
        )

    if requested != "auto":
        for name, caller in available:
            if name == requested:
                return name, caller
        raise RuntimeError(f"The {requested} provider was selected but its API key is missing.")
    if not available:
        raise RuntimeError("Provide gemini_api_key or openrouter_api_key for AI triage.")
    if len(available) == 1:
        return available[0]

    def failover(prompt: str) -> ReviewReport:
        failures: list[str] = []
        for name, caller in available:
            try:
                return caller(prompt)
            except RuntimeError as exc:
                failures.append(f"{name}: {' '.join(str(exc).split())[:180]}")
                logger.warning("%s triage failed; trying the next configured provider.", name)
        raise RuntimeError("Every configured AI provider failed. " + "; ".join(failures))

    return "auto", failover


def _changed_line_issues(
    issues: list[ReviewIssue],
    changed_files_lines: dict[str, set[int]],
) -> list[ReviewIssue]:
    """Enforce AegisPR's contract: only findings anchored to added PR lines."""
    retained: list[ReviewIssue] = []
    for issue in issues:
        path = issue.sink_file or issue.file
        line = issue.sink_line or issue.line
        if path not in changed_files_lines or line not in changed_files_lines[path]:
            logger.warning("Discarding unmodified-line issue at %s:%s.", path, line)
            continue
        if issue.code_role not in {"RUNTIME", "UNKNOWN"}:
            logger.info("Excluding %s issue in %s code.", issue.code_role, path)
            continue
        if issue.file != path or issue.line != line:
            issue = issue.model_copy(update={"file": path, "line": line})
        retained.append(issue)
    return retained


def _post_summary(pr, outcome: TriageOutcome, issue_count: int, diagnostics: int) -> None:
    counts: dict[str, int] = {}
    for disposition in outcome.report.dispositions:
        counts[disposition.status] = counts.get(disposition.status, 0) + 1
    ledger = ", ".join(
        f"{status.lower().replace('_', ' ')}: {count}" for status, count in sorted(counts.items())
    )
    completeness = "Complete" if outcome.complete else "Incomplete — manual review required"
    body = (
        "## 🛡️ AegisPR security review\n\n"
        f"- **Status:** {completeness}\n"
        f"- **Confirmed issues on changed lines:** {issue_count}\n"
        f"- **Detector batches:** {outcome.batch_count}\n"
        f"- **Candidate ledger:** {ledger or 'No detector candidates'}\n"
        f"- **Non-runtime scanner diagnostics:** {diagnostics}\n"
    )
    if outcome.missing_candidate_ids:
        body += f"- **Missing AI verdicts:** {len(outcome.missing_candidate_ids)}\n"
    if outcome.invalid_candidate_ids:
        body += f"- **Invalid AI ledger entries:** {len(outcome.invalid_candidate_ids)}\n"
    pr.create_issue_comment(body)


def main() -> None:
    github_token = os.environ.get("INPUT_GITHUB_TOKEN", "").strip()
    gemini_api_key = os.environ.get("INPUT_GEMINI_API_KEY", "").strip()
    openrouter_api_key = os.environ.get("INPUT_OPENROUTER_API_KEY", "").strip()
    if not github_token:
        raise RuntimeError("INPUT_GITHUB_TOKEN is required.")

    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    workspace = _repository_workspace()
    if not event_path or not repository:
        raise RuntimeError("GITHUB_EVENT_PATH and GITHUB_REPOSITORY are required.")
    event_data = json.loads(Path(event_path).read_text(encoding="utf-8"))
    if "pull_request" not in event_data:
        logger.info("Not a pull request event; nothing to review.")
        return

    provider_name, call_provider = _provider(gemini_api_key, openrouter_api_key)
    pr_data = event_data["pull_request"]
    pr_number = int(pr_data["number"])
    head_branch = str(pr_data["head"]["ref"])
    is_fork = bool(pr_data["head"]["repo"]["fork"])

    gh = Github(auth=Auth.Token(github_token))
    repo = gh.get_repo(repository)
    pr = repo.get_pull(pr_number)
    diff_parts: list[str] = []
    changed_files_lines: dict[str, set[int]] = {}
    for changed_file in pr.get_files():
        if any(character in changed_file.filename for character in "\r\n\0"):
            raise RuntimeError("A changed path contains unsupported control characters.")
        patch = changed_file.patch
        if not patch:
            continue
        diff_parts.append(f"--- a/{changed_file.filename}\n+++ b/{changed_file.filename}\n{patch}")
        changed_files_lines[changed_file.filename] = get_modified_lines(patch)
    diff_text = "\n\n".join(diff_parts)
    if not diff_text:
        logger.info("No reviewable added lines were present in this pull request.")
        return
    max_diff_chars = _positive_int("INPUT_MAX_DIFF_CHARS", 300_000)
    if len(diff_text) > max_diff_chars:
        raise RuntimeError(
            f"Pull-request diff is {len(diff_text):,} characters, above the configured "
            f"{max_diff_chars:,}-character audit boundary. Split the PR or raise max_diff_chars."
        )

    exclusions = [
        value.strip()
        for value in os.environ.get("INPUT_SEMGREP_EXCLUSIONS", ".git,.venv,node_modules").split(
            ","
        )
        if value.strip()
    ]
    rule_mode = os.environ.get("INPUT_SEMGREP_RULE_MODE", "bundled").strip().casefold()
    max_target_bytes = _positive_int("INPUT_MAX_TARGET_BYTES", 1_000_000)
    logger.info(
        "Reviewing PR #%s with %s · bundled rules %s · %s changed files.",
        pr_number,
        provider_name,
        bundled_rules_sha256()[:12],
        len(changed_files_lines),
    )
    semgrep_output: SemgrepScanOutput = run_semgrep_scan(
        str(workspace),
        changed_files_lines,
        exclude_patterns=exclusions,
        max_target_bytes=max_target_bytes,
        rule_mode=rule_mode,
    )

    changed_paths = list(changed_files_lines)
    structural_context = "\n\n".join(
        value
        for value in (
            build_ast_context(workspace, changed_paths),
            build_related_context(workspace, changed_paths, max_characters=20_000),
        )
        if value
    )
    outcome = run_batched_triage(
        diff_text=diff_text,
        semgrep_findings=str(semgrep_output),
        call_provider=call_provider,
        findings_per_batch=_positive_int("INPUT_FINDINGS_PER_BATCH", 8, maximum=20),
        structural_context=structural_context,
        finding_blocks=semgrep_output.finding_blocks,
    )
    issues = _changed_line_issues(outcome.report.issues, changed_files_lines)

    if issues:
        commits = pr.get_commits()
        latest_commit = commits[commits.totalCount - 1]
        post_inline_comments(pr, latest_commit, issues)
    _post_summary(pr, outcome, len(issues), len(semgrep_output.diagnostics))

    if issues and not is_fork and _enabled("INPUT_APPLY_FIXES", True):
        changed = apply_auto_fixes_with_paths(issues, str(workspace))
        if changed:
            push_auto_fixes(
                github_token,
                repository,
                head_branch,
                changed_files=changed,
                repo_path=str(workspace),
            )
    elif is_fork:
        logger.info("Skipping auto-fixes for a fork pull request.")

    if not outcome.complete and _enabled("INPUT_FAIL_ON_INCOMPLETE", True):
        raise RuntimeError("AI triage was incomplete; the PR cannot be reported as clean.")
    blocking = {
        value.strip().upper()
        for value in os.environ.get("INPUT_BLOCKING_SEVERITIES", "CRITICAL,HIGH").split(",")
        if value.strip()
    }
    blocking_issues = [issue for issue in issues if issue.severity in blocking]
    if blocking_issues:
        names = ", ".join(
            f"{issue.issue_name} ({issue.severity})" for issue in blocking_issues[:10]
        )
        raise RuntimeError(f"AegisPR found blocking security issues: {names}")
    logger.info("AegisPR completed with no blocking changed-line security issues.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("%s", " ".join(str(exc).split()))
        sys.exit(1)
