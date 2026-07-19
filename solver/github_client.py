"""
Wrapper around PyGithub for the issue/PR/comment side of things.
Repo file mutations happen locally via git_ops.py instead -- it's more
reliable than pushing individual file blobs through the REST API.
"""
from __future__ import annotations

import os

from github import Github


class GitHubClient:
    def __init__(self, token: str | None = None, repo_full_name: str | None = None):
        self.gh = Github(token or os.environ["GITHUB_TOKEN"])
        self.repo = self.gh.get_repo(repo_full_name or os.environ["GITHUB_REPOSITORY"])

    def get_issue(self, issue_number: int):
        return self.repo.get_issue(number=issue_number)

    def comment_on_issue(self, issue_number: int, body: str) -> None:
        self.get_issue(issue_number).create_comment(body)

    def create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        draft: bool = False,
    ):
        try:
            return self.repo.create_pull(
                title=title, body=body, head=head_branch, base=base_branch, draft=draft,
            )
        except Exception:
            # Common cause: default branch isn't "main" (e.g. "master")
            default_branch = self.repo.default_branch
            if default_branch != base_branch:
                return self.repo.create_pull(
                    title=title, body=body, head=head_branch,
                    base=default_branch, draft=draft,
                )
            raise
