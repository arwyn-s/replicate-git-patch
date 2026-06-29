import atexit
from typing import Literal, TypedDict, final
import os
import logging
from git import Repo, GitCommandError
from pathlib import Path
from rich.logging import RichHandler
from rich.status import Status
from rich.prompt import Prompt
import json

logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler()])

log = logging.getLogger("rich")

spinner = Status("Processing...", spinner="line2")

WorkflowStep = Literal[
    "init", "commit", "cherry_pick", "origin_sync", "pull_request", "complete"
]


class BranchState(TypedDict):
    name: str
    state: WorkflowStep
    base: str
    commits: list[str]
    commit0: str
    pr_id: str | None


class MainState(TypedDict):
    branch_states: dict[str, BranchState]
    bug_id: str | None
    release_branches: list[str]
    develop_branch: str
    current_branch: str | None
    pr_title: str
    pr_hash: str | None


@final
class WorkflowEngine:
    """Executes workflow steps"""

    def __init__(self, repo: Repo, state: BranchState, ref: MainState):
        self.repo = repo
        self.state = state
        self.ref = ref

    def check_update(self) -> None:
        """Rerun the current step"""
        log.info(
            f"Rerunning step '{self.state['state']}' for branch '{self.state['name']}'..."
        )
        gonext = self._step_commit_or_cherry_pick()
        self.state["state"] = "complete"
        if gonext:
            self._step_push_origin()
            self.state["state"] = "complete"

    def execute_step(self) -> bool:
        """Execute a workflow step. Returns True if successful, False if needs retry"""
        step = self.state["state"]
        try:
            if step == "init":
                return self._step_commit_or_cherry_pick()
            elif step == "commit":
                return self._step_push_origin()
            elif step == "cherry_pick":
                return self._step_push_origin()
            elif step == "origin_sync":
                return self._step_create_prs()
            elif step == "pull_request":
                return self._step_complete()
            return True
        except Exception as e:
            log.error(f"❌ Error: {e}")
            return False

    def _step_commit_or_cherry_pick(self) -> bool:
        branch_name = self.state["name"]
        ref_branch = self.ref["branch_states"][self.ref["develop_branch"]]
        if branch_name == ref_branch["name"] and self.state[
            "commit0"
        ] == self.repo.git.rev_parse("HEAD"):
            log.info(f"Commit changes to '{branch_name}'...")
            return False
        if (
            branch_name == ref_branch["name"]
            and len(self.state["commits"]) > 0
            and self.state["commits"][-1] == self.repo.git.rev_parse("HEAD")
        ):
            log.info(f"Commit are upto date in '{branch_name}'")
            return False
        if branch_name == ref_branch["name"]:
            # find all the commits since commit0
            commit0 = self.state["commit0"]
            spinner.update(f"Collecting commits since {commit0[:8]}...")
            commits = list(self.repo.iter_commits(f"{commit0}..HEAD"))
            commits.reverse()
            commit_hashes = [c.hexsha for c in commits]
            self.state["commits"] = commit_hashes
            self.state["state"] = "commit"
            log.info(f"✓ Collected {len(commit_hashes)} commits")
            return True
        log.info(f"Cherry-picking commits to '{branch_name}'...")
        if len(ref_branch["commits"]) > 0 and ref_branch["commits"][
            -1
        ] == self.repo.git.rev_parse("HEAD"):
            log.info(f"✓ Commits are upto date in '{branch_name}'")
            return False
        for commit in ref_branch["commits"]:
            if commit in self.state["commits"]:
                log.info(f"✓ Commit {commit[:8]} already cherry-picked, skipping")
                continue
            log.info(f"Cherry-picking commit {commit[:8]}...")
            try:
                spinner.update(f"Cherry-picking commit {commit[:8]}...")
                self.repo.git.cherry_pick(commit)
                self.state["commits"].append(commit)
            except GitCommandError as e:
                log.info("⚠️  Conflicts detected!")
                log.error(e)
                return False
        self.state["state"] = "cherry_pick"
        return True

    def _step_push_origin(self) -> bool:
        branch_name = self.state["name"]
        spinner.update(f"Pushing branch '{branch_name}' to origin...")
        origin = self.repo.remote("origin")
        origin.push(branch_name, set_upstream=True)
        log.info(f"✓ Pushed to origin/{branch_name}")
        self.state["state"] = "origin_sync"
        return True

    def _step_create_prs(self) -> bool:
        """Step 14: Create PRs using gh CLI"""
        # Check for description file
        description_file = "pr.self.md"
        description_path = Path(description_file)
        if self.state.get("pr_id"):
            log.info(f"✓ PR already created: {self.state['pr_id']}")
            self.state["state"] = "pull_request"
            return True
        if not description_path.exists():
            log.info(f"⚠️  Description file '{description_file}' not found.")
            return False

        try:
            import subprocess

            title = (
                f"[{self.state['base']}][{self.ref['bug_id']}] {self.ref['pr_title']}"
            )
            spinner.update(
                f"Creating PR for branch '{self.state['name']}' with title '{title}'..."
            )
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    self.state["base"],
                    "--title",
                    title,
                    "--body-file",
                    description_path,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # Extract PR URL from output
                pr_url = result.stdout.strip().split("\n")[-1]
                log.info(f"✓ Created PR: {pr_url}")
                self.state["pr_id"] = pr_url
            else:
                log.error(f"❌ Failed to create PR: {result.stderr}")
                return False

            self.state["state"] = "pull_request"
            return True

        except Exception as e:
            log.error(f"❌ Error creating PRs: {e}")
            return False

    def _step_complete(self) -> bool:
        """Final step"""
        log.info("\n🎉 Workflow completed successfully!")
        log.info("\n📊 Summary:")
        log.info(f"  Name: {self.state.get('name')}")
        log.info(f"  Base branch: {self.state.get('base')}")
        log.info(f"  Commits applied: {len(self.state.get('commits', []))}")
        log.info(f"  PR created: {self.state.get('pr_id')}")
        self.state["state"] = "complete"
        return True


