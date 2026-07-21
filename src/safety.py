"""
Safety validator for AI-synthesized auto-fix patches.

Enforces deterministic patch cleansing by blocking dangerous patterns
that an LLM might introduce: dynamic evaluation, unvetted sub-processes,
loose permissions, unsafe deserialization, and obfuscated imports.
"""

import re


def is_suggested_fix_safe(suggested_fix: str) -> tuple[bool, str]:
    """
    Validate that an AI-synthesized fix does not introduce dangerous patterns.

    Returns:
        (True, "") if the fix is safe.
        (False, reason) if the fix contains a blocked pattern.
    """
    # 1. Dynamic evaluations
    dynamic_eval_patterns = [
        (r'\b(eval|exec)\s*\(', "raw dynamic evaluation block ('eval' or 'exec')"),
        (r'\b__import__\s*\(', "obfuscated dynamic import via __import__()"),
    ]
    for pattern, description in dynamic_eval_patterns:
        if re.search(pattern, suggested_fix, re.IGNORECASE):
            return False, f"Suggested fix contains {description}."

    # 2. Unvetted sub-processes or command execution
    subprocess_patterns = [
        (
            r'\b(os\.system|os\.popen|os\.spawn|pty\.spawn)\b',
            "unvetted sub-process or command execution",
        ),
        (
            r'\bshell\s*=\s*True\b',
            "shell=True subprocess execution (command injection risk)",
        ),
    ]
    for pattern, description in subprocess_patterns:
        if re.search(pattern, suggested_fix, re.IGNORECASE):
            return False, f"Suggested fix contains {description}."

    # 3. Unsafe deserialization
    deserialization_patterns = [
        (r'\bpickle\.(loads?|Unpickler)\s*\(', "unsafe pickle deserialization"),
        (r'\bmarshal\.loads?\s*\(', "unsafe marshal deserialization"),
        (
            r'\byaml\.load\s*\([^)]*\)',
            "yaml.load() without SafeLoader (use yaml.safe_load())",
        ),
    ]
    for pattern, description in deserialization_patterns:
        match = re.search(pattern, suggested_fix)
        if match:
            # Allow yaml.load if SafeLoader/CSafeLoader is explicitly specified
            if 'yaml.load' in (match.group(0) if match else ''):
                if re.search(r'Loader\s*=\s*(yaml\.)?(Safe|CSafe)Loader', suggested_fix):
                    continue
            return False, f"Suggested fix contains {description}."

    # 4. Loose system/file permissions
    permission_patterns = [
        (r'\b0[oO]?[0-7]*[7]{2,}[0-7]*\b', "highly permissive octal permissions (e.g. 777)"),
        (r'\b777\b', "highly permissive numeric permissions (777)"),
        (
            r'\b(stat\.S_IRWXO|stat\.S_IRWXG)\b',
            "loose group/other read-write-execute permissions",
        ),
    ]
    for pattern, description in permission_patterns:
        if re.search(pattern, suggested_fix):
            return False, f"Suggested fix contains {description}."

    return True, ""
