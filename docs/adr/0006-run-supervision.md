# ADR-0006: One monitor process per run, and a worker that turns its files into durable state

- Status: accepted (M3-T03, 2026-10-12)
- Deciders: project owner (priority: observability of experiments), implementing agent

## Context

`milestones/M3/AGENTS.md` asks for a real, long-lived local supervisor: not a coroutine tied to
a request, no child orphaned by accident, argument vectors instead of shell lines, incremental
capture of output, limits, a process identity made of PID and start time, group-aware
cancellation, runs that survive an API restart, and after a supervisor restart either a safe
reconciliation or an honest `lost`, never an invented success.

A single daemon that owns the pipes of its children cannot meet the last two requirements. When
it dies, the pipes close: output is lost, the limits are no longer enforced, and nobody records
how the program ends. The program goes on unobserved and unbounded, which is exactly what must
not happen.

## Decisions

1. **Two kinds of process.** A **monitor** exists once per run. It starts the program in its
   own process group, records every output line with its arrival time and stream, samples the
   resources of the whole process tree, enforces the limits, obeys a cancellation request and
   finally records how the program ended. It writes files only: no database, no network. It is
   detached from whoever started it. A **worker** (`numericos worker run`) is the supervisor
   proper: it serves the queue, prepares each run (code, inputs, environment, the monitor's
   specification), starts monitors, turns what they write into run state and ledger events, and
   takes over runs whose worker is gone. The API executes nothing.
2. **The run directory is the contract between them** (`<data_dir>/runs/<run_id>/`).
   Line-oriented records (`output.jsonl`, `resources.jsonl`, `journal.jsonl`) are append-only
   and read by byte offset; documents (`spec.json`, `monitor.json`, `started.json`,
   `exit.json`, `cancel.json`) are written atomically. Whoever is alive can continue from the
   files, so a worker keeps nothing about a run only in memory. `spec.json` holds the real
   environment of the run and is readable by the user only (mode 0600).
3. **A process is its PID and its start time.** A PID alone is reused by the operating system;
   every liveness check compares both.
4. **A run directory has exactly one monitor.** A monitor names itself by creating
   `monitor.json` exclusively. Of two monitors started for one run by mistake, one gets the
   name and the other leaves without starting anything.
5. **Stopping a program** means SIGTERM to its process group, SIGKILL after the grace period
   of the protocol, and after the program has ended the same for whatever is left in its
   group. The limits are the wall clock (mandatory), the resident memory summed over the
   process tree, and the size of the stored output (beyond it lines are still counted, not
   stored, and the run says so). A stop is recorded as the reason of the end only if it had
   an effect: a limit that passes, or a request that arrives, after the program already ended
   by itself does not rewrite how it ended.
6. **Status says how the program ended, nothing more.**

   | What the monitor recorded | Status | Failure class |
   | --- | --- | --- |
   | ended by itself with exit code 0 | `succeeded` | none |
   | ended by itself with another exit code, or by SIGSEGV, SIGFPE, SIGABRT and the like | `failed` | `code_error` |
   | killed by a signal that NumericOS did not send | `failed` | `unknown` |
   | a build command failed, or the program could not be started | `failed` | `code_error` |
   | wall-clock limit | `timed_out` | `resource_limit` |
   | memory limit | `failed` | `resource_limit` |
   | a numerical guardrail asked for the stop (M3-T04) | `failed` | `numerical_instability` |
   | cancellation, or the monitor itself was told to stop | `cancelled` | none |
   | a declared input is missing or not the expected file | `failed` | `data_problem` |
   | code export, trust withdrawn, monitor could not start, monitor failed | `failed` | `infrastructure` |
   | no monitor, no program and no recorded outcome | `lost` | `unknown` |

   `succeeded` is a statement about a process. Whether the result is valid is decided by
   validators (M3-T05) and is stored elsewhere.
7. **Recovery decides only what is certain.** A worker takes over the active runs of a worker
   that said it stopped, or that has been silent for 15 seconds, and continues from the files
   (`RUN_ADOPTED`). A claimed run for which no monitor ever named itself is queued again after
   10 seconds: nothing was executed (`RUN_REQUEUED`). If the monitor is gone while the program
   is alive, the run stays `running` and says that its end will not be recorded
   (`RUN_MONITOR_LOST`). If both are gone and no outcome was recorded, the run is `lost`.
   Success is never inferred.
