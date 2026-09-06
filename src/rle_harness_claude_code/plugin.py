"""Entry point for ``--harness claude-code``."""

from __future__ import annotations

from pydantic import BaseModel
from rle.harness import Availability, BaseHarness, HarnessContext
from rle.testing.scripted_agent import ScriptedMcpHarness

from rle_harness_claude_code.harness import ClaudeCodeHarness, binary_version, resolve_binary
from rle_harness_claude_code.options import ClaudeCodeOptions


class ClaudeCodePlugin:
    name = "claude-code"
    description = (
        "Claude Code coding agent (headless `claude -p`, session resumed each tick) acting "
        "through the RLE MCP tools."
    )

    def available(self) -> Availability:
        if resolve_binary("claude") is not None:
            return Availability.available()
        return Availability.missing(
            "claude binary not on PATH. "
            "Install Claude Code (https://code.claude.com) or pass "
            "--harness-opt binary=/path/to/claude.",
        )

    def option_schema(self) -> type[BaseModel]:
        return ClaudeCodeOptions

    def create(self, ctx: HarnessContext, options: BaseModel) -> BaseHarness:
        assert isinstance(options, ClaudeCodeOptions)
        if resolve_binary(options.binary) is None:
            raise RuntimeError(
                f"Claude Code binary {options.binary!r} not found; set --harness-opt "
                "binary=/path/to/claude",
            )
        return ClaudeCodeHarness(options)

    def smoke(self, ctx: HarnessContext, options: BaseModel) -> BaseHarness:
        """No Claude Code needed: a scripted agent plays the MCP round trip."""
        assert isinstance(options, ClaudeCodeOptions)
        return ScriptedMcpHarness(options, name=self.name)

    def describe(self) -> dict[str, str]:
        return {"harness": self.name, "claude-code": binary_version("claude")}


PLUGIN = ClaudeCodePlugin()
