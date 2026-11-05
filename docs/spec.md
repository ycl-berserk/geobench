# geobench — specification

**Version 0.1 (charter) · Status: proposed · This document is the single source of truth for the implementation.**

Every task in [`../tasks/`](../tasks/) references a section of this document. When this document and an implementation disagree, the implementation is wrong.

---

## 1. Scope

### 1.1 In scope (v1)

- **Plane geometry** only. Cartesian plane, 2D.
- A deterministic kernel that can: build constructions from exact primitives, decide geometric relations, detect degeneracy, and render.
- An MCP server exposing that kernel to any MCP client.
- Problem files (statement + figure + verification record) with export to SVG / TikZ / PNG / LaTeX.
- A benchmark measuring the validity of kernel verdicts and of machine-generated problems.

### 1.2 Out of scope (v1)

| Excluded | Why | Revisit |
|---|---|---|
| Solid / 3D geometry | Constraint solving and incidence in 3D are a different order of magnitude of cost; needs a CAD kernel, not a hand-written one | v2, via OpenCascade + three.js |
| Conics (ellipse/parabola/hyperbola) | Not needed by the target audience (junior-secondary and olympiad plane geometry) | v1.1 if asked for |
| Training a geometry model | Research groups (BIGAI+PKU, DeepMind) own this; our leverage is the last mile | never |
| Student-facing "solve this problem" apps | Different product, different audience, not the goal here | — |
| Arbitrary numeric tolerance settings | The kernel is exact; tolerance is a rendering concern only | — |

### 1.3 Target users

1. **Competition students and their coaches** (primary): authoring original problems and problem sets.
2. **Junior-secondary geometry teachers** (secondary): "show me a triangle where this relation holds" → editable figure → typeset handout.

Both users need: an exact figure, a proof that it is not degenerate, and a typeset result. Neither needs a general-purpose dynamic-geometry environment.

## 2. Terminology

| Term | Meaning |
|---|---|
| **construction graph** | The serialized description of a figure: nodes (points, lines, circles), edges (dependencies), and declared relations. |
| **operator (op)** | A deterministic function `Args → Node`, e.g. `point.midpoint(A, B)`. |
| **judge** | A deterministic function `Args → Verdict` about a relation, e.g. `collinear(A, B, C)`. |
| **verdict** | `proved` / `refuted` / `supported` / `undecided`, plus evidence. |
| **degeneracy** | A configuration in which some part of the construction is undefined or collapses. |
| **variant** | A distinct admissible configuration of the same construction family (different placement of free points). |
| **problem file** | One problem, one JSON document. See §10. |
| **oracle** | An independent implementation used to cross-check a kernel operator. See §5.3. |

## 3. Core data model

### 3.1 Construction graph

```jsonc
{
  "version": "1.0",
  "id": "fig_0001",
  "nodes": [
    { "id": "A", "kind": "point", "role": "free",
      "coords": ["0", "0"], "label": "A", "style": {} },

    { "id": "B", "kind": "point", "role": "free",
      "coords": ["4", "0"], "label": "B", "style": {} },

    { "id": "M", "kind": "point", "role": "derived",
      "op": "point.midpoint", "args": ["A", "B"], "label": "M", "style": {} },

    { "id": "l1", "kind": "line", "role": "derived",
      "op": "line.free", "args": ["A", "B"], "label": "AB", "style": {} },

    { "id": "c1", "kind": "circle", "role": "derived",
      "op": "circle.through", "args": ["A", "B", "C"], "label": "⊙O", "style": {} }
  ],
  "relations": [
    { "id": "r1", "kind": "collinear", "args": ["A", "M", "C"], "expected": true }
  ],
  "meta": { "tags": [], "source": "manual", "notes": "" }
}
```

**Rules.**

- `id` is unique within a figure; stable across edits; used by all tool calls.
- `role: "free"` nodes carry exact coordinates and are the *only* source of variation. `role: "derived"` nodes carry an `op` and `args` and are **never** allowed to store coordinates that contradict their operator. The kernel recomputes derived nodes on every change; stored coordinates are a cache only.
- `coords` are exact expressions serialized as strings (see §4).
- `relations` are *claims under test*. The kernel never assumes a claim is true; it is the thing `geo_verify` adjudicates. `expected` records the author's intent, used for regression tests and for the "false problem" detector.
- The graph is a DAG. Cycles are rejected at insertion with a precise error.

### 3.2 Node kinds

`point`, `line`, `circle`. v1 has no other primitives.

