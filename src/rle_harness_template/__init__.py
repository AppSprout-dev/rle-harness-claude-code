"""rle-harness-template — copy this repo to build an RLE harness plugin.

RLE (https://github.com/AppSprout-dev/RLE) benchmarks *harnesses x models*.
A harness is whatever turns colony state into actions each tick. This
package registers one under the ``rle.harnesses`` entry-point group so
``python scripts/run_benchmark.py --harness template`` just works after
``pip install``.

Two shapes are possible:

* Subclass :class:`rle.harness.BaseHarness` (below) and return an
  ``ActionPlan`` — the environment executes it.
* Subclass :class:`rle.harness.cli_base.HeadlessCliHarness` to drive an
  external coding agent over the RLE MCP server — the agent acts through
  tools during its turn and the ledger is scored (see the OpenCode / Grok
  Build harness repos for real examples).
"""

from rle_harness_template.plugin import PLUGIN, TemplatePlugin

__all__ = ["PLUGIN", "TemplatePlugin"]
