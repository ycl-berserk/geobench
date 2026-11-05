# T001 — Kernel skeleton: construction graph, exact field, operator registry

**Status**: proposed
**Owner**: agent
**Spec**: `docs/spec.md` §3 (data model), §4 (numeric strategy), §5.1 (registry contract)
**Depends on**: —
**Layers touched**: model / infra

## Goal

The kernel can load, mutate and serialize a construction graph, hold every geometric value as an exact expression, and register operators behind a uniform contract. Nothing is rendered, nothing is solved; this is the substrate everything else stands on.

## Deliverables

- `src/geobench/field.py` — the `Field` protocol: `add`, `sub`, `mul`, `div`, `sqrt`, `simplify_to_zero(expr) -> bool`, `to_float(expr) -> float`. SymPy-backed implementation. Rejects float literals at construction.
- `src/geobench/model.py` — `Node`, `Relation`, `Figure` dataclasses; validation (unique ids, DAG check, argument arity, type check); JSON round-trip that is byte-stable.
- `src/geobench/registry.py` — operator registry: `register`, `lookup`, `describe` (returns the §5.1 contract), duplicate-id rejection, `degenerate_when` metadata carried through.
- `src/geobench/state.py` — figure store: apply/dry-run operations, dependency recomputation of derived nodes, undo history (XML-free, our own snapshot list).
- `tests/unit/test_model.py`, `tests/unit/test_field.py`, `tests/unit/test_registry.py`.
- `tests/no_float/test_no_float.py` — AST-walks `src/geobench` and fails on float literals outside `to_float` and display code.

## Acceptance criteria

```bash
pytest tests/unit/test_model.py tests/unit/test_field.py tests/unit/test_registry.py -q
pytest tests/no_float -q
ruff check . && mypy src
python -c "from geobench.model import Figure; f=Figure.from_json(Figure.example().to_json()); assert f.to_json()==Figure.example().to_json()"
```

Additionally, by hand:
- Inserting a node whose `op` has the wrong arity fails with an error naming the operator and the expected arity.
- A cyclic dependency is rejected with the cycle path in the message.
- `simplify_to_zero` returns `True` for `x - x` and for `sin(x)**2 + cos(x)**2 - 1`, and `False` for `x - 1`.

## Non-goals

- Any operator implementation beyond trivial ones used by tests (T004 owns the catalogue).
- Rendering, solving, judging, MCP.
- Performance work.
