# ADR-0008: The owner's redirection: commentable agent documents before validators

- Status: accepted (2026-10-12)
- Decider: project owner

## Context

After trying the M3 deliverables (experiments, runs, metrics, the Run Monitor) the owner said
they did not understand the trajectory nor how to use what was built, and took the lead. Their
requirements, in their order, condensed from their words:

1. Intercept the answers of the coding agent. For a computational project the first thing to
   understand is what the project does: a **theory** page, rendered like a paper (formulas, clean
   text, images), which must itself be open to question.
2. A page with cached **descriptions of the files** of the project: inputs, code, outputs, images.
3. A description of **what happens during execution**, without adding code to the source.
4. When the code changes, the descriptions it affects are updated.
5. The **conversations and prompts** of each project, as a client such as Codex shows them.
6. The **plan** written by the coding agent, shown as a Trello-like board; adding, moving or
   editing cards changes the plan.
7. Most important: every description and every agent answer is **commentable**: select text,
   press a contextual button, write. A **Clarify** button gathers all comments that ask for a
   clarification and sends them to the agent together; the agent expands only the commented
   passages, never the whole text. A **Resolve** button gathers all comments that ask for a
   change (to the code or to the theory) and sends them together; if requests conflict, the
   agent decides whether and how to proceed, as it does today in a terminal.

The owner answered three questions about how this should behave:

- A change request makes the agent **modify the project's files directly**; there is no
  branch-and-approve step in between.
- One talks to the agent **only from NumericOS**. Sessions the owner runs in a terminal are not
  imported.
- Work **starts with the clarifications**.

## Decisions

1. **M3 is paused** after T04 and the first part of T06. T05 (validators and comparison) and
   the rest of T06 wait until the owner queues them again. The M3 gate is not claimed.
2. **The active milestone is M1 in the owner's version**, defined here. The brief in
   `milestones/M1/AGENTS.md` keeps its engineering rules (anchors, isolation of focused threads,
   no fake agent output, real browser tests) and is adapted as the table below says.
3. **The first adapter is the Claude Code command line**, not the Codex App Server the brief
   proposed. The owner uses Claude Code; it is installed (2.1.296); its non-interactive mode
   (`claude -p`) was verified on 2026-10-12 to provide a structured event stream
   (`--output-format stream-json --verbose`: text blocks, every tool call with its input, every
   tool result, a final record with cost and usage), a structured answer validated against a JSON
   schema (`--json-schema`), continuation of a session (`--resume <id>`), branching of a session
   (`--fork-session`), a chosen session ID (`--session-id`), a system prompt extension
   (`--append-system-prompt`) and a spending bound (`--max-budget-usd`). Codex follows later
   through the same `AgentAdapter` boundary; `codex exec` offers `resume` and `fork` as well.
   The provider-specific protocol stays inside `numericos.agents.claude_code`.
4. **NumericOS launches the agent**; a turn is a subprocess of the supervisor (`numericos worker
   run`), never of the API. The API only queues turns, as it only queues runs. A turn writes its
   stream to a file in the data directory; the supervisor turns the file into state and events,
   so a supervisor that stops does not lose a turn, and the next one continues from the file.
5. **Three permission modes**, chosen per session and shown as they are: `read_only` (the agent
   reads the repository; edits and commands are refused), `edit` (file edits are allowed, commands
   are refused), `full` (everything is allowed, as `--dangerously-skip-permissions` in a
   terminal). What a mode refused is recorded on the answer, never hidden. The project directory
   must be trusted for execution (ADR-0005) before any session starts: an agent that edits files
   or runs commands executes with the user's permissions.
