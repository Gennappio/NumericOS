# ADR-0005: Which code a run executes, and when NumericOS may execute at all

- Status: accepted (M3-T02, 2026-10-12)
- Deciders: project owner (priority: observability of code), implementing agent

## Context

`milestones/M3/AGENTS.md` and the reference procedure (`docs/ml-autopilot-reference_SKILL.md`)
require the exact executed source to be recorded: the full commit SHA, the dirty state or a
diff fingerprint that makes it reproducible ("a SHA of an uncommitted worktree alone is not
sufficient"), a branch name never being enough. They forbid changing the user's checked-out
branch, silent cleans, resets, merges and auto-commits, and ask for explicit trust before
project code is executed. The worktree-per-task policy concerns coding agents, which do not
exist yet (ADR-0004).

## Decisions

1. **A run executes an exact commit by default (`code.mode: ref`).** The ref (the protocol's
   default, or the `code_ref` of the submission) is resolved to a full SHA when the run is
   created. From then on the branch may move: the run executes that commit. The files come from
   `git archive` of the SHA, exported into the run's own directory, never from the user's
   working tree. The run is clean by construction. Whether the working tree had uncommitted
   changes at submission is recorded as a fact (`submitted_with_dirty_working_tree`), because
   someone who expected them to run should see that they did not.
2. **A candidate and its baseline differ by commit, not by protocol.** A submission may name the
   commit it executes (`code_ref`), so two runs of one experiment can compare two revisions
   under the same frozen protocol and argument vector.
3. **Running the working tree is an explicit protocol choice (`code.mode: working_tree`).** The
   run then executes in place. When it starts, the supervisor records the commit under the
   tree, the uncommitted changes to tracked files as a binary patch with its SHA-256, and the
   untracked (not ignored) files as digests plus an archive up to 64 MB. Commit, patch and
   archive rebuild the executed tree; a test does exactly that. If the untracked files are too
   large to store, the record says the run is not self-sufficient.
4. **NumericOS only reads the user's repository.** All Git access goes through
   `provenance/git.py`: no checkout, reset, clean, stash, commit or fetch, and
   `GIT_OPTIONAL_LOCKS=0` so that even `git status` does not rewrite the index. Refs are passed
   after `--end-of-options` and can never act as options. A test asserts the index file is
   byte-identical after status and diff.
5. **Reproduction is a first-class operation.** `GET /v1/runs/{id}/record` exports the run with
   its provenance and protocol (`numericos.run-record.v1`). `POST /v1/runs/{id}:rerun` queues a
   run with the same commit, parameters and seed, linked through `reproduces_run_id`. A
   working-tree run cannot be rerun automatically (`NOT_REPRODUCIBLE`): it is rebuilt by hand
   from commit, patch and archive.
6. **Execution needs explicit trust in one directory.** A run executes the project's code with
   the user's permissions. No run can be queued until the project's `root_path` has been
   trusted through an explicit action that repeats the exact path
   (`POST /v1/projects/{id}:trust-execution`, `numericos project trust`). The path must be the
   top of a Git work tree. Changing `root_path` withdraws the trust; it can also be revoked.
   Trust is recorded as events.
7. **Inputs and environment are recorded when a run starts.** Declared input files are hashed
   and, if the protocol states a SHA-256, enforced. The environment record holds host facts,
   the resolved program file with its digest, the outputs of the protocol's probe commands and
   the run's variables. A run gets a small base environment plus what the protocol declares or
   asks to inherit; values of secret-looking names are passed to the run but redacted in the
   record.

## Consequences

- `git archive` exports what the commit contains: submodule contents and Git LFS objects are
  not part of the export. Projects that need them use `working_tree` mode for now.
- One export per run costs disk space proportional to the tracked tree. It keeps runs isolated
  and makes the executed tree inspectable; sharing exports between runs of one commit is an
  optimisation for later.
- There is no sandbox. Trust means the command runs as the user. Isolation (containers, remote
  execution) is out of scope for M3.
- `root_path` must be the top of the work tree; a project that is a subdirectory of a larger
  repository is not supported yet.