| Kind | Parameters |
|---|---|
| `point` | exact `(x, y)`; may additionally carry `on: [node ids]` for incidence hints (advisory only, verified by judges) |
| `line` | exact point + direction, or exact implicit equation `ax + by + c = 0` with `a² + b² ≠ 0` |
| `circle` | exact center + exact squared radius, or exact implicit equation `x² + y² + dx + ey + f = 0` with `d² + e² - 4f > 0` |

### 3.3 Style

Styles never affect geometry. A `style` block holds rendering attributes only: `visible`, `color`, `line_width`, `line_style` (`solid`/`dashed`/`dotted`), `point_size`, `fill`, `label`, `label_pos`. §9 defines the competition preset.

## 4. Numeric strategy

- **Exactness is mandatory.** All coordinates and all judge computations use exact symbolic expressions (`sympy` `Rational`, algebraic roots, symbolic sums/products).
- **No implicit floats.** A literal float in an operator argument is a hard error, not a warning. Approximation is produced only at the render boundary, from the exact value.
- **Promotion of fields is automatic.** Rational → algebraic (with `sqrt`) as soon as an operator needs it. No manual "switch to float mode".
- **Squared radii, not radii.** `circle` stores `r²` exactly; `r` is derived and may be irrational. This avoids `sqrt` in every downstream expression.
- **Coordinates of intersections** are returned as exact expressions *and* as a chosen numeric root, with the root index recorded, so the "which intersection?" ambiguity is explicit rather than hidden.

## 5. Operator catalogue

### 5.1 Registry contract

An operator declares:

```jsonc
{
  "id": "point.midpoint",
  "kind": "point",
  "args": [{ "name": "a", "type": "point" }, { "name": "b", "type": "point" }],
  "exact": true,
  "returns": { "type": "point" },
  "degenerate_when": ["a == b"],
  "oracle": "sympy:segment_midpoint",
  "since": "v1"
}
```

`degenerate_when` is part of the contract: it is how §7's detectors know when to flag a result.

### 5.2 v1 operators

**Tier A — required for v1 (16).**

| Op | Args | Notes |
|---|---|---|
| `point.free` | `(x, y)` exact | the only source of variation |
| `line.free` | `(a, b)` points | |
| `circle.free` | `(center, r²)` | |
| `point.midpoint` | `(a, b)` | |
| `point.foot` | `(p, line)` | perpendicular foot |
| `point.intersect_lines` | `(l1, l2)` | degenerate when parallel |
| `point.intersect_line_circle` | `(line, circle, index)` | `index ∈ {0,1}` |
| `point.intersect_circles` | `(c1, c2, index)` | degenerate when tangent / disjoint / concentric |
| `point.circumcenter` | `(a, b, c)` | degenerate when collinear |
| `point.incenter` | `(a, b, c)` | |
| `point.orthocenter` | `(a, b, c)` | |
| `point.centroid` | `(a, b, c)` | |
| `point.angle_bisector_point` | `(a, b, c, side)` | bisector ∩ `side` |
| `line.perpendicular_through` | `(p, line)` | |
| `line.parallel_through` | `(p, line)` | |
| `circle.through` | `(a, b, c)` | degenerate when collinear |

**Tier B — v1.1 (18).** `point.reflect`, `point.tangent_point`, `point.inverse`, `point.arc_midpoint`, `point.touchpoint`, `point.excenter`, `point.symmedian_point`, `point.nine_point_center`, `line.angle_bisector`, `line.perpendicular_bisector`, `line.median`, `line.altitude`, `line.tangent_at`, `circle.incircle`, `circle.circumcircle`, `point.projection`, `point.rotate`, `point.scale_from`.

**Tier C — out of v1.** 3D ops, conic ops, loci, transformations as first-class entities.

### 5.3 Oracle requirement

Every operator in the registry **must** ship with an oracle cross-check before it is marked `since: "v1"`. The oracle is an independent implementation (SymPy geometry / GeoGebra JS API / hand-computed closed form) run on a fixed battery of ≥ 20 configurations, including degenerate ones. `tasks/T002` defines the harness. An operator without a passing oracle does not enter the registry.

## 6. Judge catalogue

### 6.1 Verdict semantics

| Verdict | Meaning | Evidence required |
|---|---|---|
| `proved` | The relation is an algebraic identity of the construction — it holds for **every** admissible placement of the free points | the reduced symbolic expression (which must reduce to `0`) and the free-point assumptions used |
| `refuted` | The relation does not hold in general | a concrete admissible configuration where it fails (exact coordinates) |
| `supported` | The relation holds for all sampled configurations but is not proven | the sample count, the sampling scheme, and the number of free-point degrees of freedom left unconstrained |
| `undecided` | The kernel cannot decide | the reason (unsupported operator, field degree blow-up, ambiguous relation) |

