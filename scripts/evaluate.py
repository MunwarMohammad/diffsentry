"""Evaluate against labeled changed-line fixtures, not filenames as fake RAG context."""

import argparse
import asyncio
import json
from pathlib import Path

from reviewer.config import get_settings
from reviewer.graph import review_files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live", action="store_true", help="Use configured OpenAI model (incurs API usage)"
    )
    args = parser.parse_args()
    settings = get_settings()
    settings.review_mode = "live" if args.live else "demo"
    cases = json.loads(Path("fixtures/evaluation.json").read_text())
    true_positive = false_positive = false_negative = 0
    results = []
    for case in cases:
        output = asyncio.run(review_files(case["files"]))
        predicted = {(f.file, f.line, f.agent) for f in output["findings"]}
        expected = {tuple(f) for f in case["expected"]}
        tp, fp, fn = len(predicted & expected), len(predicted - expected), len(expected - predicted)
        true_positive += tp
        false_positive += fp
        false_negative += fn
        results.append({"name": case["name"], "tp": tp, "fp": fp, "fn": fn})
    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    report = {
        "mode": settings.review_mode,
        "model": settings.openai_model if args.live else None,
        "precision": precision,
        "recall": recall,
        "cases": results,
        "limitation": "Small fixture regression suite; not a production quality benchmark.",
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/evaluation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if precision < 0.8 or recall < 0.8:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
