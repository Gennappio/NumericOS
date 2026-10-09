# M2 / AGENTS.md — Knowledge Registry, approved decisions and verifiable Context Compiler

Read root `AGENTS.md`, active pointer and M1 text-anchor/agent contracts. **Implement M2 only.** M2 addresses the user's biggest frustration after long AI conversations: decisions, corrections and constraints become buried, contradictory or missing when a new session starts. NumericOS should keep the *question/discussion* separate from the *knowledge a future agent is allowed to use*.

## 0. Product promise

A user highlights a phrase in an agent answer, asks a narrow question, obtains clarification, and **optionally** turns the resolution into a typed reviewed decision or constraint. The next agent receives a precise, inspectable context snapshot of currently applicable knowledge without reading a giant chat. A new agent should know *what was decided, where it applies, who approved it, what superseded it, and how confident the evidence is*.

No one should claim we can create a literally 'perfect' context: instead implement **transparent, deterministic, provenance-linked, versioned, task-specific context** with conflict warnings and clear omissions.

## Skill-aware context without implicit promotion

M2 consumes the M1 canonical `SkillRegistry`. A skill is a **procedure**, not an approved project decision, experimental evidence or a substitute for a numerical validator. `ContextSnapshot` stores activated skill IDs, content digests, provider/model IDs and the explicit applicable approved knowledge. On a fresh agent session, compile context once with provenance and install selected skill versions; show in GUI why each approved fact and skill was included. Thread clarifications remain local unless promoted, and accepting a corrected text span does not automatically create a new global instruction. Concurrent project constraints override generic skill suggestions only by an explicit policy and review, never via hidden prompt concatenation.


## 1. Persistent objects

`KnowledgeItem`:
- `id`, `project_id`, `kind` (`decision`, `constraint`, `claim`, `open_question`, `definition`, `finding`, `assumption`), `text`, optional structured value, `scope` (project, module/file, experiment/research task), `epistemic_status` (as appropriate, e.g. `proposed`, `supported`, `contradicted`, `inconclusive`), `approval_status` (`draft`, `in_review`, `approved`, `rejected`, `superseded`), `author`, `reviewer`, approval time, `version`, `supersedes_id`, provenance refs (annotation/thread/message/experiment/source).
- Scientific claims are not made true by clicking Approve. **Approve** indicates the user chooses to use a statement or constraint as operative project context; epistemic support is a separate attribute grounded in evidence.

`ContextSnapshot`:
- `id`, `project_id`, `purpose/task_id`, `agent_session_id?`, `created_at`, `compiler_version`, `policy_version`, `included_items` with exact item versions, `excluded_items` with reason if requested, `experiment_refs`, `rendered_context`, `token_count_estimate`, `digest`, source/provenance and `status` (preview, frozen, used).

`KnowledgeConflict` or computed conflict report:
- Contradictory or overlapping constraints, scope collision, outdated revision, ambiguous precedence. The first version can use deterministic matching plus optional LLM suggestion; must label a suggested contradiction as heuristic, not fact.

`ContextPolicy`:
- explicit scope resolution and ordering, budget, required foundational constraints, relevant evidence, optional open questions; no silent arbitrary re-ranking of human-approved hard constraints.

## 2. User experiences to implement

### Promote a discussion (explicitly)

From anchored sidebar, select `Promote to project knowledge`. Let user choose type, text (editable before approval), scope and relation to existing knowledge. Show original selected quote, local thread and author. This creates a **draft**; clicking `Approve` creates active approved version. `Ask`, `Add Note`, `Suggest Change`, `Accept Text Edit` remain independent actions. No invisible automatic promotion.

### Resolve contradicting knowledge

If user approves 'Never convert CSR to dense' after a previous decision promoting dense arrays, show a review UI: `supersede previous / restrict scope / retain both for distinct conditions / cancel`. Keep history; do not silently remove old item. A deterministic compiler handles explicit `supersedes` and scope; heuristic conflict detector only flags potential conflicts.

### Inspect current context

Display a read-only **Context Preview** for a selected task/agent. Each entry has 'why included', source thread/message, version, scope, current approval state. Make budget/omissions visible. The user can edit by creating/reviewing knowledge, not by secretly rewriting an already-used snapshot.

### Fresh agent session

Create a NEW provider-backed agent session with only a prepared snapshot plus actual task/instructions. It must respect the latest applicable approved constraint; do not pass entire earlier chat. Preserve the old session as history. Store snapshot ID/hash on session creation and tool events for audit/replay.

## 3. Context selection algorithm (first release)

Prefer explicit deterministic selection to a mysterious vector-memory system:

1. Read the task description, project and optional module/experiment scope.
2. Collect all active, approved project-wide constraints and applicable scoped decisions; exclude drafts, rejected and superseded versions.
3. Include relevant definitions, assumptions, validated findings and evidence references, governed by scope/type ordering. Open questions only when user policy requests them.
4. Resolve explicit supersedes chains and detect malformed cycles. If contradictory active hard constraints remain, fail compilation or mark BLOCKED for review; never silently choose a favorite.
5. Allocate budget by class: hard constraints and task definition are mandatory; trim optional background/evidence summaries with visible exclusion rationale. If mandatory content cannot fit, return `CONTEXT_BUDGET_EXCEEDED` instead of silently dropping it.
6. Serialize in stable order with exact version/IDs and provenance; produce digest from compiler/policy/items/task. Store immutable snapshot. Provide an inspectable inclusion report.
7. On a session start, pass exactly the frozen snapshot and task, then persist agent-session linkage. A later knowledge edit does not retroactively change already-frozen snapshots.

