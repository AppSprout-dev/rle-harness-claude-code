"""Contract + invocation-shaping tests (no Claude Code binary required)."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from rle.config import RLEConfig
from rle.harness import (
    HarnessContext,
    HarnessOptionsError,
    HarnessStepError,
    get_plugin,
    harness_names,
)
from rle.rimapi.client import RimAPIClient
from rle.testing import MockRimAPI, run_harness_smoke

from rle_harness_claude_code.harness import (
    DEFAULT_ADVERTISED_MCP_URL,
    ClaudeCodeHarness,
    binary_version,
    build_command,
    mcp_config_json,
    parse_json_output,
    resolve_binary,
)
from rle_harness_claude_code.options import DEFAULT_DISALLOWED_TOOLS, ClaudeCodeOptions

NAME = "claude-code"


class TestRegistration:
    def test_entry_point(self) -> None:
        assert NAME in harness_names()
        assert get_plugin(NAME).option_schema() is ClaudeCodeOptions

    async def test_smoke_round_trip(self) -> None:
        report = await run_harness_smoke(NAME, ticks=2)
        assert report.ok and report.harness == NAME
        assert all(t.execution.executed == 1 for t in report.ticks)

    async def test_options_validated(self) -> None:
        with pytest.raises(HarnessOptionsError):
            await run_harness_smoke(NAME, ticks=1, options={"max_turns": 0})


class TestInvocationShaping:
    def test_mcp_config(self) -> None:
        cfg = mcp_config_json("http://127.0.0.1:7000/mcp")
        assert cfg == {
            "mcpServers": {
                "rle": {"type": "http", "url": "http://127.0.0.1:7000/mcp"},
            },
        }

    def test_build_command_first_tick(self) -> None:
        cmd = build_command(
            "/bin/claude",
            "do it",
            ClaudeCodeOptions(max_turns=6),
            model="sonnet",
            mcp_config="/tmp/mcp.json",
            session_id=None,
        )
        assert cmd[:3] == ["/bin/claude", "-p", "do it"]
        assert "--output-format" in cmd and cmd[cmd.index("--output-format") + 1] == "json"
        assert cmd[cmd.index("--permission-mode") + 1] == "bypassPermissions"
        assert cmd[cmd.index("--mcp-config") + 1] == "/tmp/mcp.json"
        assert "--strict-mcp-config" in cmd
        assert "--bare" in cmd
        assert cmd[cmd.index("--tools") + 1] == ""
        assert cmd[cmd.index("--model") + 1] == "sonnet"
        assert "--resume" not in cmd
        assert cmd[cmd.index("--max-turns") + 1] == "6"
        assert cmd.count("--disallowed-tools") == len(DEFAULT_DISALLOWED_TOOLS)
        assert "Bash" in cmd

    def test_build_command_resumes(self) -> None:
        cmd = build_command(
            "claude",
            "again",
            ClaudeCodeOptions(),
            model=None,
            mcp_config="/tmp/mcp.json",
            session_id="abc-123",
        )
        assert cmd[cmd.index("--resume") + 1] == "abc-123"
        assert "--model" not in cmd
        cmd = build_command(
            "claude",
            "again",
            ClaudeCodeOptions(resume_session=False),
            model=None,
            mcp_config="/tmp/mcp.json",
            session_id="abc-123",
        )
        assert "--resume" not in cmd

    def test_build_command_can_keep_stock_tools(self) -> None:
        cmd = build_command(
            "claude",
            "x",
            ClaudeCodeOptions(tools=None, disallowed_tools=[]),
            model=None,
            mcp_config="/tmp/mcp.json",
            session_id=None,
        )
        assert "--tools" not in cmd
        assert "--disallowed-tools" not in cmd

    def test_parse_json_output(self) -> None:
        payload = {
            "type": "result",
            "subtype": "success",
            "result": "Placed walls.",
            "session_id": "s-1",
            "num_turns": 4,
            "is_error": False,
            "usage": {
                "input_tokens": 700,
                "cache_read_input_tokens": 4000,
                "cache_creation_input_tokens": 0,
                "output_tokens": 180,
            },
            "total_cost_usd": 0.0127,
            "duration_ms": 4200,
        }
        turn = parse_json_output("some log line\n" + json.dumps(payload))
        assert turn.text == "Placed walls."
        assert (turn.prompt_tokens, turn.completion_tokens) == (4700, 180)
        assert turn.extras["session_id"] == "s-1"
        assert turn.extras["cost_usd"] == 0.0127
        assert turn.extras["num_turns"] == 4

    def test_parse_error_object(self) -> None:
        with pytest.raises(HarnessStepError, match="auth failed"):
            parse_json_output('{"type":"result","is_error":true,"result":"auth failed"}')

    def test_parse_non_json(self) -> None:
        assert parse_json_output("plain text").text == "plain text"


def _fake_claude(tmp_path: Path) -> Path:
    """A stand-in `claude` that records argv and emits a headless json object."""
    script = tmp_path / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys, os\n"
        f"open({str(tmp_path / 'argv.json')!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "assert os.path.exists(os.path.join(os.getcwd(), 'mcp.json'))\n"
        "print(json.dumps({\n"
        "    'type': 'result', 'subtype': 'success', 'result': 'ok',\n"
        "    'session_id': 'sess-9', 'is_error': False,\n"
        "    'usage': {'input_tokens': 5, 'output_tokens': 1},\n"
        "}))\n",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _prompt_argvs(tmp_path: Path) -> list[list[str]]:
    lines = (tmp_path / "argv.json").read_text().splitlines()
    return [json.loads(line) for line in lines]


class TestAgainstFakeBinary:
    async def test_two_turns_resume_session(self, tmp_path: Path) -> None:
        fake = _fake_claude(tmp_path)
        harness = ClaudeCodeHarness(ClaudeCodeOptions(binary=str(fake), model="sonnet"))
        mock = MockRimAPI()
        async with RimAPIClient("http://mock") as client:
            mock.attach(client)
            ctx = HarnessContext(config=RLEConfig(tick_interval=0.0), client=client)
            harness._ctx = ctx
            await harness.start_agent("http://127.0.0.1:1/mcp")
            try:
                turn1 = await harness.send_turn("turn one")
                turn2 = await harness.send_turn("turn two")
            finally:
                await harness.stop_agent()
        assert turn1.text == "ok" and turn1.prompt_tokens == 5
        assert turn2.extras["session_id"] == "sess-9"
        argvs = _prompt_argvs(tmp_path)
        assert len(argvs) == 2
        assert "--resume" not in argvs[0]
        assert argvs[1][argvs[1].index("--resume") + 1] == "sess-9"
        assert argvs[0][argvs[0].index("--model") + 1] == "sonnet"
        assert argvs[0][argvs[0].index("--mcp-config") + 1].endswith("mcp.json")

    async def test_advertise_url_written_to_mcp_config(self, tmp_path: Path) -> None:
        fake = _fake_claude(tmp_path)
        harness = ClaudeCodeHarness(
            ClaudeCodeOptions(
                binary=str(fake),
                mcp_advertise_url=DEFAULT_ADVERTISED_MCP_URL,
            ),
        )
        mock = MockRimAPI()
        async with RimAPIClient("http://mock") as client:
            mock.attach(client)
            harness._ctx = HarnessContext(config=RLEConfig(tick_interval=0.0), client=client)
            await harness.start_agent("http://127.0.0.1:54321/mcp")
            try:
                assert harness._mcp_config is not None
                cfg = json.loads(Path(harness._mcp_config).read_text(encoding="utf-8"))
                assert cfg["mcpServers"]["rle"]["url"] == DEFAULT_ADVERTISED_MCP_URL
                assert "127.0.0.1:54321" not in json.dumps(cfg)
                env = harness._subprocess_env()
                assert env["MCP_URL"] == DEFAULT_ADVERTISED_MCP_URL
            finally:
                await harness.stop_agent()

    async def test_nonzero_exit_is_a_step_error(self, tmp_path: Path) -> None:
        fake = tmp_path / "claude"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "print('auth failed', file=sys.stderr)\n"
            "raise SystemExit(1)\n",
        )
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        harness = ClaudeCodeHarness(ClaudeCodeOptions(binary=str(fake)))
        mock = MockRimAPI()
        async with RimAPIClient("http://mock") as client:
            mock.attach(client)
            harness._ctx = HarnessContext(config=RLEConfig(tick_interval=0.0), client=client)
            await harness.start_agent("http://127.0.0.1:1/mcp")
            try:
                with pytest.raises(HarnessStepError, match="auth failed"):
                    await harness.send_turn("x")
            finally:
                await harness.stop_agent()

    def test_resolve_binary_and_version(self, tmp_path: Path) -> None:
        fake = _fake_claude(tmp_path)
        assert resolve_binary(str(fake)) == str(fake.resolve())
        assert resolve_binary("definitely-not-a-claude-binary-xyz") is None
        assert binary_version("definitely-not-a-claude-binary-xyz") == "not installed"
