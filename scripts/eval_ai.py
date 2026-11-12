"""Run the evaluation set against a real model service.

This is the **manual** runner: it talks to the network, so it is not
part of CI (CI uses a fake provider -- see ``tests/eval``).  Run it
when the skill changes, to see the pass rate move:

    python scripts/eval_ai.py                 # everything
    python scripts/eval_ai.py 锐角             # only the cases whose name matches
    python scripts/eval_ai.py --show          # also print the figures
    python scripts/eval_ai.py --only statements   # only the problem statements

There are two reports, and they answer two different questions:

- the **cases** ask whether the model knows our language;
- the **statements** ask whether the model can take a problem
  statement and produce a figure that satisfies it.

The second one is the product question, and it is the harder one.

The service is the one the studio would use: the environment first,
then the key file, then the app's own settings.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from evals.cases import CASES  # noqa: E402
from evals.harness import run_all_statements, run_case  # noqa: E402
from evals.statements import STATEMENTS  # noqa: E402

from geobench.ai_settings import resolve_provider  # noqa: E402
from geobench.operators import register_builtins  # noqa: E402
from geobench.registry import OperatorRegistry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pattern", nargs="?", default="", help="only the ones whose name matches"
    )
    parser.add_argument("--show", action="store_true", help="print the figures too")
    parser.add_argument("--retries", type=int, default=2, help="how many tries the model gets")
    parser.add_argument(
        "--only",
        choices=("cases", "statements", "both"),
        default="both",
        help="which half of the evaluation set to run",
    )
    args = parser.parse_args()

    resolution = resolve_provider()
    if not resolution.ok:
        print(f"没有可用的模型服务：{resolution.reason}", file=sys.stderr)
        return 1
    print(f"服务：{resolution.provider.name}（密钥来自 {resolution.source_kind}: {resolution.source_name}）")
    print()

    registry = OperatorRegistry()
    register_builtins(registry)

    passed = 0
    total = 0

    if args.only in ("cases", "both"):
        print("=" * 78)
        print("契约用例：模型知不知道我们的语言")
        print("=" * 78)
        cases = [case for case in CASES if args.pattern in case.name]
        for case in cases:
            result = run_case(resolution.provider, case, registry, retries=args.retries)
            mark = "PASS" if result.passed else "FAIL"
            print(f"[{mark}] {case.name}  (attempts={result.attempts})")
            if args.show:
                print(result.text)
            for reason in result.reasons():
                print(f"        · {reason}")
            total += 1
            passed += 1 if result.passed else 0
        print()
        print(f"契约用例：{passed}/{total} 通过")
        print()

    if args.only in ("statements", "both"):
        print("=" * 78)
        print("真实题面：说一句话，能不能得到满足条件的图")
        print("=" * 78)
        statements = [
            statement for statement in STATEMENTS if args.pattern in statement.name
        ]
        report = run_all_statements(
            resolution.provider, registry, tuple(statements), retries=args.retries
        )
        print(report.summary())
        if args.show:
            for result in report.results:
                print("-" * 74)
                print(result.statement.name)
                print(result.text)
        passed += report.satisfied
        total += report.total

    print()
    print(f"合计：{passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
