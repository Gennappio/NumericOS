# M1 / AGENTS.md — Provider-neutral coding agent, scientific board, annotated conversations and Skills Registry

Read root `AGENTS.md`, `CURRENT_MILESTONE.md`, M0 contracts and this file. Implement **M1 only**. This is the primary human-interface differentiator. The user strongly dislikes coding agents' long chat walls: a small question about one phrase should NOT cause a new giant main-thread conversation that buries the original answer.

## 0. Intended user experience

User opens a project → sees a scientific Trello-like board and asks **a selected provider (Codex first by default)** a question → the agent writes normal Markdown (not automatically exploded into mandatory cards) → user **selects any portion of rendered assistant text** → a contextual menu appears with **Ask / Suggest Change / Add Note** → an anchored sidebar opens while the original response remains visible → discussion/revision/note persists across reload. A local question does **not** grow the main conversation. Separate thread from main agent session is a hard invariant.

Do not build a generic rich-text collaborative editor; implement robust selection and annotation over **read-only rendered assistant responses**. Editable knowledge documents can be added later.

## 1. Components and boundaries

- `AgentAdapter` contract: `capabilities()`, `start_session(project, provider_config, context?)`, `send_message(session_id, content)`, `stream_events(session_id)`, `interrupt(session_id)`, `resume(session_id)` *if supported*, `get_state(session_id)`, `close(session_id)` and `install_skills(session_id, skill_set)` with typed errors. No assumption that resume, tool interception or approval are identical across providers. **Codex App Server adapter first by default**, after a real version-pinned protocol spike. Claude Agent SDK and Pi RPC are planned first-class implementations; defer full provider parity to M5. See adapter contract doc.
- Record `provider`, `adapter_version`, `model_id` when exposed, `native_session_id`, capability snapshot, exact tool activity and approval events; do not promise hidden reasoning or every provider-internal event.
- Agent process lifecycle: use official structured transport for chosen provider (Codex App Server JSON-RPC; Claude Agent SDK; Pi RPC when implemented), explicit argv/no shell interpolation, stdout framing/error separation, backpressure, prompt/turn IDs, approval routing, EOF/crash/interrupt semantics and reconnection policy. Do not pretend a subprocess is resumable without proof. Authentication and access policies are provider-specific.
- Persistence: AgentSession, immutable Message (role, original Markdown, format, message version, created_at), AgentEvent, Annotation, Thread, ThreadMessage, optional MessageRevision with old/new relation. Write event stream linked to project.
- UI: main conversation pane + project board + fixed/right-side anchored discussion panel (collapsible). Main chat remains navigable when sidebar opens; highlight shows source span. Visible agent status and tool actions rather than generic spinner.
- Full Kanban: columns/workflow states from M0; type-specific card details; dnd-kit reorder persisted through API; task/hypothesis/experiment/issue/decision types; do not treat card movement as scientific endorsement.

## 1a. Canonical Scientific Skill Registry (must ship in M1)

- Follow the open Agent Skills format: `skills/<skill-id>/SKILL.md` with required `name`/`description` frontmatter; metadata may also capture license, revision and compatibility where supported. Source of truth is NumericOS's checked-in `skills/`, **never** divergent hand-edited copies in `.agents/skills` or `.claude/skills`.
- Provide `list`, `validate`, `install`, `activate/deactivate` operations as backend services and expose project/session selection through the GUI. Installation may be project-scoped copy/symlink or adapter-discovered explicit directories depending on OS, sandbox and provider. Verify actual discovery via a provider integration smoke test; do not rely on undocumented global directories.
- Verify candidate paths and security: a `SKILL.md` may link scripts or assets with executable code. Never run untrusted skill scripts on scan/install. Trust/version pinning is explicit; do not log secrets.
- Record `skill_id`, `version` or Git revision, `sha256` digest, enabled state, installation strategy and provider compatibility outcome for each session; log `SKILLS_ACTIVATED` into existing event ledger. Prefer lightweight project-local manifests to adding unnecessary DB tables.
- M1 ships three minimally useful baseline skill instructions: `scientific-method` (hypothesis/expected result/controlled variables/falsification), `research-code-style` (lean code + rigorous numeric safeguards), `numerical-validation` (plan appropriate mathematical tests). No magic scientific correctness claims before real validators ship in M3.
- This registry is explicitly **provider neutral**: Codex, Claude, Pi read the same canonical skill text. Adapter locates or installs them using each provider's supported mechanism; tests pin the actual version and verify parity. See `docs/SKILL_ARCHITECTURE.md`.

## 2. The exact text-selection interaction (critical)

Selecting a substring of the assistant's rendered Markdown triggers a floating menu near selection (use browser selection and DOM Range mapping; no React state that destroys selection before action). Actions:

