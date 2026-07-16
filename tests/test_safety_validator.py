import pytest
from src.main import is_suggested_fix_safe

def test_safety_validator_safe_code():
    suggested_fix = "subprocess.run(shlex.split(cmd), shell=False)"
    is_safe, reason = is_suggested_fix_safe(suggested_fix)
    assert is_safe is True
    assert reason == ""

def test_safety_validator_blocks_eval():
    suggested_fix = "result = eval('1 + 1')"
    is_safe, reason = is_suggested_fix_safe(suggested_fix)
    assert is_safe is False
    assert "eval" in reason.lower()

def test_safety_validator_blocks_os_system():
    suggested_fix = "os.system('rm -rf /')"
    is_safe, reason = is_suggested_fix_safe(suggested_fix)
    assert is_safe is False
    assert "unvetted sub-process" in reason.lower()

def test_safety_validator_blocks_permissive_chmod():
    suggested_fix = "os.chmod('file.txt', 0o777)"
    is_safe, reason = is_suggested_fix_safe(suggested_fix)
    assert is_safe is False
    assert "permissive" in reason.lower()

def test_safety_validator_allows_subprocess_module():
    # Since we un-banned 'subprocess' entirely and only banned 'os.system' etc.
    suggested_fix = "import subprocess\nsubprocess.Popen(['ls'])"
    is_safe, reason = is_suggested_fix_safe(suggested_fix)
    assert is_safe is True
