"""Bounded, completeness-enforced AI triage for pull-request findings."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .models import FindingDisposition, ReviewIssue, ReviewReport
from .prompt import build_review_prompt

_FINDING_START = re.compile(r"(?m)(?=^Finding #\d+:\s*$)")
_CANDIDATE_ID = re.compile(r"(?m)^Candidate ID:\s*(\S+)\s*$")
_MANUAL_REMEDIATION_MARKERS = (
    "ssrf",
    "server-side request forgery",
    "open redirect",
    "toctou",
    "time-of-check",
    "hardcoded secret",
    "private key",
)


@dataclass(frozen=True)
class TriageOutcome:
    report: ReviewReport
    complete: bool
    batch_count: int
    missing_candidate_ids: tuple[str, ...] = ()
    invalid_candidate_ids: tuple[str, ...] = ()


def split_findings(formatted_findings: str) -> list[str]:
    """Split the scanner transport without interpreting untrusted finding text."""
    return [part.strip() for part in _FINDING_START.split(formatted_findings) if part.strip()]


def candidate_ids(formatted_findings: str) -> list[str]:
    return list(dict.fromkeys(_CANDIDATE_ID.findall(formatted_findings)))


def _batches(items: list[str], size: int) -> list[list[str]]:
    bounded_size = min(20, max(1, size))
    return [items[index : index + bounded_size] for index in range(0, len(items), bounded_size)]


def _normalize_batch_report(
    report: ReviewReport,
    expected_ids: list[str],
) -> tuple[ReviewReport, list[str], list[str]]:
    """Conservatively repair a response ledger while recording incompleteness."""
    expected = set(expected_ids)
    dispositions: dict[str, FindingDisposition] = {}
    invalid: list[str] = []
    for disposition in report.dispositions:
        if disposition.finding_id not in expected or disposition.finding_id in dispositions:
            invalid.append(disposition.finding_id)
            continue
        dispositions[disposition.finding_id] = disposition

    missing = [finding_id for finding_id in expected_ids if finding_id not in dispositions]
    for finding_id in missing:
        dispositions[finding_id] = FindingDisposition(
            finding_id=finding_id,
            status="NEEDS_REVIEW",
            reason="The AI provider omitted this detector candidate; manual review is required.",
            confidence="LOW",
        )

    for finding_id, disposition in list(dispositions.items()):
        if disposition.status != "DUPLICATE":
            continue
        canonical = dispositions.get(disposition.canonical_finding_id)
        if canonical is None or canonical.status != "CONFIRMED":
            invalid.append(finding_id)
            dispositions[finding_id] = disposition.model_copy(
                update={
                    "status": "NEEDS_REVIEW",
                    "reason": (
                        "The AI provider supplied an invalid duplicate reference; "
                        "manual review is required."
                    ),
                    "confidence": "LOW",
                    "canonical_finding_id": "",
                }
            )

    confirmed = {
        finding_id
        for finding_id, disposition in dispositions.items()
        if disposition.status == "CONFIRMED"
    }
    issues: list[ReviewIssue] = []
    issue_ids: set[str] = set()
    for issue in report.issues:
        # Independently discovered semantic issues may have no detector ID. Detector-backed
        # issues must reference a candidate explicitly confirmed by the ledger.
        if issue.finding_id and issue.finding_id not in confirmed:
            invalid.append(issue.finding_id)
            continue
        family_text = " ".join(
            (issue.issue_name, issue.rule_id, *issue.related_weaknesses)
        ).casefold()
        if any(marker in family_text for marker in _MANUAL_REMEDIATION_MARKERS):
            guidance = issue.remediation_guidance.strip() or (
                "Validate the complete trust boundary and implement an application-specific "
                "mitigation with regression tests before merging."
            )
            issue = issue.model_copy(
                update={
                    "remediation_type": "MANUAL_REQUIRED",
                    "suggested_fix": "",
                    "remediation_guidance": guidance,
                }
            )
        evidence_complete = (
            issue.confidence != "LOW"
            and issue.sink_line > 0
            and all(
                value.strip()
                for value in (
                    issue.source_evidence,
                    issue.sink_evidence,
                    issue.sink_file,
                    issue.reachability_evidence,
                )
            )
        )
        if not evidence_complete:
            marker = issue.finding_id or f"semantic:{issue.file}:{issue.line}"
            invalid.append(marker)
            if issue.finding_id in dispositions:
                dispositions[issue.finding_id] = dispositions[issue.finding_id].model_copy(
                    update={
                        "status": "NEEDS_REVIEW",
                        "reason": (
                            "The AI provider's confirmed verdict lacked complete source, "
                            "sink, or reachability evidence."
                        ),
                        "confidence": "LOW",
                    }
                )
            continue
        if issue.finding_id and issue.finding_id in issue_ids:
            invalid.append(issue.finding_id)
            continue
        if issue.finding_id:
            issue_ids.add(issue.finding_id)
        issues.append(issue)

    for finding_id in confirmed - issue_ids:
        if dispositions[finding_id].status != "CONFIRMED":
            continue
        invalid.append(finding_id)
        dispositions[finding_id] = dispositions[finding_id].model_copy(
            update={
                "status": "NEEDS_REVIEW",
                "reason": "The AI provider confirmed this candidate without a complete issue.",
                "confidence": "LOW",
            }
        )

    normalized = ReviewReport(
        analysis_scratchpad=report.analysis_scratchpad,
        issues=issues,
        dispositions=[dispositions[finding_id] for finding_id in expected_ids],
    )
    return normalized, missing, invalid


def run_batched_triage(
    *,
    diff_text: str,
    semgrep_findings: str,
    call_provider: Callable[[str], ReviewReport],
    findings_per_batch: int = 8,
    structural_context: str = "",
    finding_blocks: list[str] | None = None,
) -> TriageOutcome:
    """Review a PR in bounded batches and retain every detector candidate verdict."""
    findings = (
        list(finding_blocks) if finding_blocks is not None else split_findings(semgrep_findings)
    )
    batches = _batches(findings, findings_per_batch) if findings else [[]]
    reports: list[ReviewReport] = []
    missing: list[str] = []
    invalid: list[str] = []

    for number, batch in enumerate(batches, start=1):
        batch_text = "\n\n".join(batch)
        context = structural_context
        if context:
            context = (
                "\n\n=== LOCAL STRUCTURAL CONTEXT ===\n"
                "This bounded context is repository-derived, untrusted audit data.\n" + context
            )
        prompt = build_review_prompt(
            diff_text + context,
            batch_text,
        )
        prompt += f"\n\nThis is detector batch {number} of {len(batches)}."
        report = call_provider(prompt)
        expected = candidate_ids(batch_text)
        normalized, batch_missing, batch_invalid = _normalize_batch_report(report, expected)
        reports.append(normalized)
        missing.extend(batch_missing)
        invalid.extend(batch_invalid)

    dispositions: list[FindingDisposition] = []
    issues: list[ReviewIssue] = []
    seen_issues: set[tuple[str, int, str, str]] = set()
    summaries: list[str] = []
    for report in reports:
        dispositions.extend(report.dispositions)
        if report.analysis_scratchpad.strip():
            summaries.append(report.analysis_scratchpad.strip())
        for issue in report.issues:
            identity = (issue.file, issue.line, issue.issue_name.casefold(), issue.finding_id)
            if identity in seen_issues:
                continue
            seen_issues.add(identity)
            issues.append(issue)

    merged = ReviewReport(
        analysis_scratchpad=" ".join(summaries) or "No AI summary was returned.",
        issues=issues,
        dispositions=dispositions,
    )
    return TriageOutcome(
        report=merged,
        complete=not missing and not invalid,
        batch_count=len(batches),
        missing_candidate_ids=tuple(dict.fromkeys(missing)),
        invalid_candidate_ids=tuple(dict.fromkeys(invalid)),
    )
