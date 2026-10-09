# NumericOS — Scientific Skill Architecture

## Purpose

One canonical set of numerical/scientific skills, selectable in the UI or machine requests, available to Codex, Claude Code, Pi and other adapters. A skill defines *how to think/work* and optional supporting scripts; a runtime validator separately determines whether an experimental claim meets a recorded scientific acceptance criterion.

## Source of truth

- `skills/<id>/SKILL.md` (required). Frontmatter includes `name` and `description` and follows https://agentskills.io/specification. Keep descriptions narrow and load fuller instructions on demand.
- Optional `references/` and `scripts/` beside `SKILL.md` only when useful. Scripts are untrusted executables until code-reviewed/approved.
- Content hash = SHA-256 over canonical source files included in manifest (consider files/paths plus contents, stable ordering). Version field or Git revision, installed path, provider/version and source license are recorded alongside actual activation.
- No divergent version hand-edited for Codex, Claude or Pi. Provider adapters may generate small wrapper manifests/loaders but must never silently modify canonical skill meaning.

## Provider installation and safety

- **Codex:** probe official project skill discovery and app-server configuration for pinned version; prefer project-local `.agents/skills/<id>/` or vendor-supported explicit paths. Do not assume a particular nested path is available without verifying on the installed version.
- **Claude Code:** probe project `.claude/skills/<id>/` and SDK session options/version; link/copy canonical folders as needed, with real smoke test.
- **Pi:** use project `.agents/skills/<id>/` or `.pi/skills/<id>/`, or supported explicit skill path; confirm RPC loader sees the skill.
- Symlink if allowed, otherwise copy into adapter-private worktree and store digest. Never mutate global personal skill directories without permission. No uncontrolled writes to repository where agents are evaluating branches.
- A skill can direct file operations and shell commands: support trusted allowlist, read-only discovery and restrictions/sandbox. Reject invalid metadata, duplicate IDs, path traversal, untrusted executable scripts and digests that differ from selected manifest.
- `install_skills` returns a **receipt**: IDs, digest, actual load path/method, supported/unsupported status and diagnostic. 'Files copied' does **not** prove model actually used skill; distinguish installed/discovered/invoked/validated.

## Registry interface (M1)

```text
scan() -> SkillDescriptor[]
validate(skill_id) -> ValidationResult
resolve(skill_ids, project, provider) -> SkillManifest | UnsupportedError
install(session, SkillManifest) -> InstallationReceipt
activate(session, SkillManifest) -> ActiveSkillSnapshot
list_active(session) -> ActiveSkillSnapshot
```

Keep a single persisted exact session manifest. Selection can be UI/manual in M1; automatic but user-reviewable recommendations belong to M4. Changing selected skills during a run requires a new context/agent session revision if semantic behavior can change; don't rewrite prior run provenance.

## Milestone split

| Milestone | Required skill behavior |
| --- | --- |
| M0 | Architecture notes only; no fake registry or loader |
| **M1** | **Working registry, validation, activation, GUI checkbox, installation into at least one real agent, version/digest logging; three baseline skill instructions** |
| M2 | Context snapshots include exact selected skills; approved project constraints remain separate from general skill procedures |
| M3 | Bind skills to real numerical observability/validator APIs and experiment provenance; `SKILL.md` instruction alone never passes validation |
| M4 | Add advanced core+domain overlays; user-reviewable task-based skill selector; evaluate skill increment with A/B/C benchmark |
| M5 | Multiple provider adapters, per-role and external-request skill policy, parity tests and structured machine delegation |

## Initial shipped skill set (M1)

- `scientific-method`: objective, hypotheses, variables, predicted observation, falsification, evidence assessment, uncertainty.
- `research-code-style`: numerical clarity, minimal code, no unnecessary defensive wrappers, explicit invariants, avoid fake fallbacks.
- `numerical-validation`: plan domain-appropriate convergence, reference/error and stability tests; **guidance only until M3 executable validators**.

## Additional core skills (M3–M4)

- `experiment-provenance` and `runtime-observability` when execution + metric adapters are real (M3).
- `numerical-debugging`, `numerical-benchmarking`, `research-loop` (M4).
- Domain overlays starting from `pde-diffusion`, `sparse-linear-algebra`, `stochastic-abm`, `ml-pipeline` (M4). CFD/FEM can extend later using real reference tests; don't generalize CFD convergence rules into unsupported universal claims.

## UI behavior

In session settings: `provider`, `model` (if provider exposes), selected skill toggles, per-skill description and version, installation status, 'instructions only' vs 'real validation available'. Allow export of effective selection and show it in experiment/run provenance.

During a research loop: user/orchestrator may set `explicit` (fixed), `auto` (recommend+approve), or `restricted` (only allowed). Before expensive runs show resolved manifest + incompatibilities. Selecting a skill is not accepting a scientific hypothesis.

## Tests

1. Parser rejects missing name, invalid slug, mismatched parent folder, duplicate skill IDs or unsafe file paths.
2. Enable/disable persists; disabled skill absent from session manifest.
3. A real agent loader discovers one chosen skill; opt-in paid/provider integration test verifies capability without pretending success on local-only fixtures.
4. Hash changes after canonical skill edit; past session records retain old immutable digest.
5. Approved context constraints and selected skills are separate provenance channels; note-only discussion does not become a skill/constraint.
6. M3 numerical validator rejects intentionally invalid solver even when numerical-validation instruction was read and process exited zero.
7. M5 two providers load the **same** skill digest; record loader compatibility rather than claiming identical model responses.
