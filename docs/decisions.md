# Open decisions

Every decision below has a **recommended** value that the charter commit already assumes, a **status**, and the **alternatives** that were considered. A decision is *Accepted* when the domain owner says so; the change is then recorded in this file (status + date) and, if it changes behaviour, in [`spec.md`](spec.md) first.

| ID | Decision | Recommended | Status | Sign-off |
|---|---|---|---|---|
| D1 | Implementation stack | Python kernel (SymPy) + local service + web frontend | *proposed* | |
| D2 | Exact-arithmetic implementation | SymPy expressions behind a `Field` protocol | *proposed* | |
| D3 | Kernel data model | Construction graph (§3 of the spec) | *proposed* | |
| D4 | MCP tool contract | Eight tools (§11 of the spec) | *proposed* | |
| D5 | v1 scope | Plane geometry, 16 operators, 8 judges | *proposed* | |
| D6 | Competition figure style | Spec §9.2 — **values need the domain owner** | *proposed* | |
| D7 | Interaction paradigm | Chat-first, with direct manipulation | *proposed* | |
| D8 | Repo, license, language | `geobench`, MIT, English canonical + Chinese README | *proposed* | |

---

## D1 — Implementation stack

**Recommended.** Kernel in Python 3.11+ using SymPy for exact arithmetic; a local service exposing the kernel to the UI; a browser-based frontend (TypeScript, SVG canvas). The MCP server is a thin wrapper over the same service, so the agent path and the human path cannot diverge.

**Why.** The hard part of a geometry kernel is *symbolic simplification and solving*, not rendering — SymPy already has both and is independently trustworthy enough to serve as an oracle for the kernel itself. The frontend is the part the human owner cares about most and wants to own. Browser delivery also means teachers can open a link, which matters more than install friction for this audience.

**Alternatives.**

- *Pure Python desktop (PySide/Qt)*: fewer processes, but web delivery reaches more users and makes the MCP and UI paths share one service. Costs a JS toolchain.
- *All-TypeScript* (exact arithmetic re-implemented): one language, but the hardest component (simplify/solve) would be rewritten from scratch, and JS `Number`/rational handling is weaker.
- *Jupyter-first*: excellent for exploration, poor as a product surface.

**Risks.** SymPy expression blow-up on long constructions → mitigated by D2's `Field` protocol so the arithmetic backend can be swapped (e.g. a rational-only fast path) without touching the operator layer.

## D2 — Exact-arithmetic implementation

**Recommended.** All geometric values are SymPy expressions behind a small `Field` protocol (`add`, `sub`, `mul`, `div`, `sqrt`, `simplify_to_zero`, `to_float`). No float literals anywhere in the kernel (enforced by lint rule, not review).

**Why.** "This relation holds" must mean *identically*, not *numerically close*. A tolerance-based kernel cannot distinguish "proved" from "supported", which is the entire point of the project.

**Alternatives.** *Custom rational + quadratic-extension field*: much faster, but `simplify_to_zero` is where symbolic correctness lives — that is the part not to reinvent.

**Open sub-question.** Whether a rational-only fast path should be added for operator-heavy pipelines (geometry of a full construction can generate deep expressions). Deferred to M3.

## D3 — Kernel data model

**Recommended.** The construction graph of spec §3.1: nodes with `role: free | derived`, explicit `op` + `args` for derived nodes, relations as claims under test, styles separate from geometry.

**Why.** It is the minimal representation that (a) is serializable, (b) is diffable, (c) is the natural intermediate language for an LLM to read and write, and (d) matches the construction-graph formulation used in the research literature (GeoGen, FormalGeo, TongGeometry) without importing their complexity.

**Alternatives.** *GeoGebra `.ggb` XML as the interchange format*: free interoperability, but the format is tied to a GUI application's semantics, does not carry a verification record, and would drag in licence and complexity questions. Keeping `.ggb` as an **export** target is still worthwhile.

## D4 — MCP tool contract

**Recommended.** The eight tools of spec §11.1, with the resources of §11.2, JSON-only responses, and actionable errors.

**Why.** The tool contract *is* the product's agent interface; it is the part other people will build against. It also forces the kernel to expose capabilities at a granularity that is meaningful to a planner rather than to a GUI.

**Alternatives.** *A single `geo_do` tool with a free-form instruction string*: smaller surface, but unauditable and untestable. *HTTP API + separate MCP wrapper*: two contracts to keep in sync.

**Open sub-question.** Whether `geo_propose` (LLM-facing problem proposal) belongs in the kernel or in a separate agent service. Currently excluded from the kernel: the kernel should not contain a model.

## D5 — v1 scope

**Recommended.** Plane geometry only; Tier-A operators (16) and Tier-B judges (8) of spec §5.2 / §6.2; solid geometry and conics explicitly deferred.

**Why.** Every additional geometry domain multiplies the degeneracy catalogue and the oracle battery. Scope creep here is the classic way an open-source geometry tool ends at 40% forever.

**Alternatives.** *Ship 3D early*: a different product, needs a CAD kernel (OpenCascade), and serves a different audience (high-school solid geometry), which is explicitly not the target.

## D6 — Competition figure style

**Recommended.** Spec §9.2, with concrete numeric values confirmed by the domain owner (a competition-experienced reader). Values still to be fixed:

| Attribute | Spec's placeholder | Needs |
|---|---|---|
| Stroke width (figure) | ≈ 0.4 pt | exact value |
| Stroke width (auxiliary/dashed) | thinner | exact value |
| Point radius | 0.8–1.0 pt | exact value |
| Label font / size | Times, ≈ 10 pt | exact value + italic policy |
| Label placement | outside the figure, no overlap | placement rules |
| Reserved labels | `O I H G D E F P Q R M N` | confirm list |
| Circle / segment notation | `⊙O`, `AB` | confirm |
| Figure caption | not inside the image | confirm |

**Why.** This is the moat that no generic tool reproduces, and the part an LLM will guess wrong every time. It must be written down exactly, not paraphrased.

## D7 — Interaction paradigm

**Recommended.** Chat-first: the user states an intent ("construct a triangle where the bisector meets the circumcircle at an equidistant point"), the agent calls the kernel, the figure appears, and the user can then **drag** free points and see the verification status update live. Direct manipulation remains available at all times; the canvas is never modal.

**Why.** Problem authoring is intent-driven (slow by hand, fast by delegation), but the human must be able to correct the machine's guess by dragging — that correction loop is where the user's own taste enters.

**Alternatives.** *Form-first* (fill in a structured form): precise but slow and hostile to exploratory work. *Canvas-first with an AI side panel*: keeps the old workflow and bolts AI onto it; that is the "GeoGebra + chat box" outcome we want to avoid.

**Open sub-question.** Whether the first release needs multi-user/classroom features at all (the recommendation: none — a teacher can open a file).

## D8 — Repository, license, language

**Recommended.** Public repository `github.com/ycl-berserk/geobench`, MIT licence (already in the repository), **English as the canonical language** for code, spec, and README, with a Chinese README (`README.zh-CN.md`) for the domestic audience of teachers and students.

**Why.** The repository is the proof artefact for an AI-collaboration workflow; English reaches the wider contributor pool and matches the international research vocabulary (`operator`, `judge`, `verdict`, `degenerate`), while the Chinese README serves the actual users of the tool.

**Alternatives.** *Chinese-first*: friendlier for the immediate audience, but raises the barrier for external contributors and for AI tools operating on the spec. *Single bilingual README*: drifts out of sync.
