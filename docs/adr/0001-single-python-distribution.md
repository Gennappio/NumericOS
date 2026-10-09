# ADR-0001: One Python distribution with module boundaries instead of a multi-package workspace

- Status: accepted (M0-T01, 2026-10-09)
- Deciders: project owner, implementing agent

## Context

`milestones/M0/AGENTS.md` suggests `apps/api/` plus `packages/{core,persistence,events,cli}` and
explicitly allows "a smaller viable layout with explicit boundaries" when the deviation is
recorded. `docs/NUMERICOS_IMPLEMENTATION_PLAN_v0.2.md` warns against "empty architecture theater".
In M0 there is one deployable (the local API) and one CLI; separate distributions would only add
`pyproject.toml` files, cross-package version pins and editable-install plumbing.

## Decision

One installable distribution `numericos` (`pyproject.toml` at the repository root, sources in
`src/numericos/`). The suggested packages become subpackages with a fixed dependency direction:

```text
core  <-  persistence  <-  events  <-  services  <-  api
cli  -> HTTP only (never imports persistence or services)
```

Future modules (`agents`, `skills`, `context`, `experiments`, `executor`, `observability`,
`validators`) are added as subpackages when a milestone needs them. The frontend stays a separate
npm project in `apps/web/`.

## Consequences

- One `uv sync`, one lock file, one `numericos` entry point; imports stay explicit and greppable.
- Boundaries are enforced by review (and may later be enforced with an import linter), not by
  packaging.
- Revisit when a client needs to install a subset without the server, e.g. the M5 Python SDK:
  that is the moment to introduce a uv workspace.
