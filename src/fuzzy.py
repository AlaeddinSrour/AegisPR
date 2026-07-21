"""
Fuzzy code replacement engine.

Matches AI-suggested original_code against actual file content by
stripping leading whitespace, then re-applies the file's original
indentation to the replacement lines.
"""

import re


def fuzzy_replace(content: str, original: str, replacement: str) -> tuple[str, bool]:
    """
    Replace `original` with `replacement` in `content`, tolerating
    indentation differences.

    Both `original` and `replacement` are stripped and compared by their
    trimmed lines. When a match is found, the replacement lines inherit
    the leading whitespace of the first matched line in the file.

    Returns:
        (new_content, True) if the replacement was applied.
        (content, False) if the original pattern was not found.
    """
    orig_lines = [line.strip() for line in original.strip().split('\n')]
    if not orig_lines:
        return content, False

    content_lines = content.split('\n')
    window_size = len(orig_lines)

    for i in range(len(content_lines) - window_size + 1):
        window = content_lines[i:i + window_size]
        if [line.strip() for line in window] == orig_lines:
            leading_whitespace = re.match(r'^[ \t]*', content_lines[i]).group(0)
            repl_lines = [
                leading_whitespace + line.strip()
                for line in replacement.strip().split('\n')
            ]
            content_lines[i:i + window_size] = repl_lines
            return '\n'.join(content_lines), True

    return content, False
