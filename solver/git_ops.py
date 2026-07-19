"""
Local git operations, run via subprocess against the already-checked-out
repo on the Actions runner. Kept deliberately simple (shell out to git)
rather than GitPython, since we're just doing branch/add/commit/push.
"""
from __future__ import annotations

import subprocess

# Directories/patterns we never want to send to the model as "context" or
# touch automatically -- keeps token usage sane and avoids the AI editing
# its own workflow, lockfiles, or build artifacts.
IGNORED_PREFIXES = (
    "node_modules/", ".git/", "dist/", "build/", ".next/", "__pycache__/",
    ".github/workflows/", "venv/", ".venv/",
)
IGNORED_SUFFIXES = (".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf")


def run(*args: str, check: bool = True) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{result.stderr}")
    return result.stdout.strip()


def get_tracked_files(max_files: int = 300) -> list[str]:
    output = run("git", "ls-files")
    files = [f for f in output.splitlines() if f.strip()]
    filtered = [
        f for f in files
        if not f.startswith(IGNORED_PREFIXES) and not f.endswith(IGNORED_SUFFIXES)
    ]
    return filtered[:max_files]


def read_file(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def write_file(path: str, content: str) -> None:
    import os
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def configure_bot_identity() -> None:
    run("git", "config", "user.name", "ai-issue-solver[bot]")
    run("git", "config", "user.email", "ai-issue-solver-bot@users.noreply.github.com")


def create_branch(branch_name: str) -> None:
    run("git", "checkout", "-b", branch_name)


def commit_and_push(branch_name: str, commit_message: str, changed_paths: list[str]) -> bool:
    """Returns False if there was nothing to commit (e.g. AI produced no diff)."""
    run("git", "add", *changed_paths)
    status = run("git", "status", "--porcelain")
    if not status.strip():
        return False
    run("git", "commit", "-m", commit_message)
    run("git", "push", "--set-upstream", "origin", branch_name)
    return True
