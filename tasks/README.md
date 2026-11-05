# Tasks

One unit of work = one file here. A task is the *only* way code enters the repository.

## Format

```markdown
# T0XX — <title>
**Status**: proposed | specced | implemented | gated | accepted | merged
**Owner**: agent | human
**Spec**: docs/spec.md §X.Y
**Depends on**: T0YY
**Layers touched**: model | operators | judges | solving | rendering | server | infra

## Goal
One paragraph: what changes for a user of the kernel.

## Deliverables
- files / symbols

## Acceptance criteria
Executable commands only. No prose criteria.

## Non-goals
What this task explicitly does not do.
```

## Rules

1. **Acceptance criteria are commands.** `pytest tests/unit/test_model.py -q` — not "the model works".
2. **One layer per task** (see the `Layers touched` row).
3. **No opportunistic refactors.** Refactors are separate tasks, so a regression is attributable.
4. **Every operator task includes oracle coverage** (spec §5.3); every judge task includes a counterexample test (spec §6.3).
5. **Rejected agent output is recorded** in `T0XX.failures.md` — never deleted (see `docs/ai-workflow.md` §6).

## Index

| ID | Title | Layer | Status | Depends on |
|---|---|---|---|---|
| [T001](T001-kernel-skeleton.md) | Kernel skeleton: construction graph, exact field, operator registry | model / infra | proposed | — |
| [T002](T002-oracle-harness.md) | Oracle harness and fixture format | infra | proposed | T001 |
| [T003](T003-mcp-server-core.md) | MCP server core: `geo_state`, `geo_construct`, `geo_evaluate` | server | proposed | T001 |
| T004 | Tier-A operators, batch 1 (`midpoint`, `foot`, `intersect_lines`, …) | operators | proposed | T002 |
| T005 | First judges (`collinear`, `perpendicular`, `concyclic`) | judges | proposed | T004 |
| T006 | Competition style preset + SVG/TikZ renderer | rendering | proposed | T001 |
| T007 | `geo_solve` and `geo_variants` | solving | proposed | T004, T005 |
| T008 | Problem file format + exporter | infra | proposed | T006 |
| T009 | Benchmark harness (`evals/`) | infra | proposed | T005, T007 |
