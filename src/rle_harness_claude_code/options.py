"""Options for the Claude Code harness (``--harness-opt key=value``)."""

from __future__ import annotations

from pydantic import Field
from rle.harness.cli_base import HeadlessCliOptions

# Built-ins that would let the agent act outside RLE (shell, files, web).
DEFAULT_DISALLOWED_TOOLS: tuple[str, ...] = (
    "Bash",
    "Edit",
    "Write",
    "Read",
    "Glob",
    "Grep",
    "WebSearch",
    "WebFetch",
    "Agent",
    "Task",
    "NotebookEdit",
    "Skill",
)


class ClaudeCodeOptions(HeadlessCliOptions):
    binary: str = Field(default="claude", description="Claude Code executable (name or path).")
    resume_session: bool = Field(
        default=True,
        description="Resume the same headless session every tick (context carries over).",
    )
    max_turns: int | None = Field(
        default=20,
        ge=1,
        description=(
            "Cap on agentic rounds per tick (--max-turns). Default 20 so a lost "
            "tool-search loop cannot burn the full turn timeout with zero RLE actions."
        ),
    )
    tools: str | None = Field(
        default="",
        description=(
            "Claude Code --tools list. Empty string disables every built-in tool "
            "(MCP tools are unaffected). None omits the flag; 'default' keeps stock tools."
        ),
    )
    disallowed_tools: list[str] = Field(
        default_factory=lambda: list(DEFAULT_DISALLOWED_TOOLS),
        description=(
            "Built-in tools denied so the agent can only act through the RLE MCP tools "
            "(--disallowed-tools). Empty list = do not pass the flag."
        ),
    )
    permission_mode: str = Field(
        default="bypassPermissions",
        description=(
            "Claude Code --permission-mode so MCP tool calls never wait for approval "
            "(headless equivalent of --dangerously-skip-permissions)."
        ),
    )
    strict_mcp_config: bool = Field(
        default=True,
        description="Pass --strict-mcp-config so only the RLE --mcp-config file is loaded.",
    )
    bare: bool = Field(
        default=True,
        description=(
            "Pass --bare so user CLAUDE.md, hooks, plugins, and auto-discovered MCP "
            "servers do not leak into the benchmark turn."
        ),
    )
    api_key_env: str = Field(
        default="ANTHROPIC_API_KEY",
        description="Env var holding the Anthropic API key (or use `claude auth login`).",
    )
    extra_args: list[str] = Field(
        default_factory=list,
        description="Additional raw flags appended to every invocation.",
    )
