"""Contract tests every RLE harness package should run in CI."""

from __future__ import annotations

import pytest
from rle.harness import HarnessOptionsError, get_plugin, harness_names
from rle.testing import run_harness_smoke

NAME = "template"


def test_registered_via_entry_point() -> None:
    assert NAME in harness_names()
    plugin = get_plugin(NAME)
    assert plugin.available().ok


async def test_smoke_runs_through_the_loop() -> None:
    report = await run_harness_smoke(NAME, ticks=3)
    assert report.ok
    assert len(report.ticks) == 3
    # our one write per tick reached RIMAPI
    assert all(t.execution.executed == 1 for t in report.ticks)
    assert report.describe["harness"] == NAME


async def test_options_are_validated() -> None:
    report = await run_harness_smoke(NAME, ticks=1, options={"work_type": "Mining", "priority": 2})
    assert report.ok
    with pytest.raises(HarnessOptionsError):
        await run_harness_smoke(NAME, ticks=1, options={"priority": 9})
