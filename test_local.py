import os
import sys
import json
from typing import List
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

class ReviewIssue(BaseModel):
    file: str = Field(description="The relative path to the file containing the issue.")
    line: int = Field(description="The line number (1-indexed) in the file where the issue is. MUST be a valid line number in the current version of the file.")
    severity: str = Field(description="Vulnerability severity. Allowed values: CRITICAL, HIGH, WARNING, INFO.")
    issue_name: str = Field(description="Short name of the issue, e.g. SQL Injection.")
    description: str = Field(description="Detailed explanation of the bug, risk, and remediation.")
    original_code: str = Field(description="The exact lines of code in the file that need to be replaced. Must match exactly. Leave empty if no automatic fix is possible.")
    suggested_fix: str = Field(description="The corrected code block to replace original_code. Leave empty if no automatic fix is possible.")

class ReviewReport(BaseModel):
    issues: List[ReviewIssue]

def apply_local_fixes(issues):
    fixed_any = False
    for issue in issues:
        if not issue.original_code or not issue.suggested_fix:
            continue
            
        file_path = issue.file
        # Local test might run from different path, resolve file
        if not os.path.exists(file_path):
            file_path = os.path.basename(file_path)
            
        if not os.path.exists(file_path):
            print(f"⚠️ Warning: File {issue.file} not found locally. Skipping local auto-fix.")
            continue
            
        try:
            with open(file_path, "r") as f:
                content = f.read()
                
            if issue.original_code in content:
                print(f"🔧 [Local Fix] Auto-fixing '{issue.issue_name}' in {file_path}...")
                content = content.replace(issue.original_code, issue.suggested_fix, 1)
                with open(file_path, "w") as f:
                    f.write(content)
                fixed_any = True
            else:
                print(f"⚠️ Warning: Could not apply auto-fix to {file_path}: original_code pattern not found in file.")
        except Exception as e:
            print(f"❌ Error applying auto-fix to {file_path}: {e}")
            
    return fixed_any

def run_local_test():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY environment variable not set.")
        print("\nTo test, please run this in your terminal first:")
        print("export GEMINI_API_KEY='your_actual_api_key_here'")
        print("\nThen run this script again.")
        sys.exit(1)

    target_file = sys.argv[1] if len(sys.argv) > 1 else "sample_iot_app.py"
    
    print(f"📄 Reading {target_file}...")
    try:
        with open(target_file, "r") as f:
            code_content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: {target_file} not found.")
        sys.exit(1)

    # Simulate diff
    diff_text = f"--- /dev/null\n+++ b/{target_file}\n"
    for line in code_content.splitlines():
        diff_text += f"+{line}\n"

    print("🤖 Initializing Gemini Client...")
    client = genai.Client(api_key=api_key)

    prompt = f"""
You are "AegisPR", an AI-driven Code Review agent specialized in Open-Source Software and IoT applications.
Your task is to analyze the following Pull Request diff for complex logical bugs and security vulnerabilities.

Focus heavily on:
1. IoT-specific vulnerabilities (e.g., hardcoded credentials, buffer overflows, insecure communication, command injection).
2. Logical flaws that standard static analysis tools might miss.
3. Edge cases and error handling.

For each issue found, populate the response schema:
- Set 'severity' to CRITICAL, HIGH, WARNING, or INFO.
- Provide the exact filename and line number.
- To enable automatic fixing, provide the 'original_code' (the exact text to replace) and 'suggested_fix' (the drop-in replacement). If the original_code does not match the file contents exactly, the auto-fix will fail.
- If no issues are found, return an empty list of issues.

Here is the diff:
```diff
{diff_text}
```
"""

    import time
    
    models_to_try = ['gemini-3.5-flash', 'gemini-2.5-flash', 'gemini-1.5-flash']
    response = None
    success = False

    print("🧠 Sending code to Gemini for review. This might take a few seconds...\n")
    print("-" * 50)
    
    for model_name in models_to_try:
        retry_delay = 5
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ReviewReport,
                    )
                )
                success = True
                break
            except Exception as e:
                print(f"⚠️ Request to {model_name} failed: {e}")
                if attempt < 1:
                    print(f"Retrying {model_name} in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
        if success:
            break
            
    if not success:
        print("❌ Failed to generate review after trying all fallback models.")
        sys.exit(1)
                
    try:
        report_data = json.loads(response.text)
        report = ReviewReport(**report_data)
        
        print("🛡️ **AegisPR Review Report (JSON Schema):**\n")
        print(json.dumps(report_data, indent=2))
        print("-" * 50)
        
        if report.issues:
            print(f"Found {len(report.issues)} issues. Running local auto-fix simulation...\n")
            apply_local_fixes(report.issues)
            
            # Print PR blocking simulation
            has_blocking = any(issue.severity.upper() in ["CRITICAL", "HIGH"] for issue in report.issues)
            if has_blocking:
                print("\n🚨 [Blocking Mode] CI Build Status: FAILED (CRITICAL/HIGH severity issues found)")
            else:
                print("\n✅ [Blocking Mode] CI Build Status: PASSED")
        else:
            print("🎉 No issues found! CI Build Status: PASSED")
            
        print("-" * 50)
    except Exception as e:
        print(f"❌ Failed to parse or validate JSON review: {e}")
        if response and hasattr(response, 'text'):
            print(f"Raw response: {response.text}")

if __name__ == "__main__":
    run_local_test()
