# geobench

**A deterministic plane-geometry kernel with an agent interface (MCP), for authoring competition-grade geometry problems.**

> **Status: pre-alpha (charter stage).** No working kernel yet. The contract that the implementation must satisfy is [`docs/spec.md`](docs/spec.md); the process that produces the implementation is [`docs/ai-workflow.md`](docs/ai-workflow.md); open decisions are tracked in [`docs/decisions.md`](docs/decisions.md).

[中文说明](README.zh-CN.md)

---

## The problem this targets

Authoring one olympiad-grade plane-geometry problem by hand means:

1. invent a configuration that *looks* like a competition figure,
2. pin it to **exact** coordinates (not a hand sketch),
3. prove that the intended relation holds for **every** admissible placement of the free points,
4. prove that nothing degenerates (no coincident points, no parallel-with-no-intersection, no vanishing denominator),
5. redraw the figure to match a typesetting standard, and
6. export it as a problem (statement + figure + answer key).

Steps 3 and 4 are where silent failures live: a problem that *looks* valid can be false, or can collapse for a special placement of the free points. Steps 1, 5 and 6 are where hours go.

`geobench` automates 2–4 with a deterministic kernel, exposes that kernel to any LLM client over MCP, and covers 5–6 with a typesetting-ready export.

## What exists already, and what does not

| | |
|---|---|
| **Research** | AlphaGeometry (DeepMind, 2024), TongGeometry (BIGAI + PKU, *Nature Machine Intelligence*, 2026), GeoGen, FormalGeo / FGeo-Parser, GeoLoom, Math-VR (HKU + Meituan). These prove geometry reasoning is automatable — and they output **datasets and papers**. |
| **Generic tools** | GeoGebra, Desmos, Sketchpad, Cabri. Powerful, general, **not** designed around authoring problems, and their numerics are not exact. |
| **AI problem generators** | Text-first generators (word problems, drill questions). They produce *prose*, not **exact geometric constructions**. |
| **geobench** | The last mile: exact kernel + agent interface + typesetting-ready export + a benchmark that measures validity, not vibes. |

Deliberately **not** in scope: training a geometry model, general-purpose dynamic geometry, 3D (v2), student-facing "solve this" apps.

## Design in one page

```
   LLM client (Claude Code / Cursor / opencode / ...)
        │  MCP over stdio or HTTP
        ▼
  ┌──────────────────────────────────────────────┐
  │ geobench MCP server                          │
  │  geo_state · geo_construct · geo_evaluate    │
  │  geo_verify · geo_solve · geo_variants       │
  │  geo_check_degenerate · geo_render           │
  └──────────────────────────────────────────────┘
        │  all calls are deterministic
        ▼
  ┌──────────────────────────────────────────────┐
  │ kernel (Python · SymPy)                      │
  │  construction graph → exact coordinates       │
  │  judges → proved / refuted / supported / ...  │
  │  degeneracy detectors                        │
  └──────────────────────────────────────────────┘
        │
        ▼
  renderer (SVG · TikZ · PNG)  +  problem files (JSON)
```

Three invariants, in order of importance:

1. **The kernel decides, the model proposes.** An LLM may propose a construction; only the kernel may assert that a relation holds. Every verdict carries evidence.
2. **No floats in the kernel.** Coordinates are exact symbolic expressions; approximations exist only for display.
3. **Every operator is oracle-checked.** Each one is cross-validated against an independent implementation (SymPy / GeoGebra) before it is allowed into the registry.

## Repository layout

```
docs/spec.md          the contract: data model, operators, judges, MCP schemas, evals
docs/decisions.md     open decisions D1–D8, with rationale and alternatives
docs/ai-workflow.md   how the implementation is produced by AI agents, and gated
tasks/                one task per unit of work, each with machine-checkable acceptance
prompts/              prompt templates used to drive implementation
evals/                benchmark definition, metrics, dataset provenance policy
src/geobench/         the kernel and server (not started yet)
```

## Benchmarks

The benchmark measures *validity*, not style. Definitions are frozen in [`evals/README.md`](evals/README.md); measurements are added as the kernel lands.

| Metric | Definition | Result |
|---|---|---|
| `construct_success` | constructions completed without kernel error | pending |
| `oracle_agreement` | coordinate agreement with the independent oracle | pending |
| `verify_precision` | `proved` verdicts surviving adversarial re-sampling | pending |
| `degenerate_rate` | configurations flagged degenerate | pending |
| `problem_validity` | generated problems whose goal is `proved` and non-degenerate | pending |
| `variant_diversity` | pairwise dissimilarity across sampled variants of one family | pending |

## Reproducing

```bash
git clone https://github.com/ycl-berserk/geobench.git
cd geobench
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q                 # unit + oracle + property + degeneracy suites
```

As of the charter stage the test suites do not exist yet; the commands above are the contract the implementation must satisfy.

## Roadmap

- [ ] **M0 — charter** (this commit): spec, decisions, workflow, task format
- [ ] **M1 — kernel skeleton**: construction graph, exact numeric types, operator registry, state store
- [ ] **M2 — oracle harness**: every operator cross-checked against SymPy / GeoGebra
- [ ] **M3 — judges**: `collinear`, `perpendicular`, `concyclic`, `equal_length`, `midpoint_of`, `angle_bisector`, `tangent_to`, `concurrency`
- [ ] **M4 — MCP server**: the eight tools above, with resources for the operator/judge catalogue
- [ ] **M5 — renderer**: SVG + TikZ export, competition style preset
- [ ] **M6 — problem generation**: `geo_variants` + `geo_solve` driven by an LLM client, end-to-end demo
- [ ] **M7 — benchmark**: `evals/` harness and published report

## Contributing

Issues and PRs welcome. Implementation follows [`docs/ai-workflow.md`](docs/ai-workflow.md): work is expressed as a task in `tasks/` with machine-checkable acceptance criteria, and no operator enters the registry without an oracle cross-check.

## License

MIT — see [`LICENSE`](LICENSE). Problem files carry their own provenance record; see [`evals/README.md`](evals/README.md).