Start without embeddings/vector DB; add similarity search only after measured retrieval gaps. Human corrections to context are recorded as new items or scoped policy updates, not silent runtime prompt edits.

## 4. Suggested context format

```yaml
context_snapshot:
  id: snapshot-019
  project_id: project-abc
  task: "Optimize a sparse 2D solver"
  compiler_version: 1
  required_constraints:
    - knowledge_id: K-018
      version: 2
      text: "Keep CSR sparse; no dense conversion in assembly/solve"
      scope: ["solver/*"]
      provenance: "THREAD-023"
  accepted_decisions:
    - knowledge_id: K-021
      version: 1
      text: "Benchmark against the baseline before any optimization"
  unresolved_questions:
    - "Is the reference implementation accurate on the coarse mesh?"
  evidence_refs: []
  omissions: []
  digest: "computed-at-runtime"
```

Sample strings are examples, not current data. Real version and hash must be generated deterministically. The LLM's interpretation of the context is not itself a validation step.

## 5. API/CLI/UX integration

Potential routes:

```http
POST /v1/knowledge-items
GET  /v1/projects/{id}/knowledge?approval_status=approved
POST /v1/knowledge-items/{id}:approve
POST /v1/knowledge-items/{id}:reject
POST /v1/knowledge-items/{id}:supersede
GET  /v1/knowledge-items/{id}/history
POST /v1/context-snapshots:preview
POST /v1/context-snapshots:compile
GET  /v1/context-snapshots/{id}
POST /v1/agent-sessions       # accepts frozen context_snapshot_id
```

CLI suggestions: `numericos knowledge list PROJECT --json`, `numericos context preview --task … --json`, `numericos context compile --task … --json`; use same API. Machine errors `UNRESOLVED_CONFLICT`, `INVALID_SCOPE`, `CONTEXT_BUDGET_EXCEEDED`, `STALE_REVISION` etc. Contract versions required.

UI: 'Knowledge' project tab; approval inbox; conflict detail/diff; Context preview and provenance links; badge indicating a fresh session's context version; not a wall-of-text view. `Why included?` and `What changed since previous context?` views are valuable.

## 6. Work tickets

1. **M2-T01 — Knowledge schema and lifecycle:** versions, scopes, approvals/supersedes, event emission and migration with tests.
2. **M2-T02 — Promotion from local thread:** UI action to draft knowledge; approval is separate; correct provenance and no implicit chat rewrite.
3. **M2-T03 — Conflict semantics:** explicit overlap/supersedes rules, blocked unresolved hard constraints, review UX.
4. **M2-T04 — Deterministic compiler:** scope selection, mandatory/optional information, token budgets, stable ordering and digest, immutable snapshot.
5. **M2-T05 — Agent integration:** fresh provider-backed agent sessions seeded only with frozen snapshot + task; explicit context source report and comparison to previous session.
6. **M2-T06 — End-to-end tests / handoff:** contradictory edits, rejection, frozen snapshots, direct thread links and round trip.

## 7. Golden acceptance scenarios

**Scenario A — FAQ clarification only:** user asks why a timestep limit holds in sidebar; closes thread without promotion. No changes to approved knowledge or new-agent context.

**Scenario B — Technical constraint revision:** user comments 'do not convert sparse CSR to dense', proposes exact rule, approves it. Context snapshot includes rule with source and correct scope. A newly created agent session sees the approved rule with no prior transcript.

**Scenario C — Conflicting decision:** previous approved item recommends dense form, new approved constraint forbids it. Approval must require explicit supersession/scope choice or compilation must flag a conflict; cannot quietly include both.

**Scenario D — History:** take snapshot S1, change knowledge item K1 to new approved version, take S2; S1 remains byte-identical, S2 has new digest and item version; session A remains linked to S1.

**Scenario E — Budget:** extremely small context budget fails loudly when mandatory constraints do not fit; doesn't drop safety/scientific constraints without disclosure.

**Scenario F — Retrieval:** query knowledge provenance from GUI; jump to the original assistant message and anchored discussion; if source is no longer available show stable archived reference, not a fake deep link.

## 8. Tests and measurements

- Unit tests for scope inheritance, supersedes cycles, deterministic serialization/digest, no rejected inclusion, token budget handling.
- Integration tests that verify saved snapshots survive backend restart and are fed to new agent sessions.
- UI e2e tests for promote → edit draft → approve → preview → jump-to-source → new session.
- Compare response-to-constraint accuracy vs replaying long chats on controlled tasks; measure omission and superseded-rule violations. Do not claim improvement without comparison.
- Validate race/stale-version submission: duplicate concurrent approvals do not invent two current versions.

## 9. Non-goals and epistemic limits

Do not build an ontological reasoner, vector-DB memory platform, automatic publication-quality claim verification, autonomous web-paper retrieval, long-context magical compression, collaboration/ACL, or semantic consensus among agents. No 'context is perfect' marketing. No automatic modification of source code when text/knowledge is edited. If optional LLM conflict detection is used, it only **proposes** concerns requiring deterministic or human resolution.

## 10. Done means

A user can annotate/clarify an exact part of a coding agent's response, explicitly promote a revised project constraint, see why it appears in a context preview, run a new independent agent session using it, and compare the immutable context snapshots. No historical giant chat replay and no silent knowledge mutation. Tests and UI demonstrations must substantiate this.
