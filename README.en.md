# geobench (English)

**A deterministic plane-geometry kernel with an agent interface (MCP), for authoring competition-grade geometry problems.**

> **Status: alpha.** The kernel decides, the DSL parses, the MCP server answers. Implemented so far: the construction graph, exact arithmetic, 14 operators (every one of them cross-checked against an independent implementation), 9 judges, competition-style SVG rendering, the **Chinese geometry DSL** (a deterministic parser) and the **MCP server** (`geo_state` / `geo_construct` / `geo_evaluate`).
>
> Not implemented yet: constraint solving, the full degeneracy catalogue, the renderer service, the interactive front end, and the remaining MCP tools.
>
> The contract is [`docs/spec.md`](docs/spec.md) (Chinese, canonical); the DSL grammar is [`docs/dsl-spec.md`](docs/dsl-spec.md) (Chinese); the process is [`docs/ai-workflow.md`](docs/ai-workflow.md) (Chinese).
>
> 中文版（正本）：[README.md](README.md)

---

## What you can do right now

```bash
pip install -e ".[dev]"
python scripts/demo.py        # build → judge → render → export a problem file
python scripts/dsl_demo.py    # Chinese DSL → construction graph → judge → render → round trip
geobench-mcp                  # start an MCP server over stdio for any agent to connect to
```

The demo script builds a triangle (circumcircle, midpoint, foot of an altitude, circumcentre) and then judges its claims one by one. All three come back `proved` in the **identity** scope — meaning "true for every admissible placement of the free points", not "true of this one picture". That distinction is the whole point of the project, and the line between this and "AI draws a picture".

Outputs: `examples/demo-figure.svg` (drop straight into LaTeX or Word), `examples/demo-figure.png`, and `examples/demo-problem.json` (with the judgement records).

### As an MCP server

```bash
geobench-mcp        # stdio transport; point an MCP client at this command
```

Three tools are exposed (the contract is [`docs/spec.md`](docs/spec.md) §11):

| Tool | What it does |
|---|---|
| `geo_state` | read back the whole construction graph, a validation summary and the degeneracy report |
| `geo_construct` | apply a batch of constructions (`dry-run` previews them); the batch is atomic — if anything fails, nothing changes |
| `geo_evaluate` | evaluate `Angle(B,A,C)` / `Distance(A,B)` / `Area(A,B,C)`, returning both the **exact** value and a display approximation |

Every response carries `status ∈ {ok, error, degraded}`. `error` means *"your request is wrong — fix it"*; `degraded` means *"your request was fine, but this configuration is degenerate"*. Those need different next steps, so the kernel reports them separately.

---

## The problem this targets

Authoring one olympiad-grade plane-geometry problem by hand means:

1. inventing a configuration that *looks* like a competition figure,
2. pinning it to **exact** coordinates (not a hand sketch),
3. proving that the intended relation holds for **every** admissible placement of the free points,
4. proving that nothing degenerates (no coincident points, no parallel-with-no-intersection, no vanishing denominator),
5. redrawing the figure to match a typesetting standard, and
6. exporting it as a problem (statement + figure + answer key).

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
   natural language (human / AI-translated)
        │  → Chinese geometry DSL (spec §12, deterministic subset)
        ▼
  ┌──────────────────────────────────────────────┐
  │ geobench kernel (Python · SymPy)             │
  │  DSL parse → construction graph → exact coords│
  │  judges → proved / refuted / supported / …    │
  │  degeneracy detectors                        │
  └──────────────────────────────────────────────┘
        │  MCP (stdio / HTTP) → any agent
        ▼
   Claude Code / Cursor / opencode / …
        │
        ▼
  renderer (SVG · TikZ · PNG)  +  problem files (JSON)
```

Three invariants, in order of importance:

1. **The kernel decides, the model proposes.** An LLM may propose a construction (by writing DSL); only the kernel may assert that a relation holds. Every verdict carries evidence.
2. **No floats in the kernel.** Coordinates are exact symbolic expressions; approximations exist only for display.
3. **Every operator is oracle-checked.** Each one is cross-validated against an independent implementation (SymPy / GeoGebra) before it is allowed into the registry.

## Two input paths

| Path | Route | Use |
|---|---|---|
| **Draw / manipulate** | drag points, pick tools → construction graph | refining an idea, exploring configurations |
| **text2graph** | natural language → (AI or human) → DSL → construction graph | starting from scratch, translating a statement into a figure, batch generation by agents |

Both paths converge on the *same* construction graph; validation, degeneracy checking, rendering and problem export are identical downstream. The DSL is a deterministic subset: it covers the common constructions, an AI translates free-form Chinese into that subset, and every translation must pass the parser.

## Repository layout

```
docs/spec.md          the contract: model, DSL, operators, judges, MCP schemas, evals
docs/dsl-spec.md      the Chinese geometry DSL grammar (notation, statements, gap list)
docs/decisions.md     decision log D1–D15 with rationale and alternatives
docs/ai-workflow.md   how the implementation is produced by AI agents, and gated
tasks/                one task per unit of work, each with machine-checkable acceptance
prompts/              prompt templates used to drive implementation
evals/                benchmark definition, metrics, dataset provenance policy
examples/             demo artefacts: SVG / PNG / problem files
scripts/              demos and fixture generation
src/geobench/         the kernel and the MCP server
tests/oracle/         the oracle harness and its fixtures
tests/contract/       the live interface against the specification
tests/integration/    a real process, a real client, a real protocol
```

## Benchmarks

The benchmark measures *validity*, not style. Definitions are frozen in [`evals/README.md`](evals/README.md).

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
pytest -q                 # unit + oracle + property + contract + integration
python scripts/demo.py    # end-to-end demo
```

## Roadmap

Task-flow driven, no fixed dates (see [`tasks/`](tasks/README.md)):

- [x] **M0 charter** — spec, decisions, process, task format
- [x] **M1 kernel skeleton** — construction graph, symbolic + placement coordinates, exact arithmetic, operator registry
- [x] **M2 oracle harness** — 14 operators × 380+ fixtures, all cross-validated
- [x] **M3 judges** — 9 judges, two scopes, counterexample tests
- [x] **M4 renderer** — competition-figure preset + SVG (TikZ to come)
- [x] **M5 DSL** — Chinese geometry DSL grammar, recursive-descent parser, round trip
- [x] **M6 MCP server** — `geo_state` / `geo_construct` / `geo_evaluate`
- [ ] **M7 degeneracy detectors** — the nine of spec §7
- [ ] **M8 automatic problem generation** — variant sampling, constraint solving, an LLM in the loop
- [ ] **M9 benchmark** — the evaluation framework and a public report

## Contributing

Issues and PRs welcome. Implementation follows [`docs/ai-workflow.md`](docs/ai-workflow.md): work is expressed as a task in `tasks/` with machine-checkable acceptance criteria, and no operator enters the registry without an oracle cross-check.

## License

MIT — see [`LICENSE`](LICENSE). Problem files carry their own provenance record.