`supported` is never silently upgraded to `proved`.

### 6.2 v1 judges (8)

| Judge | Args | Typical use |
|---|---|---|
| `collinear` | `(p1, p2, p3)` | Menelaus, Desargues |
| `perpendicular` | `(l1, l2)` or `(p, l)` | orthogonality |
| `concyclic` | `(p1, p2, p3, p4)` | Miquel, power of a point |
| `equal_length` | `(seg1, seg2)` | isosceles, congruence |
| `midpoint_of` | `(m, a, b)` | medians, parallelograms |
| `angle_bisector` | `(p, a, b, c)` | bisector theorems |
| `tangent_to` | `(line, circle)` | tangent constructions |
| `concurrency` | `(l1, l2, l3)` | Ceva, radical axes |

**v1.1 judges:** `parallel`, `equal_angle`, `similar` (AA), `area_ratio`, `segment_ratio`, `power_equal`, `isosceles`, `right_angle`.

### 6.3 Symmetry requirement

Each judge ships with both a **positive** test (the relation holds) and a **counterexample** test (the relation fails). A judge that cannot produce a refutation for a mutated figure is not trustworthy and does not ship.

## 7. Degeneracy model

A configuration is *degenerate* if any of the following holds. Each detector returns the offending node and the reason.

| Detector | Condition |
|---|---|
| `coincident_points` | two distinct point ids have equal coordinates |
| `zero_length` | a segment used in a length relation has zero length |
| `collinear_triple` | three points that define a circle (circumcircle, incenter) are collinear |
| `parallel_no_intersection` | two lines that must intersect are parallel |
| `tangent_multiplicity` | a circle-circle / line-circle intersection has multiplicity ≠ the expected number of distinct points |
| `zero_denominator` | a ratio or area expression divides by zero |
| `undefined_angle` | an angle is taken between coincident points or opposite rays |
| `circle_degenerate` | `r² ≤ 0` for a circle node |
| `off_domain` | an operator's result is outside its declared domain (e.g. `point.inverse` at the center) |

**Invariant:** `geo_check_degenerate` must report *every* applicable detector for a figure, not just the first.

## 8. Constraint solving

`geo_solve` takes a set of constraints (incidence, collinearity, concyclicity, length/angle equalities, parallelism, perpendicularity) plus a construction template, and returns admissible configurations.

Contract:

- The solver is **numeric-first** (Newton / continuation on the free-point coordinates), with **symbolic verification** of the returned solution against the constraint set.
- The response reports: number of solutions found (within tolerance), whether the solution is **generic** (not on any degeneracy locus), the **degrees of freedom** remaining, and the free-point assignments.
- A numeric solution that fails symbolic verification is discarded, not returned with a warning.
- Solving is a **sampling** mechanism for variants (§11) and for finding configurations where a claim fails — not a general-purpose solver.

## 9. Rendering and export

### 9.1 Outputs

| Target | Purpose |
|---|---|
| SVG | lossless, scriptable, embeds in LaTeX via `svg` + `inkscape`, editable by teachers |
| TikZ / PGF | native LaTeX figure for problem sets (Chinese olympiad papers are usually LaTeX or Word) |
| PNG | preview / web / Word paste |
| JSON | the problem file (§10) |

### 9.2 Competition style preset (Chinese olympiad papers)

Required attributes of the preset (final values to be confirmed with the domain owner):

- Pure black strokes, no colors; background transparent or white.
- Line width: figure strokes ≈ 0.4 pt, auxiliary construction lines dashed.
- Free points: filled black discs, radius ≈ 0.8–1.0 pt; derived points may be hollow.
- Labels: upright serif (Times), italic only for variables, ≈ 10 pt; placed outside the figure, never overlapping a stroke.
- Auxiliary lines (perpendicular feet, extension rays) dashed and unlabeled by default.
- Circle labels as `⊙O`; segment as `AB`; the figure caption is **not** drawn inside the image (it is part of the statement: "如图").
- Reserved label set: `A B C …` for vertices, `O` for circumcenter, `I` for incenter, `H` for orthocenter, `G` for centroid, `D E F` for feet, `P Q R …` for free points, `M N` for midpoints.

### 9.3 Round-trip

Rendering is a pure function of `(construction graph, style, view transform)`. No hidden state, so a figure exported today must be byte-identical when re-exported from the same file — this is a regression test, not a nicety.

## 10. Problem file format

One problem, one JSON document, versioned:

