"""Offline graph demo: uv run python -m scripts.demo."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from reviewer.config import get_settings
from reviewer.diff import prepare_files
from reviewer.graph import review_files
from reviewer.summary import summary


def main():
    if get_settings().review_mode != "demo":
        raise SystemExit("Set REVIEW_MODE=demo for this offline demo")
    files, warnings = prepare_files(json.loads(Path("fixtures/files.json").read_text()), 100_000)
    result = asyncio.run(review_files(files))
    report = {
        "mode": "demo",
        "head_sha": "a" * 40,
        "findings": [f.model_dump() for f in result["findings"]],
        "warnings": warnings
        + result["warnings"]
        + ["DEMO: deterministic example rules, not an AI review"],
    }
    output = Path("reports")
    output.mkdir(exist_ok=True)
    (output / "demo.json").write_text(json.dumps(report, indent=2))
    markdown = summary(SimpleNamespace(**report))
    (output / "demo.md").write_text(markdown)
    print(markdown)


if __name__ == "__main__":
    main()
