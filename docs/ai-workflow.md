# AI workflow

**Principle: the model writes the code, the human writes the specification and adjudicates the truth.**

This document is not a style guide. It is the mechanism that makes the project's central claim credible — that geometry software can be produced by AI agents under a human-owned contract — and it doubles as one of the project's proof artefacts.

---

## 1. Why this shape

Geometry kernel code has a property that is unusual and useful: **almost every line is checkable**. An operator either computes the right point or it does not; a judge either proves the relation or it does not. This makes it unusually well suited to a workflow where a model does the typing and a machine does the judging:

- A human-written spec is unambiguous in a way a human-written *implementation* rarely is.
- An AI-generated implementation is cheap to produce and cheap to discard.
- The expensive part — deciding what is true — is exactly the part that can be automated *deterministically* inside the kernel.

So the human's scarce attention goes to: scope, semantics, taste (what a good competition figure looks like), and the adjudication of edge cases that the spec did not anticipate.

## 2. Roles

| Owned by the human (domain owner) | Owned by the agent |
|---|---|
| `spec.md` — semantics, operator/judge contracts, verdict meanings | Implement operators, judges, tools, tests |
| Scope decisions (D5), style values (D6) | Property-based and counterexample test batteries |
| The "what makes a good competition figure" judgement | Oracle cross-checks against independent implementations |
| Accepting or rejecting a task | CI configuration, packaging, docs drafts |
| The final "is this a valid problem" call | Refactoring within the constraints of a task |

The human does **not** review code style. Linting and typing are gates, not review items.

## 3. Task lifecycle

```
 proposed ──▶ specced ──▶ implemented ──▶ gated ──▶ accepted ──▶ merged
   │            │             │            │           │
   │            │             │            │           └─ human: verdict semantics,
   │            │             │            │              taste, edge cases
   │            │             │            └─ CI: lint · types · unit · oracle ·
   │            │             │               property · degeneracy · no-float
   │            │             └─ agent produced code + tests
   │            └─ task file has machine-checkable acceptance criteria
   └─ idea, from the human or from the open-issues list
```

A task never enters `implemented` without a task file in [`../tasks/`](../tasks/) whose acceptance criteria are **commands that can be executed** (not prose).

## 4. Task grain

One task = one unit of behaviour + its tests + its oracle. Concretely, a task implements **one operator**, **one judge**, **one MCP tool**, or **one piece of infrastructure** — not "the geometry module".

- Target size: ≤ 300 changed lines including tests. A larger change is split.
- No opportunistic refactoring inside a feature task. Refactors are their own tasks, so a failure can be attributed.
- A task touches at most one layer of the kernel (see `spec.md` §1.1 ordering: model → operators → judges → solving → rendering → server).

## 5. Gates (all in CI, all blocking)

| Gate | Command | What it protects |
|---|---|---|
| lint | `ruff check .` | style, banned patterns, **float literals in the kernel** |
| types | `mypy src` | contract drift |
| unit | `pytest tests/unit -q` | behaviour |
| oracle | `pytest tests/oracle -q` | operator correctness against an independent implementation |
| property | `pytest tests/property -q` | identity-level correctness over random inputs |
| degeneracy | `pytest tests/degeneracy -q` | edge-case handling |
| no-float | `pytest tests/no_float -q` | the exactness invariant of `spec.md` §4 |
| contract | `pytest tests/contract -q` | the public API matches `spec.md` |

Additional rules:

- Every judge needs **one positive and one counterexample test**. A judge that cannot refute a mutated figure does not ship.
- Every operator needs oracle coverage over ≥ 20 configurations, ≥ 3 of them degenerate. The harness prints a coverage table; an operator with no oracle row is a CI failure.
- A `proved` verdict must be re-checkable: `geo_verify` responses carry the reduced expression and the assumptions.

## 6. The failure protocol — the part that matters

Every rejected agent output is recorded, not deleted. `tasks/<task-id>.failures.md` accumulates:

```markdown
### F2 — 2026-11-08 · sympy simplification returned a non-zero remainder
- **Task**: T004 point.foot
- **Symptom**: `verify` returned `undecided` for a right angle that is obviously true.
- **Root cause**: the agent assumed `simplify()` normalises trig identities; it does not.
- **Fix**: use `trigsimp` + `simplify` and compare against `0` after `cancel`.
- **Gate that should have caught it**: the oracle battery (a right-triangle fixture was missing).
- **Action**: added the fixture to `tests/oracle/fixtures/right_triangle.json`.
```

This log is the honest evidence of AI-assisted engineering: it shows what failed, why, and which gate was tightened afterwards. A repository with only successful outputs proves nothing about the process.

## 7. Prompting rules

Templates live in [`../prompts/`](../prompts/). The rules they encode:

1. **Quote the spec verbatim.** The agent is given the relevant section of `spec.md`, not a paraphrase of it.
2. **No invented APIs.** The agent must use existing registry/interface patterns and may not add public API beyond the task's scope. Adding public API is a spec change first.
3. **Tests before code.** The agent writes the failing test (including the counterexample for judges) before the implementation.
4. **No floats.** Stated explicitly, because it is the invariant agents break most often.
5. **No silent approximations.** If an exact computation is not possible, the operator must raise a typed error — never return a float and hope.
6. **Ambiguity is an error, not a guess.** Intersection indices, arc choices, and "the" circle must be explicit; if the spec does not say, the agent asks instead of choosing.
7. **Report, do not claim.** The agent's final message contains the files changed, the exact commands run with their output, and known limitations.

## 8. Measuring the workflow itself

The workflow is instrumented like any other part of the project, because its quality is part of the claim:

- **Acceptance rate** per task type (operator / judge / tool / infrastructure).
- **Iterations to green** per task (median and p90).
- **Gate hit histogram** — which gate rejects most often (this tells us where the spec is underspecified).
- **Regressions introduced** by agent tasks.

These numbers are reported in `docs/ai-workflow.md` (this file) at each milestone, and the raw data lives in `evals/reports/`.

## 9. Tools

The kernel is driven through the MCP server (`spec.md` §11), from any MCP client — the human uses one for interactive work, and agents use the same interface. There is no privileged path for the agent: **if the agent can call it, the human can call it**, and everything the agent does is recorded in the figure state and reproducible from the problem file.
