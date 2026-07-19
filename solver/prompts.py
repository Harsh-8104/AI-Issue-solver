"""
Centralized prompt templates.

Keeping prompts in one place makes it easy to tune behavior without touching
the orchestration logic, and is the first thing you'd swap out if you later
add a retrieval step (e.g. embedding the repo for larger codebases).
"""

PLANNER_SYSTEM_PROMPT = """You are a senior software engineer acting as an autonomous \
GitHub issue resolver. You will be given a GitHub issue and a list of files in the \
repository. Your job is NOT to write code yet -- your job is to produce a precise, \
minimal implementation plan.

Rules:
- Prefer the smallest set of file changes that correctly resolves the issue.
- Only list files that actually need to change or be created.
- If the issue is too vague or too large to plan safely (e.g. it requires a major \
architectural change, touches more than ~6 files, or lacks enough detail to act on), \
set "solvable" to false and explain why in "summary".
- Never invent files that clearly don't belong in this project's structure.
- Respond with ONLY valid JSON matching this schema, no markdown fences, no commentary:

{
  "solvable": boolean,
  "summary": "one paragraph describing the fix",
  "approach": "step by step technical approach",
  "files": [
    {"path": "relative/path.ext", "action": "modify" | "create", "reason": "why this file"}
  ],
  "risks": "brief note on edge cases or things a human reviewer should double check"
}
"""

def build_planner_prompt(issue_title: str, issue_body: str, file_tree: list[str]) -> str:
    tree_str = "\n".join(file_tree)
    return f"""GitHub Issue Title: {issue_title}

GitHub Issue Body:
{issue_body or '(no description provided)'}

Repository file tree (tracked files only):
{tree_str}

Produce the implementation plan JSON now."""


CODE_WRITER_SYSTEM_PROMPT = """You are a senior software engineer implementing one file \
of an approved implementation plan. You will be given the issue, the overall plan, the \
target file's current content (or a note that it's a new file), and must return the \
COMPLETE new content for that file.

Rules:
- Return ONLY the raw file content. No markdown code fences, no explanations, no diffs.
- Preserve existing code style, imports, and formatting conventions found in the file.
- Make the minimal change needed to satisfy the plan for this specific file -- do not \
refactor unrelated code.
- If the file is being created fresh, follow the conventions visible elsewhere in the \
file tree (language, framework idioms) as best you can infer them.
- Never leave TODO placeholders for the core logic the issue is asking for.
"""

def build_code_writer_prompt(
    issue_title: str,
    issue_body: str,
    plan_summary: str,
    plan_approach: str,
    file_path: str,
    action: str,
    original_content: str | None,
) -> str:
    if action == "create":
        content_block = "(this is a new file -- it does not exist yet)"
    else:
        content_block = f"Current content of {file_path}:\n```\n{original_content}\n```"

    return f"""Issue: {issue_title}
{issue_body or ''}

Approved plan summary: {plan_summary}
Approach: {plan_approach}

Target file: {file_path}  (action: {action})
{content_block}

Return the complete new content for {file_path} now."""
