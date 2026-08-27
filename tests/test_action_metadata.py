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

    assert "Checkout trusted AegisPR action" in workflow
    assert "Checkout pull-request code as audit data" in workflow
    assert "uses: ./.aegispr-action" in workflow
    assert workflow.count("persist-credentials: false") == 2