@final
class WorkflowState:
    """Manage workflow state across steps"""

    def __init__(self, state_file: str = "local/.workflow_state.json"):
        self.repo = Repo(".")
        self.state_file = state_file
        self.state: MainState = self._load_state()
        spinner.start()
        atexit.register(spinner.stop)

    def _load_state(self) -> MainState:
        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as f:
                return json.load(f)
        return {
            "branch_states": {},
            "bug_id": None,
            "release_branches": [],
            "develop_branch": "develop",
            "current_branch": None,
            "pr_hash": None,
            "pr_title": "",
        }

    def save(self):
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def init(self, name: str, base: str, last_commit: str):
        self.state["branch_states"][name] = {
            "name": name,
            "state": "init",
            "base": base,
            "commits": [],
            "commit0": last_commit,
            "pr_id": None,
        }
        self.save()

    def clear(self):
        self.state = {
            "branch_states": {},
            "bug_id": None,
            "release_branches": [],
            "develop_branch": "develop",
            "current_branch": None,
            "pr_title": "",
            "pr_hash": None,
        }
        if os.path.exists(self.state_file):
            os.remove(self.state_file)

    def initialize(self):
        spinner.stop()
        develop_branch = Prompt.ask(
            "Enter develop branch name", default="develop"
        ).strip()

        release_branches = Prompt.ask("Enter release branches (comma-separated)").split(
            ","
        )
        release_branches = [b.strip() for b in release_branches if b.strip()]

        bug_id = Prompt.ask("Enter JIRA bug ID").strip()

        pr_title = Prompt.ask("Enter PR title").strip()

        self.state["bug_id"] = bug_id
        self.state["release_branches"] = release_branches
        self.state["develop_branch"] = develop_branch
        self.state["pr_title"] = pr_title
        self.save()
        spinner.start()
        return self

    def new_branch_workflow(self, base: str):
        name = f"{self.state['bug_id']}_{base}"
        spinner.update(f"Checking out to base branch '{base}'...")
        self.repo.git.checkout(base)
        spinner.update(f"Pulling latest changes for '{base}' from origin...")
        origin = self.repo.remote("origin")
        origin.pull(base)
        spinner.update(f"Creating new branch '{name}' from '{base}'...")
        self.repo.git.checkout(name, b=True)
        commit0 = self.repo.git.rev_parse("HEAD")
        branch: BranchState = {
            "name": f"{self.state['bug_id']}_{base}",
            "state": "init",
            "base": base,
            "commits": [],
            "commit0": commit0,
            "pr_id": None,
        }
        self.state["current_branch"] = base
        self.state["branch_states"][base] = branch
        self.save()
        return WorkflowEngine(self.repo, branch, self.state)

    def sanitize(self):
        if self.repo.is_dirty(untracked_files=True):
            log.error(
                "current branch is dirty, please commit or stash changes first",
            )
            raise
        current_branch = self.state.get("current_branch")
        if current_branch:
            branch = self.state["branch_states"].get(current_branch)
            if (
                branch is not None
                and branch.get("name") != self.repo.active_branch.name
            ):
                log.error(
                    f"i'm confused, current branch-{branch['name']} in state does not match repo-{self.repo.active_branch.name}"
                )
                raise

    def reset(self):
        spinner.update("Resetting workflow state to dev branch...")
        self.state["current_branch"] = self.state["develop_branch"]
        tobranch = self.state["branch_states"][self.state["develop_branch"]]["name"]
        self.save()
        self.repo.git.checkout(tobranch)
        log.info(f"Checked out to branch '{tobranch}'")

    def current(self):
        branch_name = self.state.get("current_branch")
        log.info(f"Current branch in state: {branch_name}")
        if not branch_name:
            log.error("No current branch in state")
            return self.new_branch_workflow(self.state["develop_branch"])
        branch = self.state["branch_states"].get(branch_name)
        if not branch:
            return self.new_branch_workflow(branch_name)
        repo = Repo(".")
        return WorkflowEngine(repo, branch, self.state)

    def next(self):
        if self.state["current_branch"] is None:
            return self.new_branch_workflow(self.state["develop_branch"])
        release_branches = self.state["release_branches"]
        for branch in release_branches:
            if branch not in self.state["branch_states"]:
                return self.new_branch_workflow(branch)
        self.reset()
        return None

    def check_updates(self, engine: WorkflowEngine) -> bool:
        if engine.state["state"] != "complete":
            return False
        try:
            if engine.state["base"] != self.state["develop_branch"]:
                log.info(
                    f"Skipping update check for branch '{engine.state['name']}' as it is not the develop branch."
                )
                return True
            engine.check_update()
            self.state["branch_states"][engine.state["base"]] = engine.state
            self.save()
            for branch in self.state["release_branches"]:
                if branch in self.state["branch_states"]:
                    self.repo.git.checkout(self.state["branch_states"][branch]["name"])
                    nengine = WorkflowEngine(
                        self.repo, self.state["branch_states"][branch], self.state
                    )
                    nengine.check_update()
                    self.state["branch_states"][nengine.state["base"]] = nengine.state
                    self.save()
            self.reset()
        except Exception as e:
            log.error(f"❌ Error during update check: {e}")
        return True

    def run(self, engine: WorkflowEngine):
        gonext = False
        while True:
            log.info(
                f"Executing step '{engine.state['state']}' for branch '{engine.state['name']}'..."
            )
            success = engine.execute_step()
            self.state["branch_states"][engine.state["base"]] = engine.state
            self.save()
            if success:
                if engine.state["state"] == "complete":
                    log.info(f"Workflow for ${engine.state['name']} is complete.")
                    gonext = True
                    break
            if not success:
                log.info("Please resolve issues and press Enter to retry...")
                gonext = False
                break
        if not gonext:
            return
        next = self.next()
        if next:
            self.run(next)


def main():
    workflow = WorkflowState()
    workflow.sanitize()
    state = workflow.state
    if state["current_branch"] is None:
        workflow.initialize()
    engine = workflow.current()
    if not workflow.check_updates(engine):
        workflow.run(engine)


if __name__ == "__main__":
    main()
