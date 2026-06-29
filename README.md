# pr-workflow

Automates replicating a fix across multiple release branches and opening a pull
request for each one.

You make your changes once on a develop branch. This tool collects those
commits, cherry-picks them onto each configured release branch, pushes every
branch to `origin`, and opens a PR per branch with `gh`. Progress is checkpointed
to disk, so an interrupted run (or a cherry-pick conflict) can be resumed from
where it stopped.

## How it works

The workflow advances each branch through a series of steps:

```
init → commit / cherry_pick → origin_sync → pull_request → complete
```

- **init** – On the develop branch, gather every commit since the recorded
  baseline (`commit0`). On a release branch, cherry-pick the develop commits.
- **origin_sync** – Push the branch to `origin` with upstream tracking.
- **pull_request** – Open a PR via `gh pr create`, targeting the branch's base.
- **complete** – Print a summary.

State lives in `local/.workflow_state.json` and is saved after every step. Re-run
the tool to continue; it picks up the current branch and step. When the develop
branch gains new commits after release branches already exist, re-running detects
them and re-applies to each release branch (`check_updates`).

## Requirements

- Python ≥ 3.12
- [`gh`](https://cli.github.com/) CLI, authenticated, for PR creation
- A repo with an `origin` remote
- Dependencies: `gitpython`, `rich`

## Setup

```bash
uv sync
```

## Usage

Run from the root of the target git repository:

```bash
uv run pr_workflow
```

On the first run it prompts for:

- **Develop branch** – where your changes live (default: `develop`)
- **Release branches** – comma-separated list to replicate the fix onto
- **JIRA bug ID** – used to name branches (`<bug_id>_<base>`) and PR titles
- **PR title**

PR bodies are read from a `pr.self.md` file in the working directory; create it
before the `pull_request` step.

### Resuming

The working tree must be clean (no uncommitted or untracked changes) before a
run — the tool aborts otherwise. If a cherry-pick conflicts, resolve it, commit,
and re-run to continue.

PR titles are generated as:

```
[<base>][<bug_id>] <pr_title>
```

## State file

`local/.workflow_state.json` tracks the bug ID, develop/release branches, and
per-branch progress (state, base, applied commits, PR URL). Delete it to start
over.