**Ask:** opens thread anchored to exact selected span. Agent reply is short and only about this span, with enough local paragraph/project context and links to relevant evidence. The user can expand or ask more in that thread. The thread is persisted as separate conversation/session branch; it does not append automatically to the main coding-agent history. Use separate thread-specific provider session with compact explicit context if the selected provider cannot branch cheaply; document and verify actual isolation.

**Suggest Change:** user writes how this selection should be changed. Agent proposes replacement text for **exact selected range** (not entire answer), plus optional rationale; show before/after or diff. Accept generates a NEW immutable message/document revision with provenance; reject leaves original unchanged. Editing assistant text does not edit source files or approve a permanent project constraint.

**Add Note:** save a human note; no LLM call by default. Notes can be personal/project-scoped later. Add Note must not pollute main agent context.

Additionally: reopen, resolve/unresolve, edit own note with history; multi-thread on distinct and overlapping spans; source link from each comment; direct link to comment if feasible. UI shows count of active comments per message, status and small highlights; no annoying giant side panel by default.

## 3. Anchor model — why naive selected_text matching is forbidden

Represent a TextAnchor (schema naming flexible):

```json
{
  "message_id": "msg-183",
  "message_version": 1,
  "start_offset": 151,
  "end_offset": 190,
  "selected_quote": "Un timestep troppo grande ...",
  "prefix": "...",
  "suffix": "...",
  "block_path": [2, 1],
  "canonicalization_version": "v1",
  "state": "attached"
}
```

This is a shape, not literal example offsets. Store **canonical normalized rendered-text** offsets, not random DOM node offsets. Precisely define Unicode offset units (e.g. Unicode code points on server; JS code-unit mapping on client). Save selected quote + prefix/suffix + optional Markdown AST block ID/path and renderer version. A `TextAnchor` belongs to an exact immutable message version. Do NOT silently reattach a comment to some other identical phrase in the same document.

Anchor behavior:
- On unchanged version, preserve exact offset; repeated substrings attach to intended occurrence.
- On newly accepted revision, do NOT mutate original. Attempt offset/quote/context reanchoring and mark `attached/moved/ambiguous/orphaned` as appropriate; if ambiguous show repair control rather than guessing.
- Overlapping highlights render correctly, accessible user selection still works and text isn't duplicated or corrupted.
- User can select an arbitrary part of a paragraph, across multiple inline formatting spans or adjacent paragraphs; multiple-line text remains accurately anchored.
- Test Unicode, emoji, accented characters, repeated phrases, emphasis, links, code formatting. Formulas/code blocks: implement correct selection OR show explicit 'not yet supported' with safe recovery. NEVER persist a wrong anchor.
- Prevent comments on streaming/incomplete message revisions until a finalized immutable message exists, or explicitly snapshot selected finalized content; document chosen behavior.

## 4. Streaming and agent session UX

- Distinguish streaming message (mutable UI draft) from finalized immutable Message; only finalized message is anchorable in first release.
- Show non-text tool calls in a compact collapsible tool activity row, rather than dumping entire tool JSON inside prose.
- Main conversation can scroll while sidebar discussion is open. Selecting another anchor switches side thread without losing main position.
- The sidebar's AI response defaults to concise; let user request more detail. Never make sidebar show the whole primary chat.
- Preserve author/source/time and thread resolution state. Thread response belongs to thread ID and selected quote version.
- Provider crashes/offline: recover persisted messages, show accurate disconnected state; non-sent prompts and invalid responses do not magically become completed. Show available capabilities and clearly marked unsupported actions.

## 5. API and event proposals

```http
POST /v1/agent-sessions                    -> session_id + state
POST /v1/agent-sessions/{id}/messages     -> accepted message request
GET  /v1/agent-sessions/{id}/messages
POST /v1/messages/{id}/annotations        -> annotation with anchor
GET  /v1/messages/{id}/annotations
POST /v1/annotations/{id}/threads         -> thread_id
POST /v1/threads/{id}/messages            -> focused human/agent turn
POST /v1/annotations/{id}/suggest-change  -> candidate replacement
POST /v1/message-revisions                -> accept diff (precondition version)
POST /v1/threads/{id}:resolve
```

Expose agent events via M0 event ledger/SSE; do not invent an independent incompatible event bus. Include `thread_id` / `source_message_id` in any agent response event. A focused thread's transcript must be accessible via its own endpoint and replayable.

## 6. Detailed task plan

