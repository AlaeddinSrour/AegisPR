"""
Semgrep static analysis runner with diff-aware filtering.

Runs Semgrep on the repository and returns formatted findings
filtered to only include lines modified in the current PR.
"""

import json
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

SEMGREP_TIMEOUT_SECONDS = 300  # 5-minute hard limit to prevent CI hangs


def run_semgrep_scan(
    repo_path: str,
    changed_files_lines: Optional[dict[str, set[int]]] = None,
) -> str:
    """
    Run Semgrep on the repository and return formatted findings for LLM triage.

    Findings are filtered to only include lines modified in the PR when
    `changed_files_lines` is provided.

    Args:
        repo_path: Absolute path to the repository root.
        changed_files_lines: Mapping of {filepath: set(modified_line_numbers)}.

    Returns:
        Formatted string of Semgrep findings, or "" if none found.
    """
    logger.info("Running Semgrep scan for sequential triage...")
    try:
        semgrep_cmd = [
            "semgrep", "scan",
            "--config", "auto",
            "--exclude", ".github",
            "--max-target-bytes", "1000000",
            "--json",
            "--quiet",
        ]
        result = subprocess.run(
            semgrep_cmd + [repo_path],
            capture_output=True,
            text=True,
            timeout=SEMGREP_TIMEOUT_SECONDS,
        )
        if not result.stdout:
            return ""

        data = json.loads(result.stdout)
        results = data.get("results", [])
        if not results:
            return ""

        formatted_findings = []
        for i, finding in enumerate(results):
            path = finding.get("path", "")
            start_line = finding.get("start", {}).get("line", "")

            # Diff-aware filtering
            if changed_files_lines is not None:
                if path not in changed_files_lines:
                    continue  # Skip files not modified in the PR
                if start_line not in changed_files_lines[path]:
                    continue  # Skip vulnerabilities on lines not modified in the PR

            rule_id = finding.get("check_id", "")
            message = finding.get("extra", {}).get("message", "")
            snippet = finding.get("extra", {}).get("lines", "").strip()

            file_content = ""
            try:
                full_path = os.path.join(repo_path, path)
                if os.path.exists(full_path):
                    with open(full_path, 'r') as f:
                        file_content = f.read()
            except Exception as e:
                logger.warning(f"Could not read full file {path} for context: {e}")

            block = (
                f"Finding #{i + 1}:\n"
                f"Rule ID: {rule_id}\n"
                f"File: {path}:{start_line}\n"
                f"Message: {message}\n"
                f"Code Snippet: {snippet}\n"
            )
            if file_content:
                block += (
                    f"\n--- FULL FILE CONTEXT ({path}) ---\n"
                    f"{file_content}\n"
                    f"--- END FILE CONTEXT ---\n"
                )

            formatted_findings.append(block)

        return "\n".join(formatted_findings)

    except subprocess.TimeoutExpired:
        logger.error(
            f"Semgrep scan timed out after {SEMGREP_TIMEOUT_SECONDS}s. "
            "Skipping SAST findings."
        )
        return ""
    except Exception as e:
        logger.error(f"Semgrep scan failed: {e}")
        return ""