8. **No automatic retry.** The only repetition is the re-queue of a run whose program was never
   started, and it is an event. A failed run is repeated by a person or an agent
   (`POST /v1/runs/{id}:rerun`), which creates a new run linked to the first.
9. **Short, fenced transactions.** The worker reads files and Git between transactions, never
   inside one, so hashing the results of a run does not keep the API from writing. Every write
   is applied only if the run still belongs to this worker and is as the worker found it;
   otherwise the reading is dropped and repeated in the next round. The heartbeat has its own
   thread: a worker that is busy preparing a run is not taken for a dead one.
10. **Cancellation is a recorded intent plus a file.** The API records
    `RUN_CANCEL_REQUESTED` with the reason, writes `cancel.json` and returns at once. A queued
    run is cancelled immediately. A running one becomes `cancelled` when its monitor reports
    that the program is gone. The worker repeats the file from the recorded intent, so a
    request is not lost with a failed file write.
11. **Observation is read by cursor.** Output and resource samples are served from the run's
    files by byte offset, with `has_more` and `complete`; `complete` means the run ended and
    everything was returned. Events come from the ledger. The API notices commits made by the
    worker through SQLite's `data_version` (`events/watcher.py`) and wakes its stream
    subscribers, so run events reach an open stream without waiting for the heartbeat.
12. **What a run leaves is registered when it ends**, with size and SHA-256: the monitor's
    records, the provenance files, the probe outputs, the files under `outputs/`
    (`$NUMERICOS_OUTPUT_DIR`) and, for a run of an exported commit, the files the program
    created or changed next to its sources. The latter are told apart by a stamp the monitor
    touches just before the program starts: the commit's own files and what the build produced
    are older. At most 1000 result files are listed and the finishing event says how many were
    not.
13. **The program file is identified when the program starts**, after the build commands, so a
    compiled program is recorded as the binary that actually ran.
14. **A measurement is exact where the system offers it, and labelled where it is sampled.**
    The program is reaped with `wait4`, which reports the CPU time and the largest resident set
    of the program and of the descendants it waited for, apart from the build commands. Its
    wall time ends when its exit is noticed, which a `SIGCHLD` wake-up makes immediate, and is
    kept apart from the duration of the whole run, which is what the wall-clock limit bounds.
    The samples of the process tree are a second, approximate view: each covers the interval
    since the previous one, and a run shorter than the interval has none. Records and commands
    always say which of the two a number is.
15. **A run does not inherit the environment NumericOS runs in.** Besides the base variables,
    what the protocol declares and what it asks to inherit, nothing reaches the program, and
    the directory of NumericOS's own Python environment is removed from the inherited `PATH`.

## Consequences

- One host. Remote executors and schedulers belong to M5.
- Limits are enforced by observation, not by the kernel: memory is checked at the sampling
  interval (0.2 s at the fastest), so a fast allocation can overshoot before the run is
  stopped. There is no limit on CPU cores or GPUs, no cgroup and no sandbox.
- If the host goes down, monitors go down with it. After the restart their runs are `lost`.
  This was tested by killing processes, not by cutting power.
- What a program writes after its monitor died is not recorded, and the program will usually
  be ended by the broken pipe the next time it writes.
- A worker whose whole process is suspended for more than 15 seconds is taken for dead and its
  runs are adopted. That is harmless for running programs. A run that was being prepared at
  that moment can fail with an infrastructure error instead of starting; it is never started
  twice.
- Every run of an exported commit keeps its export, so disk use grows with the tracked tree
  per run. Nothing is pruned yet.
- A run in the working tree writes into the project's own directory. Only what it puts under
  `$NUMERICOS_OUTPUT_DIR` is registered as a result.
- Values written in `execution.env` are part of the contract and are stored as written. A
  secret is passed with `inherit_env`: its value then exists only in the supervisor's
  environment and in `spec.json`.