6. **Clarify and Resolve are batched turns.** Clarify forks the session that produced the
   document, so the agent has the context in which it wrote, and the main conversation does not
   grow (the brief's hard invariant). Its answer is structured: one expansion per comment,
   inserted where the comment is. Resolve continues the main session with edit permissions.
7. **A change request edits the files directly**, by the owner's decision. The root `AGENTS.md`
   principle that a correction, an endorsement, a text revision and a code change are distinct
   operations still holds in the record: a Resolve turn is an explicit action of the owner, it is
   recorded as such, and what the agent changed is visible in Git. What is relaxed is the
   proposal-then-accept step for code.
8. **Anchors live on the Markdown source** of an immutable message version: start and end
   offsets into the source, the quoted text and its context. The server verifies that the quote
   is exactly what the offsets select, so a wrong anchor is never persisted. The details of the
   anchor engine get their own record when it is built.

## How the M1 brief is adapted

| M1 brief | In the owner's version |
| --- | --- |
| Codex App Server first | Claude Code command line first (decision 3) |
| **Ask** opens an anchored side thread with a short answer | **Clarify**: comments of kind *clarification* are sent together; each answer appears as an expansion at its anchor |
| **Suggest Change** proposes a replacement for the span, accepted or rejected | **Resolve**: comments of kind *change* are sent together; the agent edits the code or the document directly; the new document version is recorded and anchors are re-attached |
| **Add Note** saves a human note without an LLM call | Kept as is |
| Scientific skill registry in M1 | Deferred; nothing here depends on it |
| Full Kanban with drag and drop | Comes with requirement 6 (the plan as a board), after the documents |
| Main conversation pane with provider and model selection | Requirement 5: one conversation list per project; sessions, prompts and answers persisted |

## Order of work

| Ticket | Delivers | Owner's requirement |
| --- | --- | --- |
| M1-T01 | Agent sessions and messages of a project; the Claude Code adapter; turns executed and observed by the supervisor; the Agents view with rendered Markdown and mathematics | 5 |
| M1-T02 | Anchors on the Markdown source; comments of kind clarification, change and note; **Clarify** | 7 (first part) |
| M1-T03 | **Resolve**: change requests sent together, direct edits, new document version, re-anchoring | 7 (second part) |
| M1-T04 | The theory page: a document the agent writes about the project, rendered like a paper, commentable like any answer | 1 |
| M1-T05 | File descriptions, cached by content hash, with the files each description read; invalidation when the code changes | 2, 4 |
| M1-T06 | The execution description: what happens when the program runs, from the code and from what the M3 supervisor observed; no instrumentation of the source | 3 |
| M1-T07 | The plan as a board: structured plan from the agent, cards editable, the board fed back to the agent | 6 |

## Order as delivered

The owner, seeing only the conversations after M1-T01, asked for the pages first ("non vedo la
board con la spiegazione dei file, la teoria, i trello del piano"). The pages were therefore
delivered before the comments: the theory (T04), the file descriptions with staleness (T05, and
requirement 4 as "marked and updated with one click", not yet by itself) and the plan on the
board with drag and drop (T07). Comments with Clarify and Resolve (T02, T03) followed on
2026-10-13 (ADR-0009); the execution description (T06) is next.

## Consequences

- `CURRENT_MILESTONE.md` points to M1 and to this record; `milestones/M3` stays as it is.
- The GUI gets a Markdown renderer with mathematics (KaTeX); raw HTML in agent output is not
  rendered.
- Every agent turn uses the owner's Claude account. The owner has a subscription: nothing is
  charged per turn, the plan's 5-hour and 7-day windows are consumed, and the answer shows
  that use as the provider reports it. The provider also reports a list-price equivalent
  (`cost_usd`), a measure of tokens, bounded per turn. The weight depends mostly on the model
  (a trivial turn: 0.31 USD-equivalent with Fable, 0.0025 with Haiku, measured 2026-10-12)
  and on whether the session is new (its system prompt is cached for the later turns). By the
  owner's request of the same evening, the model and the effort are chosen **per task**
  (conversation, clarify, resolve, theory, file descriptions, execution description, plan)
  among what the chosen coding agent offers, with a per-conversation override.
- The release benchmark of the root `AGENTS.md` (section 9) becomes possible once the adapter
  exists, but is not part of these tickets.
