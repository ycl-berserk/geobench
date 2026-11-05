# Prompt template — implement one operator

Used by the agent that implements a single operator task. Fill the placeholders; do not edit the rules.

---

You are implementing **one operator** of the geobench geometry kernel.

**Operator id**: `<op.id>` — e.g. `point.foot`
**Task file**: `tasks/<T0XX>.md` — read it first, in full.
**Spec section**: `docs/spec.md` §<X.Y> — read it verbatim; the excerpt below is a copy, the file is the truth.

```
<PASTE THE RELEVANT SPEC SECTION HERE VERBATIM>
```

### Hard rules

1. **No floats.** The kernel must contain no floating-point literals and no float arithmetic on geometric quantities. A `Field` protocol exists for this (`src/geobench/field.py`); use it. If an exact result is impossible, raise a typed error — never return an approximation.
2. **Do not invent public API.** Use the existing registry, `Field`, and error types. If you believe the spec needs to change, stop and say so in your report instead of changing it.
3. **Tests first.** Write the test file before the implementation. Include: ≥ 3 normal cases, ≥ 2 degenerate cases asserting a typed error, and one exact-value assertion with a hand-derived expected result.
4. **Declare degeneracy.** Fill in `degenerate_when` in the operator contract (`spec.md` §5.1). Every situation in which the operator is undefined or ambiguous must appear there — including ambiguous intersection indices.
5. **Ambiguity is an error, not a guess.** If the operator can return several results (e.g. two intersections), the choice must be an explicit argument. Never pick "the first one" silently.
6. **Stay in your layer.** Touch only the files your task lists. Refactors are separate tasks.
7. **Do not weaken a test to make it pass.** If a test is wrong, fix the test only with a written justification in your report.

### Deliver

- The implementation, the tests, and the registry entry.
- A one-line oracle note: what independent implementation will cross-check this operator (see `tasks/T002-oracle-harness.md`).

### Report format

```
Files changed:
  - <path> — <one line>

Commands run and their output:
  $ pytest tests/unit/test_op_foot.py -q
  ...

Known limitations / spec ambiguities found:
  - <...>   (or "none")

Degenerate cases handled:
  - <condition> → <error type>
```

Do not claim success without pasting the actual command output.
