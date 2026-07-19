# AI Issue Solver

An autonomous agent that reads a GitHub issue, drafts an implementation plan,
writes the code, and opens a pull request — triggered directly from a comment
on the issue. Runs entirely on GitHub Actions' free runners with Google's
Gemini API (free tier), so there's no hosting bill.

Built by [Ghost](https://github.com/Harsh-8104).

## How it works

```
Issue comment "/solve"
        │
        ▼
GitHub Action spins up (permission check on commenter)
        │
        ▼
Read issue + repo file tree  ──────►  Gemini: generate implementation plan (JSON)
        │
        ▼
Plan says "not solvable"? ──► comment on issue, stop
        │ (solvable)
        ▼
For each file in plan ──────►  Gemini: generate full new file content
        │
        ▼
Best-effort test run (pytest / npm test) — non-blocking, logged in PR
        │
        ▼
Commit → push branch → open PR referencing the issue → comment with PR link
```

Every run happens on a fresh, disposable GitHub Actions runner — there's no
persistent server, container, or sandbox to manage or pay for.

## Setup

1. **Add secrets** to your repo (Settings → Secrets and variables → Actions):
   - `GEMINI_API_KEY` — from [Google AI Studio](https://aistudio.google.com/apikey), free, no card required.
   - `GITHUB_TOKEN` is provided automatically by Actions, no setup needed.

2. **Drop in the workflow and solver package**:
   ```
   .github/workflows/solve-issue.yml
   solver/
   requirements.txt
   ```

3. **Trigger it** by commenting `/solve` on any issue, or adding the `ai-solve` label.
   Only users with write access to the repo can trigger a run.

## Design decisions (and why)

- **Execution environment: the Actions runner itself.** No Render job, no
  Docker container to maintain. The runner is already ephemeral and free —
  it's the sandbox, at zero extra cost.
- **Full-file rewrites, not diffs.** For v1, Gemini returns the complete new
  content of each changed file rather than a patch. This is far more robust
  against malformed diffs and easier to review — the tradeoff is it doesn't
  scale well to very large files (see Roadmap).
- **Plan-then-code, two-stage prompting.** Separating "what should change and
  why" from "write the actual code" produces a PR description that's
  genuinely useful for review, and gives the model a chance to bail out
  cleanly (`"solvable": false`) on issues that are too vague or too large,
  instead of hallucinating a fix.
- **Non-blocking test execution.** Tests run if a recognizable test command
  exists, and results are posted in the PR body. It doesn't gate the PR yet —
  that's an intentional v1 simplification (see Roadmap).
- **Force-push on the solver branch.** Re-triggering `/solve` on an issue that
  was already attempted (e.g. after a failed prior run) reuses the same
  branch name. Since that branch is exclusively owned by the bot, it's
  force-pushed rather than rejected on a non-fast-forward — the latest
  attempt always wins.

## Current scope (v1)

Handles well:
- Well-defined bugs and small features scoped to a handful of files
- Issues with a clear description, expected behavior, or repro steps

Will decline (mark `"solvable": false` and comment instead of guessing):
- Broad architectural changes
- Issues touching more than ~6 files
- Vague issues lacking enough detail to act on safely

## Scope: which repos can this act on?

By default, **this only works on the repo it's installed in.** The workflow
listens for `/solve` comments on issues in *this* repo alone — it has no
reach into your other projects unless it's explicitly set up there too.
There are three ways to extend that:

**1. Per-repo install (simplest)**
Copy `.github/workflows/solve-issue.yml`, `solver/`, `requirements.txt`, and
`.gitignore` into any other repo, add a `GEMINI_API_KEY` secret there, and it
runs independently. No shared state between repos — just duplicated code.

**2. Reusable workflow (one source of truth)**
Keep the `solver/` package here, and have other repos reference this
workflow instead of copying it:
```yaml
jobs:
  solve:
    uses: Harsh-8104/ai-issue-solver/.github/workflows/solve-issue.yml@main
    secrets: inherit
```
Update the logic once, every repo using it picks up the change automatically.

**3. Published GitHub Action (most reusable)**
Package it with an `action.yml` and publish to the GitHub Marketplace so any
public repo — not just mine — can add it with a few lines of YAML. This is
the natural direction if the goal is a tool other developers can install,
rather than a personal script.

In all three cases, it still only *acts* where it's deliberately triggered —
it's not a bot that scans or roams GitHub on its own; it needs to be added to
a repo and given a valid API key before it can do anything there.

## Roadmap / extensibility hooks already in place

The code is split so each of these can be added without restructuring:

- **Self-correction loop** — `try_run_tests()` in `main.py` already captures
  test failures; feeding that output back into `gemini_client.py` for a
  retry-before-PR loop is a small, contained change.
- **Codebase-aware planning (RAG over the repo)** — `git_ops.get_tracked_files()`
  currently sends a flat file list; swapping in an embeddings index (e.g.
  Gemini embeddings + a vector store) for larger repos is isolated to that
  one function and the planner prompt.
- **Diff-based edits instead of full-file rewrites** — would let it handle
  large files without re-generating the whole thing; isolated to
  `gemini_client.generate_file_content` and `git_ops.write_file`.

## Tech stack

- **Trigger:** GitHub Actions (`issue_comment`, `issues:labeled`)
- **LLM:** Gemini 2.5 Flash via the `google-genai` SDK (free tier)
- **GitHub API:** PyGithub
- **Git operations:** local `git` CLI on the runner
- **Language:** Python 3.12
