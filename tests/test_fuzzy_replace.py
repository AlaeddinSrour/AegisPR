import pytest
from src.fuzzy import fuzzy_replace

def test_fuzzy_replace_exact_match():
    content = "def test():\n    print('hello')\n    return True\n"
    original = "    print('hello')"
    replacement = "    print('world')"
    new_content, success = fuzzy_replace(content, original, replacement)
    
    assert success is True
    assert "print('world')" in new_content
    assert "print('hello')" not in new_content

def test_fuzzy_replace_bizarre_indentation():
    content = "def test():\n          os.system('id')\n    return True\n"
    original = "os.system('id')"
    replacement = "subprocess.run(['id'], shell=False)"
    
    new_content, success = fuzzy_replace(content, original, replacement)
    assert success is True
    assert "          subprocess.run(['id'], shell=False)" in new_content

def test_fuzzy_replace_multiline():
    content = "def test():\n    x = 1\n    y = 2\n    z = 3\n"
    original = "x = 1\ny = 2"
    replacement = "x = 10\ny = 20"
    
    new_content, success = fuzzy_replace(content, original, replacement)
    assert success is True
    assert "    x = 10\n    y = 20" in new_content

def test_fuzzy_replace_not_found():
    content = "def test():\n    x = 1\n"
    original = "y = 2"
    replacement = "y = 3"
    
    new_content, success = fuzzy_replace(content, original, replacement)
    assert success is False
    assert new_content == content
