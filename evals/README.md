# Evaluation harness

The benchmark measures **validity**, not taste. Every number in this repository must be reproducible: a report states the kernel version, the fixture/seed set, and the exact command.

## Tiers

### Tier 1 — operator correctness

Does the kernel compute the right thing?

- Metric `oracle_agreement`: fraction of operator outputs that match the oracle implementation exactly (symbolic equality after canonicalisation).
- Metric `construct_success`: fraction of attempted constructions that complete without a kernel error.
- Fixture set: `tests/oracle/fixtures/*.json` (≥ 20 configurations per operator, ≥ 3 degenerate).

### Tier 2 — judge correctness

Does the kernel judge correctly?

- Metric `verify_precision`: fraction of `proved` verdicts that survive adversarial re-sampling with different free points.
- Metric `refute_precision`: fraction of `refuted` verdicts that are backed by an explicit counterexample configuration (the spec requires this; a refutation without a witness is a failure).
- Required test shape: every judge has one positive case and one counterexample case (spec §6.3).

### Tier 3 — problem generation

Do generated problems hold up?

- Metric `problem_validity`: fraction of generated problems whose goal is `proved` **and** whose degeneracy report is clean.
- Metric `degenerate_rate`: fraction of generated configurations flagged by at least one detector.
- Metric `variant_diversity`: mean pairwise dissimilarity across variants of one construction family (distance between normalised free-point placements).
- Human rubric (0–2 per dimension, reported separately, never merged into the automated metrics): *is this a good competition problem?* — non-trivial, non-degenerate, has a discoverable idea, figures cleanly.
- Report generator prompts and seeds; the model, its version, and the sampling temperature used.

## Thresholds (proposed — confirm before the first benchmark run)

| Metric | Threshold | Rationale |
|---|---|---|
| `oracle_agreement` | = 1.0 | Any mismatch means an operator is wrong; there is no "mostly right" |
| `verify_precision` | ≥ 0.98 | Below this, the kernel is not trustworthy enough for a teacher to rely on |
| `refute_precision` | = 1.0 | A refutation without a witness is not a refutation |
| `degenerate_rate` | ≤ 0.05 on curated families | Above this the sampler is producing junk configurations |
| `problem_validity` | ≥ 0.90 | The headline number of the project |

## Dataset provenance policy

- **No verbatim reproduction of copyrighted problem text.** Problem statements are re-typed and paraphrased from public sources, or authored from scratch, and each file records its `provenance` (`source`, `license`, `notes`).
- Self-authored problems are released under `CC0-1.0`.
- Benchmark fixtures for Tier 1 and 2 are synthetic (randomly generated configurations), so no third-party content is involved.
- A benchmark set that includes third-party problem text must ship with an explicit licence note per item.

## Reports

`evals/reports/<YYYY-MM-DD>-<kernel-version>.md`, containing:

1. environment (OS, Python, SymPy version, model and version if an LLM was involved),
2. the exact command,
3. the metrics table with raw counts, not only percentages,
4. a list of failures with the minimal reproducing case,
5. the git commit under test.

Reports are committed; a metric quoted in the README must point at a report file.
