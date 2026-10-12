# ADR-0004: Observability of code and experiments before agents and further board work

- Status: accepted (2026-10-12)
- Decider: project owner

## Context

The blueprint orders the milestones M1 (coding agent, anchored discussions, skill registry, full
Kanban), M2 (knowledge and context), M3 (experiment engine, provenance, numerical
observability). After reviewing M0 the project owner set a different priority: the board is the
last thing to work on, and what matters most is the observability of code and experiments.

## Decision

1. The M0 gate is accepted (tag `m0-gate`).
2. The active milestone is **M3**, built directly on M0.
3. Further board work (drag and drop, type-specific card details, any board polish) moves to the
   end of the roadmap. The board stays as M0 delivered it.
4. M1 and M2 keep their briefs and come after M3. Their relative order is not decided here.

## How the M3 brief is adapted while M1 and M2 do not exist

`milestones/M3/AGENTS.md` assumes an agent adapter, a skill registry and knowledge items. Until
they exist:

| M3 brief | In this ordering |
| --- | --- |
| "Reuse M1 skill registry"; a run saves the "activated skill manifest/digests" and the agent provider/model | No agent and no skill are involved in a run. The run record says so explicitly (`agent` and `skills` are absent, and the GUI states it) instead of leaving the question open. No skill loading is built in M3 |
| "asks an agent to implement a candidate (or uses existing code)" | Candidates are commits, or explicitly allowed working-tree states, made by the researcher |
| "one branch + worktree per independent agent code-editing task" | No agent edits code yet. The policy applies when agents arrive; M3 defines only how a run obtains exactly the code it executes |
| Hypothesis "source knowledge refs"; the Explorer "integrates with M2 knowledge" | There are no knowledge items; nothing refers to them until M2 |
| "Hypothesis card opens hypothesis ... and linked experiments" | A card may reference a hypothesis or an experiment through `entity_ref`. The Experiments view, not the board, is the entry point |

Everything else in the M3 brief applies unchanged: typed hypotheses, experiments and runs, Git
and input provenance, a supervisor that outlives the API and the CLI, observability levels L0 to
L3 with explicit coverage, validators that are independent of any LLM, and no automatic merge.

## Order inside M3

The backend tickets keep the order of the brief (T01 domain model, T02 provenance, T03
supervisor, T04 numeric adapters). The Run Monitor part of T06 is delivered right after T04, so
that a real run can be watched by hand as early as possible; validators and comparison (T05) and
the rest of the Explorer follow.

## Consequences

- The release benchmark that compares a coding agent with and without NumericOS (root
  `AGENTS.md`, section 9) cannot run before agents exist.
- The gate items of M1 that concern the board are deferred with it.
- `CURRENT_MILESTONE.md` points to M3 and to this record.
