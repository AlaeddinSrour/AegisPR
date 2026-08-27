from unittest.mock import MagicMock, patch

import pytest

from src.main import _changed_line_issues, _positive_int, _provider, _repository_workspace
from src.models import ReviewIssue, ReviewReport


def _issue(**overrides):
    values = {
        "file": "app.py",
        "line": 7,
        "severity": "HIGH",
        "issue_name": "Authorization bypass",
        "description": "A changed route omits authorization.",
        "original_code": "return record",
        "suggested_fix": "return owned_record",
        "code_role": "RUNTIME",
    }
    values.update(overrides)
    return ReviewIssue(**values)


def test_changed_line_contract_discards_unmodified_and_non_runtime_issues():
    retained = _changed_line_issues(
        [
            _issue(),
            _issue(line=8),
            _issue(file="tests/test_app.py", code_role="TEST"),
        ],
        {"app.py": {7}, "tests/test_app.py": {7}},
    )

    assert retained == [_issue()]


def test_sink_location_is_used_for_changed_line_enforcement():
    issue = _issue(file="helper.py", line=2, sink_file="app.py", sink_line=7)

    retained = _changed_line_issues([issue], {"app.py": {7}})

    assert retained[0].file == "app.py"
    assert retained[0].line == 7


def test_positive_int_rejects_invalid_action_input(monkeypatch):
    monkeypatch.setenv("INPUT_FINDINGS_PER_BATCH", "0")

    with pytest.raises(RuntimeError, match="between 1 and 20"):
        _positive_int("INPUT_FINDINGS_PER_BATCH", 8, maximum=20)


def test_provider_requires_key_for_explicit_selection(monkeypatch):
    monkeypatch.setenv("INPUT_AI_PROVIDER", "openrouter")

    with pytest.raises(RuntimeError, match="API key is missing"):
        _provider("gemini-key", "")


def test_auto_provider_fails_over_between_configured_services(monkeypatch):
    monkeypatch.setenv("INPUT_AI_PROVIDER", "auto")
    expected = ReviewReport(analysis_scratchpad="ok", issues=[], dispositions=[])
    client = MagicMock()
    with (
        patch("src.main.genai.Client", return_value=client),
        patch("src.main.call_gemini_with_failover", side_effect=RuntimeError("quota")),
        patch("src.main.call_openrouter_with_failover", return_value=expected) as openrouter,
    ):
        name, caller = _provider("gemini-key", "openrouter-key")
        result = caller("prompt")

    assert name == "auto"
    assert result == expected
    openrouter.assert_called_once()


def test_repository_workspace_accepts_contained_subdirectory(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("INPUT_WORKSPACE_SUBDIRECTORY", "target")

    assert _repository_workspace() == target


def test_repository_workspace_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("INPUT_WORKSPACE_SUBDIRECTORY", "../outside")

    with pytest.raises(RuntimeError, match="must stay inside"):
        _repository_workspace()