1. **M1-T01 — Agent adapter feasibility spike:** verify Codex App Server startup, authenticated prompt, streaming, native session IDs, tool/approval events, interruption and crash; freeze version-pinned `AgentAdapter` interface and capability matrix. If blocked, document an ADR and use Claude Agent SDK or Pi RPC without changing NumericOS contracts.
2. **M1-T02 — Agent chat UI:** persisted project sessions/messages with **real selected provider**, normalized structured event stream, tool-action collapse, reload/reconnect, provider/model selection.
3. **M1-T03 — Scientific Skills Registry MVP:** scan canonical `skills/*/SKILL.md`, parse/validate frontmatter, preserve optional references/scripts, enable/disable skill IDs per session, record content digests/versions, install or project-link skills for the selected agent and verify actual discovery. Include `scientific-method`, `research-code-style`, `numerical-validation` as **guidance-only** MVP skills; no invented executable numerical validator yet.
4. **M1-T04 — Anchor engine:** canonical text extraction/DOM mapping, exact-version persistence, highlights, selection menu; tests for repeated substrings, Unicode, Markdown, overlap.
5. **M1-T05 — Threaded Ask / Note:** side panel, genuinely isolated focused agent thread, persistent replies and notes without main-chat pollution.
6. **M1-T06 — Suggest Change/revisions:** replacement-span diff, accept/reject, immutable versions, safe reanchoring/ambiguous states.
7. **M1-T07 — Scientific board + skill UX:** dnd-kit persisted typed cards, per-session skill checklist, enabled skill descriptions and installation status, no misleading 'validator passed' when skill only supplies instructions.

## 7. Test matrix

| Scenario | Expected behavior |
|---|---|
| Highlight second occurrence of identical phrase | Annotation remains on second occurrence after reload |
| Highlight 'é', emoji, multiline and bold-to-plain span | Correct quote/position or visible unsupported state |
| Two overlapping comments on same text | Both visible and individually openable |
| Focused Ask in sidebar | Main chat message count unchanged; thread grows independently |
| Accept local change | New version, original recoverable; other selected text unmodified |
| Reject proposed edit | No message mutation, no knowledge approval |
| Chosen provider process killed mid-turn | Explicit interrupted state; no forged final message |
| Agent skill disabled then session launched | Agent environment excludes the disabled skill; project canonical registry remains unchanged |
| Skill selected in Codex adapter | Agent can discover real `SKILL.md`; selected digest and provider install path are recorded |
| Two skill names collide or metadata is invalid | Fail clearly without loading a wrong skill |
| CLI/provider does not support a capability | Capability UI says unsupported; no silent emulation of partial features |
| Reconnect browser/refresh | Sessions, annotations, board cards and event order retained |
| Board card dragged then page reloaded | Correct column, ordering and distinct semantic type |
| Select link/inline formula/code | Right anchor or visible, non-corrupting limitation |

Add browser e2e tests with Playwright or equivalent for actual selection and sidebar (not only mocked unit state). Test **a real first-provider integration** separately from deterministic adapter fakes; do not require paid model calls on every CI job. Include one opt-in integration test proving that a `SKILL.md` is installed/discovered, not just displayed in the GUI.

## 8. Forbidden shortcuts / scope exclusions

- **Never** split every AI answer into card fragments against the user's wishes; selectable arbitrary text is the design.
- Do not route every sidebar question into the main agent session or silently auto-summarize all sidebars into the project.
- Do not update knowledge/context just because a user asks a question or accepts a text rewrite (M2 handles explicit promotion).
- No uncontrolled HTML rendering or XSS through model Markdown, copied code, links or annotations. Use sanitization and safe URL handlers.
- Don't build numerical execution, experiment state machines, multiagent workflow editor, MCP or SLURM here. M1's `numerical-validation` is procedure guidance only; actual validators belong to M3.
- Avoid over-engineering with CRDT/real-time collaboration until multiuser need is validated.

## 9. Exit gate demo

1. Create a scientific project with at least two typed board cards.
2. Start a real session with the selected supported provider (Codex default) and ask for analysis of a short numerical algorithm; show provider, capabilities and activated scientific skills.
3. Select an arbitrary sentence fragment; Ask 'Why?'; receive short answer in sidebar only.
4. Select a second fragment; Add Note. Reopen first thread later.
5. Suggest correction, see minimal diff, accept; show original version and valid/repaired anchor states.
6. Drag a board card; reload the page; everything persists.
7. Install/discover three canonical project skills, disable one, and prove the resulting provider session reflects the selected skill set.
8. Demonstrate DB/API restart and one deliberate provider error without false success.

Deliver recorded behavior/screenshots, passing contract/unit/e2e tests, message and anchor schema, documented edge-case limitations, and a reviewable commit. **Do not claim M1 done if repeated-phrase/Unicode anchoring or isolated threads fail.**