```jsonc
{
  "id": "geo-2026-0001",
  "version": 1,
  "statement": { "zh": "如图，…", "en": "As shown, …" },
  "figure": { "construction graph (§3.1)" },
  "givens": ["AD ⊥ BC", "E 为 BC 中点"],
  "goal": "证明 P, Q, R 三点共线",
  "relations": [ { "kind": "collinear", "args": ["P", "Q", "R"], "expected": true } ],
  "verification": {
    "verdict": "proved",
    "evidence": "…",
    "checked_at": "2026-11-05T00:00:00Z",
    "kernel_version": "0.1.0"
  },
  "degeneracy": { "status": "clean", "reports": [] },
  "variants": [ { "id": "v1", "figure_ref": "fig_0002", "notes": "锐角三角形" } ],
  "difficulty": { "tier": "联赛", "tags": ["相似", "面积比"], "est_minutes": 25 },
  "provenance": { "source": "self-authored", "license": "CC0-1.0", "notes": "" }
}
```

`verification` and `degeneracy` are **required**: a problem file without a `proved` verdict and a clean degeneracy report cannot be exported as a "ready" problem. It may still be saved as a draft.

## 11. MCP interface

Transport: stdio (default) and streamable HTTP. The server is a pure function of its figure state; the client owns nothing but the figure id.

### 11.1 Tools

| Tool | Input | Output |
|---|---|---|
| `geo_state` | `{ figure_id? }` | the construction graph, validation summary, active degeneracy reports |
| `geo_construct` | `{ figure_id?, ops: [ { id?, op, args } ], mode: "apply" \| "dry-run" }` | created / updated / removed node ids, per-op status, precise errors |
| `geo_evaluate` | `{ figure_id?, expr }` | exact value + display approximation, for expressions like `Angle(B,A,C)`, `Distance(A,B)`, `Area(A,B,C)` |
| `geo_verify` | `{ figure_id?, relation }` | verdict + evidence + the assumptions under which it holds |
| `geo_solve` | `{ figure_id?, constraints, template, count }` | configurations + solution report (count, genericity, degrees of freedom) |
| `geo_variants` | `{ figure_id?, family, count, seed }` | distinct admissible configurations of a construction family, with degeneracy reports |
| `geo_check_degenerate` | `{ figure_id? }` | the full list of degeneracy reports |
| `geo_render` | `{ figure_id?, format: "svg"\|"tikz"\|"png", style: "competition"\|"plain", view? }` | the rendered artifact |

### 11.2 Resources

| URI | Content |
|---|---|
| `geobench://spec/operators` | the operator registry (§5) |
| `geobench://spec/judges` | the judge catalogue (§6) |
| `geobench://style/competition` | the competition style preset (§9.2) |
| `geobench://figure/{id}` | one construction graph |

### 11.3 Agent-facing rules

- Every tool response is **JSON**, never prose, and includes a machine-readable `status` (`ok` / `error` / `degraded`).
- Errors are **actionable**: they name the offending operator, argument index, and the reason (unknown node id, wrong argument type, degenerate configuration, ambiguous intersection index).
- Tools are **idempotent where possible** (`geo_construct` with explicit ids is idempotent).
- No tool performs hidden network access, and no tool mutates state outside the addressed figure.

## 12. Evaluation harness

Located in [`../evals/`](../evals/). Metrics (definitions frozen in `evals/README.md`):

- `construct_success` — fraction of attempted constructions that complete without error.
- `oracle_agreement` — fraction of operator outputs matching the oracle exactly.
- `verify_precision` — fraction of `proved` verdicts that survive adversarial re-sampling with different free points.
- `degenerate_rate` — fraction of generated configurations that a detector flags.
- `problem_validity` — fraction of generated problems whose goal is `proved` and whose degeneracy report is clean.
- `variant_diversity` — mean pairwise dissimilarity across variants of one family.

Additional reporting requirement: every benchmark run records the kernel version, the seed set, and the exact command, so a number in this repository is reproducible.

## 13. Acceptance criteria

A component is done when:

1. It has a task in [`../tasks/`](../tasks/) with machine-checkable acceptance criteria.
2. Its unit tests pass, including at least one **counterexample** test per judge.
3. Its operators have passing oracle cross-checks (§5.3).
4. Its degenerate cases are covered by the degeneracy suite (§7).
5. The kernel contains no floating-point arithmetic on geometric quantities (enforced by a lint rule, not by review).
6. The public API matches this document; if it must change, this document changes first.

## 14. Open items

Tracked in [`decisions.md`](decisions.md): D1 stack, D2 exact-arithmetic implementation, D3 data model confirmation, D4 MCP contract confirmation, D5 v1 scope of relations, D6 competition style values, D7 interaction paradigm, D8 repository/branding.
