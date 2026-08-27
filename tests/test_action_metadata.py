from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_action_exposes_provider_completeness_and_workspace_controls():
    action = (ROOT / "action.yml").read_text(encoding="utf-8")

    for input_name in (
        "openrouter_api_key:",
        "ai_provider:",
        "findings_per_batch:",
        "fail_on_incomplete:",
        "workspace_subdirectory:",
    ):
        assert input_name in action


def test_container_entrypoint_cannot_import_target_repository_src_first():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY aegispr_action.py /app/aegispr_action.py" in dockerfile
    assert 'ENTRYPOINT ["python", "/app/aegispr_action.py"]' in dockerfile
    assert 'ENTRYPOINT ["python", "-m", "src.main"]' not in dockerfile


def test_self_review_keeps_action_code_separate_from_pr_audit_data():
    workflow = (ROOT / ".github/workflows/review.yml").read_text(encoding="utf-8")

    audit_checkout = workflow.index("Checkout pull-request code as audit data")
    trusted_checkout = workflow.index("Checkout trusted AegisPR action")
    action_run = workflow.index("uses: ./.aegispr-action")

    assert audit_checkout < trusted_checkout < action_run
    assert workflow.count("persist-credentials: false") == 2
