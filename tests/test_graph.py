import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from reviewer.config import get_settings
from reviewer.diff import added_lines, prepare_files, validate_findings
from reviewer.graph import review_files, run_agent
from reviewer.models import AgentOutput, Finding


def test_diff_coordinates_and_dedup():
    patch_text = "@@ -10,2 +10,3 @@\n keep\n-old\n+new\n+other"
    assert list(added_lines(patch_text)) == [(11, "new"), (12, "other")]
    finding = Finding(file="app.py", line=11, message="Bug", severity="warning", agent="security")
    findings, warnings = validate_findings(
        [
            finding,
            finding.model_copy(update={"agent": "architecture"}),
            finding.model_copy(update={"line": 999}),
        ],
        [{"filename": "app.py", "patch": patch_text}],
    )
    assert len(findings) == 1
    assert "1 findings" in warnings[0]


def test_binary_truncated_and_oversize_are_explicit():
    files, warnings = prepare_files(
        [
            {"filename": "binary.png"},
            {"filename": "large.py", "patch": "@@ -0,0 +1 @@\n+x", "additions": 2},
            {"filename": "budget.py", "patch": "@@ -0,0 +1 @@\n+x", "additions": 1},
        ],
        limit=1,
    )
    assert not files and len(warnings) == 3


def test_four_agent_graph_no_reducer_duplicates():
    files = json.loads(Path("fixtures/files.json").read_text())
    result = asyncio.run(review_files(files))
    assert len(result["findings"]) == 3
    assert len(result["candidates"]) == 3
    assert {f.agent for f in result["findings"]} == {"security", "architecture", "static_analysis"}


def test_live_structured_output_and_refusal():
    get_settings().review_mode = "live"
    get_settings().openai_api_key = "test-only"
    client = AsyncMock()
    client.responses.parse.return_value = SimpleNamespace(
        status="completed", output_parsed=AgentOutput(findings=[])
    )
    with patch("reviewer.graph.AsyncOpenAI") as constructor:
        constructor.return_value.__aenter__.return_value = client
        assert asyncio.run(run_agent("security", [], [])) == []
        assert client.responses.parse.call_args.kwargs["store"] is False
        client.responses.parse.return_value = SimpleNamespace(
            status="incomplete", output_parsed=None
        )
        with pytest.raises(RuntimeError, match="incomplete"):
            asyncio.run(run_agent("security", [], []))


def test_agent_failure_does_not_become_clean_review():
    with patch(
        "reviewer.graph.run_agent", new=AsyncMock(side_effect=RuntimeError("provider unavailable"))
    ):
        with pytest.raises(RuntimeError):
            asyncio.run(review_files([]))
