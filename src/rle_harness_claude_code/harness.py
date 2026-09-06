"""Claude Code driven one headless invocation per tick.

Surface used (https://code.claude.com/docs/en/cli-reference):

* ``claude -p "<prompt>" --output-format json --permission-mode bypassPermissions
  --mcp-config <file> --strict-mcp-config --bare --tools ""
  [--model MODEL] [--resume <session_id>] [--max-turns N]
  [--disallowed-tools ...]``
  -> one JSON object: ``type=result``, ``result``, ``session_id``,
  ``usage{input_tokens, output_tokens, cache_*}``, ``total_cost_usd``
* MCP config is a temp JSON file declaring only the RLE streamable-HTTP server::

      {"mcpServers": {"rle": {"type": "http", "url": "http://127.0.0.1:PORT/mcp"}}}

  Claude Code names MCP tools ``mcp__<server>__<tool>``
  (``mcp__rle__get_brief``, ``mcp__rle__end_turn``).
* Auth is ``ANTHROPIC_API_KEY`` or a prior ``claude auth login``. This
  package never writes credentials.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, ClassVar

from rle.harness import HarnessStepError
from rle.harness.brief import ScenarioBrief
from rle.harness.cli_base import HeadlessCliHarness, TurnResult

from rle_harness_claude_code.options import ClaudeCodeOptions

logger = logging.getLogger(__name__)

MCP_SERVER_NAME = "rle"
DEFAULT_ADVERTISED_MCP_URL = "http://host.docker.internal:8766/mcp"

TOOL_NAMING_NOTE = (
    "In this environment the RLE tools are MCP tools on the `rle` server: call "
    "mcp__rle__get_brief, mcp__rle__work_priority, mcp__rle__blueprint, ..., and "
    "finish with mcp__rle__end_turn. Some clients also expose them unprefixed "
    "(get_brief / end_turn). The only MCP server available is rle --- do not "
    "search for other tools."
)


def resolve_binary(binary: str) -> str | None:
    """Resolve a Claude Code executable (PATH name, absolute path, or ``.exe``)."""
    candidate = Path(binary).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    found = shutil.which(binary)
    if found is not None:
        return found
    if not binary.lower().endswith(".exe"):
        return shutil.which(f"{binary}.exe")
    return None


def effective_mcp_url(bind_url: str, advertise_url: str | None) -> str:
    """URL written into the MCP config: advertised (Docker) wins over bind URL."""
    if advertise_url and advertise_url.strip():
        return advertise_url.strip()
    return bind_url


def mcp_config_json(mcp_url: str) -> dict[str, Any]:
    """RLE-only Claude Code MCP config (HTTP / streamable-HTTP)."""
    return {
        "mcpServers": {
            MCP_SERVER_NAME: {
                "type": "http",
                "url": mcp_url,
            },
        },
    }


def build_command(
    binary: str,
    prompt: str,
    opts: ClaudeCodeOptions,
    *,
    model: str | None,
    mcp_config: str,
    session_id: str | None,
) -> list[str]:
    cmd = [
        binary,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--permission-mode",
        opts.permission_mode,
        "--mcp-config",
        mcp_config,
    ]
    if opts.strict_mcp_config:
        cmd.append("--strict-mcp-config")
    if opts.bare:
        cmd.append("--bare")
    if opts.tools is not None:
        cmd += ["--tools", opts.tools]
    if model:
        cmd += ["--model", model]
    if session_id and opts.resume_session:
        cmd += ["--resume", session_id]
    if opts.max_turns:
        cmd += ["--max-turns", str(opts.max_turns)]
    for tool in opts.disallowed_tools:
        cmd += ["--disallowed-tools", tool]
    cmd += list(opts.extra_args)
    return cmd


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def parse_json_output(stdout: str) -> TurnResult:
    """Turn the headless ``json`` object into a TurnResult (tolerant of noise)."""
    data: Any = None
    text = stdout.strip()
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if data is None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return TurnResult(text=text)
    if not isinstance(data, dict):
        return TurnResult(text=text)
    if data.get("type") == "error" or data.get("is_error"):
        message = data.get("result") or data.get("message") or data
        raise HarnessStepError(f"claude reported an error: {message}")
    usage = data.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    cached = _as_int(usage.get("cache_read_input_tokens")) + _as_int(
        usage.get("cache_creation_input_tokens"),
    )
    session_id = data.get("session_id") or data.get("sessionId") or ""
    result_text = data.get("result")
    if result_text is None:
        result_text = data.get("text", "")
    return TurnResult(
        text=str(result_text),
        prompt_tokens=_as_int(usage.get("input_tokens")) + cached,
        completion_tokens=_as_int(usage.get("output_tokens")),
        reasoning_tokens=_as_int(usage.get("reasoning_tokens")),
        extras={
            "session_id": str(session_id),
            "stop_reason": data.get("stop_reason") or data.get("subtype"),
            "num_turns": data.get("num_turns"),
            "cost_usd": data.get("total_cost_usd"),
            "duration_ms": data.get("duration_ms"),
        },
    )


class ClaudeCodeHarness(HeadlessCliHarness):
    name: ClassVar[str] = "claude-code"

    def __init__(self, options: ClaudeCodeOptions) -> None:
        super().__init__(options)
        self.opts = options
        self._binary: str | None = None
        self._workdir: str | None = None
        self._mcp_config: str | None = None
        self._session_id: str | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._mcp_url: str | None = None

    async def start_agent(self, mcp_url: str) -> None:
        binary = resolve_binary(self.opts.binary)
        if binary is None:
            raise HarnessStepError(f"Claude Code binary {self.opts.binary!r} not found on PATH")
        self._binary = binary
        self._workdir = tempfile.mkdtemp(prefix="rle-claude-code-")
        cfg_url = effective_mcp_url(mcp_url, self.opts.mcp_advertise_url)
        self._mcp_url = cfg_url
        config_path = Path(self._workdir) / "mcp.json"
        config_path.write_text(
            json.dumps(mcp_config_json(cfg_url), indent=2) + "\n",
            encoding="utf-8",
        )
        self._mcp_config = str(config_path)
        logger.info("Claude Code workdir=%s with RLE-only MCP at %s", self._workdir, cfg_url)
        if not os.environ.get(self.opts.api_key_env):
            logger.info(
                "%s not set --- relying on Claude Code's cached login for headless auth",
                self.opts.api_key_env,
            )

    def render_prompt(self, brief: ScenarioBrief) -> str:
        return super().render_prompt(brief) + "\n\n" + TOOL_NAMING_NOTE

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self._mcp_url is not None:
            env["MCP_URL"] = self._mcp_url
        return env

    async def send_turn(self, prompt: str) -> TurnResult:
        assert self._binary is not None and self._workdir is not None
        assert self._mcp_config is not None
        cmd = build_command(
            self._binary,
            prompt,
            self.opts,
            model=self.opts.model or self.ctx.config.model,
            mcp_config=self._mcp_config,
            session_id=self._session_id,
        )
        logger.debug(
            "claude invocation: %s",
            " ".join(cmd[:1] + ["-p", "<prompt>"] + cmd[3:]),
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self._workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._subprocess_env(),
        )
        self._proc = proc
        try:
            stdout_b, stderr_b = await proc.communicate()
        except asyncio.CancelledError:
            await self._terminate_process(proc)
            raise
        finally:
            if self._proc is proc:
                self._proc = None
        returncode = proc.returncode or 0
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        if stderr.strip():
            logger.debug("claude stderr (tail): %s", stderr.strip()[-1500:])
        if returncode != 0:
            raise HarnessStepError(
                f"claude exited {returncode}: {(stderr or stdout).strip()[-800:]}",
            )
        turn = parse_json_output(stdout)
        sid = turn.extras.get("session_id")
        if sid:
            self._session_id = str(sid)
        return turn

    async def _terminate_process(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass

    async def abort_turn(self) -> None:
        proc = self._proc
        if proc is not None:
            await self._terminate_process(proc)
        if self._proc is proc:
            self._proc = None

    async def stop_agent(self) -> None:
        await self.abort_turn()
        if self._workdir is not None:
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None
        self._mcp_config = None
        self._mcp_url = None

    def agent_versions(self) -> dict[str, str]:
        return {"claude-code": binary_version(self.opts.binary)}


def binary_version(binary: str) -> str:
    path = resolve_binary(binary)
    if path is None:
        return "not installed"
    try:
        out = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    text = (out.stdout or out.stderr).strip()
    return text.splitlines()[0] if text else "unknown"
