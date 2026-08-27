from src.models import FindingDisposition, ReviewIssue, ReviewReport
from src.triage import candidate_ids, run_batched_triage, split_findings


def _finding(number: int) -> str:
    return (
        f"Finding #{number}:\n"
        f"Candidate ID: sg-{number}\n"
        "Rule ID: aegispr.python.test\n"
        f"File: app.py:{number}\n"
        "Code Role: RUNTIME\n"
        "Message: test candidate\n"
        "Code Snippet: risky()\n"
    )


def test_split_findings_and_candidate_ids_are_stable():
    payload = _finding(1) + "\n" + _finding(2)

    assert len(split_findings(payload)) == 2
    assert candidate_ids(payload) == ["sg-1", "sg-2"]


def test_batched_triage_merges_complete_ledgers():
    calls: list[str] = []

    def provider(prompt: str) -> ReviewReport:
        calls.append(prompt)
        ids = candidate_ids(prompt)
        return ReviewReport(
            analysis_scratchpad="reviewed",
            issues=[],
            dispositions=[
                FindingDisposition(
                    finding_id=finding_id,
                    status="FALSE_POSITIVE",
                    reason="No attacker-controlled flow reaches the sink.",
                )
                for finding_id in ids
            ],
        )

    outcome = run_batched_triage(
        diff_text="+ risky()",
        semgrep_findings="\n".join(_finding(index) for index in range(1, 4)),
        call_provider=provider,
        findings_per_batch=2,
    )

    assert outcome.complete is True
    assert outcome.batch_count == 2
    assert len(calls) == 2
    assert [item.finding_id for item in outcome.report.dispositions] == [
        "sg-1",
        "sg-2",
        "sg-3",
    ]


def test_missing_disposition_fails_closed_as_needs_review():
    outcome = run_batched_triage(
        diff_text="+ risky()",
        semgrep_findings=_finding(1),
        call_provider=lambda _prompt: ReviewReport(
            analysis_scratchpad="omitted",
            issues=[],
            dispositions=[],
        ),
    )

    assert outcome.complete is False
    assert outcome.missing_candidate_ids == ("sg-1",)
    assert outcome.report.dispositions[0].status == "NEEDS_REVIEW"


def test_unconfirmed_detector_issue_is_removed_from_merged_report():
    issue = ReviewIssue(
        file="app.py",
        line=1,
        severity="HIGH",
        issue_name="Test",
        description="Not confirmed by its ledger.",
        original_code="risky()",
        suggested_fix="safe()",
        finding_id="sg-1",
    )
    outcome = run_batched_triage(
        diff_text="+ risky()",
        semgrep_findings=_finding(1),
        call_provider=lambda _prompt: ReviewReport(
            analysis_scratchpad="invalid",
            issues=[issue],
            dispositions=[
                FindingDisposition(
                    finding_id="sg-1",
                    status="FALSE_POSITIVE",
                    reason="The candidate is not exploitable.",
                )
            ],
        ),
    )

    assert outcome.complete is False
    assert outcome.report.issues == []
    assert outcome.invalid_candidate_ids == ("sg-1",)


def test_semantic_diff_issue_without_detector_id_is_retained():
    issue = ReviewIssue(
        file="app.py",
        line=4,
        severity="HIGH",
        issue_name="Authorization bypass",
        description="A changed route omits the ownership check.",
        original_code="return record",
        suggested_fix="return owned_record",
        source_evidence="Authenticated user controls the record identifier.",
        sink_evidence="The route returns another user's record.",
        sink_file="app.py",
        sink_line=4,
        reachability_evidence="The changed route directly returns the lookup result.",
    )
    outcome = run_batched_triage(
        diff_text="+ return record",
        semgrep_findings="",
        call_provider=lambda _prompt: ReviewReport(
            analysis_scratchpad="semantic review",
            issues=[issue],
            dispositions=[],
        ),
    )

    assert outcome.complete is True
    assert outcome.report.issues == [issue]


def test_confirmed_candidate_without_evidence_is_incomplete_and_downgraded():
    issue = ReviewIssue(
        file="app.py",
        line=1,
        severity="HIGH",
        issue_name="Speculative issue",
        description="The provider did not establish a complete flow.",
        original_code="risky()",
        suggested_fix="safe()",
        finding_id="sg-1",
    )
    outcome = run_batched_triage(
        diff_text="+ risky()",
        semgrep_findings=_finding(1),
        call_provider=lambda _prompt: ReviewReport(
            analysis_scratchpad="incomplete evidence",
            issues=[issue],
            dispositions=[
                FindingDisposition(
                    finding_id="sg-1",
                    status="CONFIRMED",
                    reason="Provider claimed confirmation.",
                )
            ],
        ),
    )

    assert outcome.complete is False
    assert outcome.report.issues == []
    assert outcome.report.dispositions[0].status == "NEEDS_REVIEW"


def test_ssrf_fix_is_forced_to_manual_remediation():
    issue = ReviewIssue(
        file="app.py",
        line=1,
        severity="HIGH",
        issue_name="Server-Side Request Forgery",
        description="Request input controls an outbound destination.",
        original_code="requests.get(url)",
        suggested_fix="requests.get(allowed_url)",
        finding_id="sg-1",
        rule_id="aegispr.python.user-input-to-network-request",
        confidence="HIGH",
        source_evidence="The route parameter supplies url.",
        sink_evidence="requests.get performs the outbound request.",
        sink_file="app.py",
        sink_line=1,
        reachability_evidence="The route passes url directly to requests.get.",
    )
    outcome = run_batched_triage(
        diff_text="+ requests.get(url)",
        semgrep_findings=_finding(1),
        call_provider=lambda _prompt: ReviewReport(
            analysis_scratchpad="confirmed SSRF",
            issues=[issue],
            dispositions=[
                FindingDisposition(
                    finding_id="sg-1",
                    status="CONFIRMED",
                    reason="Complete source-to-sink evidence.",
                )
            ],
        ),
    )

    assert outcome.complete is True
    assert outcome.report.issues[0].remediation_type == "MANUAL_REQUIRED"
    assert outcome.report.issues[0].suggested_fix == ""
    assert outcome.report.issues[0].remediation_guidance


def test_invalid_duplicate_reference_is_fail_closed():
    findings = _finding(1) + "\n" + _finding(2)
    outcome = run_batched_triage(
        diff_text="+ risky()",
        semgrep_findings=findings,
        call_provider=lambda _prompt: ReviewReport(
            analysis_scratchpad="invalid duplicate",
            issues=[],
            dispositions=[
                FindingDisposition(
                    finding_id="sg-1",
                    status="FALSE_POSITIVE",
                    reason="Not exploitable.",
                ),
                FindingDisposition(
                    finding_id="sg-2",
                    status="DUPLICATE",
                    reason="Incorrect duplicate.",
                    canonical_finding_id="sg-missing",
                ),
            ],
        ),
    )

    assert outcome.complete is False
    assert outcome.report.dispositions[1].status == "NEEDS_REVIEW"
