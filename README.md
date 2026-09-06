# rle-harness-template

Template repository for an [RLE](https://github.com/AppSprout-dev/RLE) harness plugin.

RLE benchmarks **harnesses × models** on a RimWorld colony. A harness is whatever turns
colony state into actions each tick — one agent, many, an agent framework, or a coding
agent attached over MCP. Harnesses are discovered through the `rle.harnesses` entry-point
group, so a new one is `pip install`, never a change to RLE core.

## Use this template

1. Click **Use this template** on GitHub (or copy the tree).
2. Rename `rle_harness_template` → `rle_harness_<yourtool>` and the entry-point name in
   `pyproject.toml`.
3. Implement `step()` in `harness.py` (or subclass `rle.harness.cli_base.HeadlessCliHarness`
   to drive an external coding agent through the RLE MCP server).
4. Keep `tests/test_plugin.py` — it is the contract RLE relies on.

## Try it

```bash
uv pip install "rimworld-learning-environment[mcp] @ git+https://github.com/AppSprout-dev/RLE"
uv pip install -e ".[dev]"
pytest

# from an RLE checkout:
python scripts/run_benchmark.py --harness list
python scripts/run_benchmark.py --smoke-test --ticks 3 --harness template
python scripts/run_benchmark.py --harness template --harness-opt work_type=Mining
```

## What RLE gives you

- `rle.harness.BaseHarness` / `StepResult` / `HarnessContext` — the protocol
- `rle.harness.brief.build_brief` — the harness-neutral scenario brief (goals, state,
  MAP_SUMMARY, action catalog)
- `rle.harness.cli_base.HeadlessCliHarness` — scaffold for CLI coding agents over MCP
- `rle.testing.run_harness_smoke` — drives your plugin through the real loop against a
  mock RIMAPI (this repo's CI)

Full guide: [docs/harness-plugins.md](https://github.com/AppSprout-dev/RLE/blob/master/docs/harness-plugins.md).

## License

MIT
