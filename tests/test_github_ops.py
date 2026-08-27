from unittest.mock import MagicMock, patch

from src.github_ops import (
    apply_auto_fixes,
    apply_auto_fixes_with_paths,
    post_inline_comments,
    run_cmd,
)
from src.models import ReviewIssue


def test_run_cmd_success():
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success output"
        mock_run.return_value = mock_result

        success, stdout = run_cmd(["echo", "hello"])
        assert success is True
        assert stdout == "success output"


def test_run_cmd_failure():
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error output"
        mock_run.return_value = mock_result

        success, stderr = run_cmd(["fail", "cmd"])
        assert success is False
        assert stderr == "error output"


@patch("src.github_ops.logger")
def test_run_cmd_redacts_token(mock_logger):
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Failed with SECRET_TOKEN"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        success, stderr = run_cmd(["echo", "SECRET_TOKEN"], redact="SECRET_TOKEN")

        assert success is False
        mock_logger.error.assert_called_once()
        log_msg = mock_logger.error.call_args[0][0]
        assert "SECRET_TOKEN" not in log_msg
        assert "***" in log_msg


def test_apply_auto_fixes_skips_missing_file():
    issue = ReviewIssue(
        file="nonexistent.py",
        line=1,
        severity="INFO",
        issue_name="Test",
        description="Desc",
        original_code="x",
        suggested_fix="y",
    )
    with patch("os.path.exists", return_value=False):
        assert apply_auto_fixes([issue]) is False


def test_apply_auto_fixes_skips_workflow_file():
    issue = ReviewIssue(
        file=".github/workflows/ci.yml",
        line=1,
        severity="INFO",
        issue_name="Test",
        description="Desc",
        original_code="x",
        suggested_fix="y",
    )
    with patch("os.path.exists", return_value=True):
        assert apply_auto_fixes([issue]) is False


def test_apply_auto_fixes_skips_unsafe_fix():
    issue = ReviewIssue(
        file="test.py",
        line=1,
        severity="INFO",
        issue_name="Test",
        description="Desc",
        original_code="x",
        suggested_fix='eval("code")',
    )
    with patch("os.path.exists", return_value=True):
        with patch("src.github_ops.is_suggested_fix_safe", return_value=(False, "unsafe")):
            assert apply_auto_fixes([issue]) is False


def test_post_inline_comments_posts_comment():
    issue = ReviewIssue(
        file="test.py",
        line=1,
        severity="WARNING",
        issue_name="Test",
        description="Desc",
        original_code="x",
        suggested_fix="y",
    )
    mock_pr = MagicMock()
    post_inline_comments(mock_pr, "commit_sha", [issue])
    mock_pr.create_review_comment.assert_called_once()
    kwargs = mock_pr.create_review_comment.call_args[1]
    assert kwargs["path"] == "test.py"
    assert kwargs["line"] == 1
    assert kwargs["commit"] == "commit_sha"


def test_post_inline_comments_fallback_on_failure():
    issue = ReviewIssue(
        file="test.py",
        line=1,
        severity="WARNING",
        issue_name="Test",
        description="Desc",
        original_code="x",
        suggested_fix="y",
    )
    mock_pr = MagicMock()
    mock_pr.create_review_comment.side_effect = Exception("Not in diff")

    post_inline_comments(mock_pr, "commit_sha", [issue])

    mock_pr.create_review_comment.assert_called_once()
    mock_pr.create_issue_comment.assert_called_once()
    fallback_body = mock_pr.create_issue_comment.call_args[0][0]
    assert "AegisPR" in fallback_body
    assert "test.py" in fallback_body


def test_apply_auto_fix_is_atomic_and_returns_only_validated_path(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("dangerous()\n", encoding="utf-8")
    issue = ReviewIssue(
        file="app.py",
        line=1,
        severity="HIGH",
        issue_name="Unsafe call",
        description="The changed line performs an unsafe operation.",
        original_code="dangerous()",
        suggested_fix="safe()",
        code_role="RUNTIME",
        confidence="HIGH",
        remediation_type="AUTOMATIC",
    )

    changed = apply_auto_fixes_with_paths([issue], str(tmp_path))

    assert changed == ["app.py"]
    assert source.read_text(encoding="utf-8") == "safe()\n"


def test_manual_remediation_is_never_applied(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("requests.get(url)\n", encoding="utf-8")
    issue = ReviewIssue(
        file="app.py",
        line=1,
        severity="HIGH",
        issue_name="SSRF",
        description="An untrusted URL reaches an outbound request.",
        original_code="requests.get(url)",
        suggested_fix="requests.get(allowed_url)",
        code_role="RUNTIME",
        confidence="HIGH",
        remediation_type="MANUAL_REQUIRED",
    )

    assert apply_auto_fixes_with_paths([issue], str(tmp_path)) == []
    assert source.read_text(encoding="utf-8") == "requests.get(url)\n"


def test_auto_fix_rejects_repository_escape(tmp_path):
    issue = ReviewIssue(
        file="../outside.py",
        line=1,
        severity="HIGH",
        issue_name="Escape",
        description="Invalid patch path.",
        original_code="dangerous()",
        suggested_fix="safe()",
        confidence="HIGH",
    )

    assert apply_auto_fixes_with_paths([issue], str(tmp_path)) == []
