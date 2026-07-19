"""
Entry point: `python -m solver.main`

Flow:
  1. Fetch the triggering issue.
  2. Get repo file tree (local git, no extra API calls).
  3. Ask Gemini for an implementation plan (JSON).
  4. If the model says it's not confidently solvable -> comment and stop.
  5. Create a branch, ask Gemini to write each file in the plan, apply changes.
  6. Best-effort test run (non-blocking) so reviewers get a signal in the PR.
  7. Commit, push, open a PR that references the issue, comment back on the issue.
"""
from __future__ import annotations

import os
import subprocess
import sys

from solver.git_ops import (
    commit_and_push,
    configure_bot_identity,
    create_branch,
    get_tracked_files,
    read_file,
    write_file,
)
from solver.github_client import GitHubClient
from solver.gemini_client import GeminiClient


def try_run_tests() -> str:
    """
    Best-effort test execution. Non-blocking by design for v1 -- results are
    surfaced in the PR body for a human to check, rather than gating the PR.
    This is the natural place to plug in a self-correction loop later:
    on failure, feed stderr back to Gemini and retry before opening the PR.
    """
    candidates = [
        (["pytest", "-q"], "pytest.ini,setup.cfg,pyproject.toml"),
        (["npm", "test", "--silent"], "package.json"),
    ]
    for cmd, marker_files in candidates:
        markers = marker_files.split(",")
        if any(os.path.exists(m) for m in markers):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                status = "✅ passed" if result.returncode == 0 else "❌ failed"
                tail = (result.stdout + result.stderr)[-1500:]
                return f"Ran `{' '.join(cmd)}` -- {status}\n\n```\n{tail}\n```"
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                return f"Ran `{' '.join(cmd)}` -- timed out after 180s (not blocking the PR)."
    return "No recognized test command found -- skipped automated test run."


def main() -> int:
    issue_number = int(os.environ["ISSUE_NUMBER"])
    gh = GitHubClient()
    gemini = GeminiClient()

    issue = gh.get_issue(issue_number)
    print(f"Solving issue #{issue_number}: {issue.title}")

    file_tree = get_tracked_files()
    plan = gemini.generate_plan(issue.title, issue.body or "", file_tree)

    if not plan.get("solvable", False):
        gh.comment_on_issue(
            issue_number,
            "🤖 I looked into this issue but don't have a confident, minimal plan "
            f"for it yet.\n\n**Why:** {plan.get('summary', 'Not enough detail to act on.')}\n\n"
            "This usually means the issue needs more specifics (exact file, expected "
            "behavior, reproduction steps) or is broad enough to need human design "
            "input first. Feel free to add detail and re-trigger with `/solve`.",
        )
        print("Plan marked not solvable. Exiting cleanly.")
        return 0

    files_plan = plan.get("files", [])
    if not files_plan:
        gh.comment_on_issue(issue_number, "🤖 I couldn't identify any files to change for this issue.")
        return 0

    branch_name = f"ai-solver/issue-{issue_number}"
    configure_bot_identity()
    create_branch(branch_name)

    changed_paths = []
    for file_entry in files_plan:
        path = file_entry["path"]
        action = file_entry.get("action", "modify")
        original = read_file(path) if action == "modify" else None

        new_content = gemini.generate_file_content(
            issue.title, issue.body or "", plan["summary"], plan.get("approach", ""),
            path, action, original,
        )
        write_file(path, new_content)
        changed_paths.append(path)
        print(f"Wrote {path} ({action})")

    test_summary = try_run_tests()

    commit_message = f"AI fix for #{issue_number}: {issue.title}"
    pushed = commit_and_push(branch_name, commit_message, changed_paths)

    if not pushed:
        gh.comment_on_issue(
            issue_number,
            "🤖 I generated a plan but the resulting changes were identical to the "
            "current code, so there's nothing to open a PR for. The issue may already "
            "be resolved, or needs a more specific description.",
        )
        return 0

    pr_body = f"""## Summary
{plan['summary']}

## Approach
{plan.get('approach', '')}

## Files changed
{chr(10).join(f"- `{f['path']}` ({f['action']}) -- {f.get('reason', '')}" for f in files_plan)}

## Risks / things to double check
{plan.get('risks', 'None noted.')}

## Automated test run
{test_summary}

---
Closes #{issue_number}
_Opened automatically by AI Issue Solver. Please review before merging -- this PR was not human-written._
"""

    pr = gh.create_pull_request(
        title=f"AI fix: {issue.title}",
        body=pr_body,
        head_branch=branch_name,
    )

    gh.comment_on_issue(issue_number, f"🤖 Opened a PR with a proposed fix: {pr.html_url}")
    print(f"Opened PR: {pr.html_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
