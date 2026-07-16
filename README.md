# AegisPR: Enterprise AI-Driven CI/CD Security Agent

<p align="center">
  <img src="aegis_pr_logo.png" alt="AegisPR Logo" width="250"/>
</p>

An enterprise-grade, autonomous AI Code Reviewer and Vulnerability Detection Agent integrated directly into the GitHub CI phase. It is designed to hunt for complex logical bugs, security flaws, and resource leaks in Open-Source Software (OSS) before code deployment.

Unlike standard static analysis tools, AegisPR uses LLM reasoning to evaluate code context, offering smart explanations and **secure auto-fixing** for vulnerabilities like Command Injection, Stack Buffer Overflows, Supply Chain Risks, and Memory Leaks.

---

## 🚀 Enterprise Features

*   **Language-Agnostic Reviews**: Automatically reviews code written in Python, C, C++, JavaScript, and more.
*   **Diff-Aware Scanning**: Only flags vulnerabilities introduced in the exact lines modified in the Pull Request. Zero alert fatigue—developers are never blocked for legacy technical debt!
*   **Fuzzy Auto-Fixer**: Safely injects AI-synthesized patches into your codebase while mathematically adapting to bizarre indentation anomalies and custom styles.
*   **Deep Context Enrichment**: Injects the full contents of vulnerable files into the AI context window, allowing the LLM to understand cross-function dependencies before suggesting fixes.
*   **Semantic Dependency Auditing**: Audits the usage semantics of third-party library imports and manifests (e.g. `Dockerfile`, `requirements.txt`, `package.json`) for insecure configurations or ecosystem CVEs.
*   **Least-Privilege Auto-Fixes**: Integrates a custom safety validator to ensure AI-suggested auto-fixes do not introduce dynamic evaluation (`eval`), unvetted subprocesses, or loose system permissions (`chmod 777`).
*   **API Failover & Throttling**: Automatically fails over between `gemini-3.5-flash`, `gemini-2.5-pro`, and `gemini-2.5-flash` using exponential backoff to handle enterprise rate-limits.
*   **CI/CD Self-Protection**: Prevents infinite CI loops by skipping triggers on bot commits, and gracefully ignores supply-chain fixes inside `.github/workflows` to prevent permission crashes.

---

## 📁 Repository Structure

```text
├── .github/workflows/
│   ├── review.yml          # GitHub Actions workflow trigger for AegisPR
│   └── test.yml            # CI/CD pipeline running PyTest for AegisPR's internal logic
├── src/
│   └── main.py             # Core Python logic for the autonomous agent
├── tests/
│   ├── test_fuzzy_replace.py       # Unit tests for the Fuzzy Matcher algorithm
│   └── test_safety_validator.py    # Unit tests for the Safety Regex logic
├── action.yml              # GitHub Action definition file
├── Dockerfile              # Containerized environment for the Action runner
└── requirements.txt        # Python package dependencies
```

---

## ⛓️ GitHub CI/CD Integration

To run this automatically on every Pull Request in your repository:

### 1. Add the API Key to Secrets
1. Go to your repository settings on GitHub (**Settings** -> **Secrets and variables** -> **Actions**).
2. Click **New repository secret**.
3. Name: `GEMINI_API_KEY`.
4. Value: Paste your Gemini API Key.

### 2. Configure the Workflow
The project includes a pre-configured workflow in `.github/workflows/review.yml` which triggers on PR actions:

```yaml
name: "AI Code Review"

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  ai_review:
    if: github.actor != 'github-actions[bot]' # Prevents infinite CI loops!
    runs-on: ubuntu-latest
    permissions:
      contents: write # Required to push auto-fixes back to the branch
      pull-requests: write # Required for the bot to write PR comments
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4
      
      - name: Run AegisPR
        uses: ./ # Uses action.yml in root
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
```

Whenever a new Pull Request is opened or updated by a human developer, **AegisPR** will review the diff, flag semantic vulnerabilities, and push mathematically sound auto-fixes directly back to the branch!
