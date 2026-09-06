"""rle-harness-claude-code — Claude Code as an RLE harness.

Claude Code (https://code.claude.com) is Anthropic's terminal coding agent
with a scriptable headless mode (``claude -p``) and native MCP support. This
package registers it with RLE (https://github.com/AppSprout-dev/RLE) so

    python scripts/run_benchmark.py --harness claude-code --model sonnet

benchmarks *Claude Code as the harness* on the same scenarios, saves and
scoring as every other harness. Each tick is one headless invocation
(``claude -p ... --output-format json``) resuming the previous session; the
agent acts through the RLE MCP tools and calls ``end_turn``.
"""

from rle_harness_claude_code.plugin import PLUGIN, ClaudeCodePlugin

__all__ = ["PLUGIN", "ClaudeCodePlugin"]
