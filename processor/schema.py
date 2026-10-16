"""
Emit schema/converters.json from the registry (`make schemas`).

pennsieve-mcp vendors a copy so plot_file can tell, per package, whether this
stage will convert (then it runs on Fargate: `executionTarget: standard`) or
pass through (then Lambda is enough: `executionTarget: lambda`), without
hardcoding the format list. Same arrangement as quick-plot's templates.json.
"""

import argparse
import json
from pathlib import Path

from processor.converters import CONVERTERS


def build() -> dict:
    return {
        "converters": [
            {
                "name": c.NAME,
                "input_extensions": list(getattr(c, "INPUT_EXTENSIONS", ())),
                "output_extension": c.OUTPUT_EXTENSION,
                "execution_target": "standard",
            }
            for c in CONVERTERS
        ],
        "pass_through_execution_target": "lambda",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="schema")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "converters.json").write_text(json.dumps(build(), indent=2) + "\n")
    print(f"wrote {out / 'converters.json'}")


if __name__ == "__main__":
    main()
