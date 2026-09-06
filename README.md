# rle-harness-claude-code

[Claude Code](https://code.claude.com) as an [RLE](https://github.com/AppSprout-dev/RLE) harness.

RLE benchmarks **harnesses × models** on a live RimWorld colony. This package lets
Anthropic's Claude Code coding agent be the harness: each tick is one headless
invocation (`claude -p … --output-format json`) that resumes the previous session,
acts on the colony through the RLE MCP tools (`mcp__rle__get_brief`,
`mcp__rle__work_priority`, … `mcp__rle__end_turn`), and the writes that reached
the game are scored with the same composite as every other harness.

## Install

```bash
# Claude Code itself (https://code.claude.com)
curl -fsSL https://claude.ai/install.sh | bash
export ANTHROPIC_API_KEY=sk-ant-...   # or `claude auth login` / `claude auth login --console`

# RLE core (not on PyPI yet) + this harness
uv pip install "rimworld-learning-environment[mcp] @ git+https://github.com/AppSprout-dev/RLE"
uv pip install git+https://github.com/AppSprout-dev/rle-harness-claude-code
```

Auth is environment / Claude Code login only. Do not bake API keys into configs,
images, or `--harness-opt` values.

## Run

From an RLE checkout with RimWorld + RIMAPI running:

```bash
python scripts/run_benchmark.py --harness list
python scripts/run_scenario.py crashlanded --harness claude-code --model sonnet --ticks 10 --tick-interval 30
python scripts/run_benchmark.py --harness claude-code --harness felix --model sonnet --runs 4
```

`--model` is a Claude Code alias (`sonnet`, `opus`, `haiku`, `fable`) or a full
model id. Credentials are `ANTHROPIC_API_KEY` or whatever `claude auth login`
already stored.

### Fair compare (Crashlanded, seed 42, scoring 1.2)

Same scenario / seed / scoring version as the other coding-agent harnesses.
Pass `turn_timeout_s=300` so a slower agent is not cut off earlier than Grok
Build / OpenCode compares:

```bash
python scripts/run_scenario.py crashlanded --harness claude-code --model sonnet \
  --seed 42 --ticks 10 --tick-interval 30 \
  --harness-opt turn_timeout_s=300
```

RLE's current composite is scoring **1.2**. Do not compare these rows to the
published scoring 1.1 Felix spread.

Options (`--harness-opt key=value`):

| Option | Default | Meaning |
|---|---|---|
| `binary` | `claude` | Executable name/path |
| `resume_session` | true | `--resume <session_id>` every tick so context carries over |
| `max_turns` | 20 | `--max-turns` cap on agentic rounds per tick |
| `tools` | `""` | `--tools` list; empty disables built-ins (MCP tools stay) |
| `disallowed_tools` | Bash/Edit/Write/… | Extra `--disallowed-tools` so the agent can only act via RLE |
| `permission_mode` | `bypassPermissions` | Skip interactive approval of MCP tool calls |
| `turn_timeout_s` | 180 | Kill the invocation after this many seconds (use 300 for compares) |
| `extra_instructions` | – | Appended to every turn prompt |
| `extra_args` | – | Raw flags appended to every invocation |
| `mcp_advertise_url` | – | URL written into the MCP config (Docker: `http://host.docker.internal:8766/mcp`) |
| `mcp_container_reachable` | – | Bind MCP on `0.0.0.0:8766` and advertise `host.docker.internal` |

## Docker / container reachability

If Claude Code runs in a container and RimWorld + RIMAPI stay on the **host**,
RLE's in-process MCP bind (`127.0.0.1` + ephemeral port) is unreachable. Pass:

```bash
python scripts/run_scenario.py crashlanded --harness claude-code --model sonnet --seed 42 \
  --harness-opt turn_timeout_s=300 \
  --harness-opt mcp_container_reachable=true \
  --harness-opt mcp_advertise_url=http://host.docker.internal:8766/mcp
```

Forward `ANTHROPIC_API_KEY` into the container. Never mount host `~/.claude`
or bake secrets into an image.

## Windows

Prefer the **native** Claude Code installer (`claude.exe` on PATH). The npm
`claude.cmd` shim is re-parsed by `cmd.exe`, which can drop a large `-p`
prompt (the same class of bug as `grok-docker.cmd`). If `claude` resolves to a
`.cmd` file, point `binary` at `claude.exe` instead:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python scripts/run_scenario.py crashlanded --harness claude-code --model sonnet --seed 42 `
  --harness-opt turn_timeout_s=300 `
  --harness-opt binary=claude.exe
```

## How it works

- A temp working directory with `mcp.json` declaring the RLE MCP server
  (hosted in-process by RLE over streamable HTTP) as the only server.
- Per tick: `claude -p <prompt> --output-format json --permission-mode bypassPermissions
  --mcp-config mcp.json --strict-mcp-config --bare --tools "" [--model …] [--resume sid] …`;
  `session_id`, `usage` and `total_cost_usd` from the JSON object feed RLE's tracking.
- `--smoke-test` needs no Claude Code: a scripted agent plays the same MCP round trip.

## Development

```bash
uv pip install "rimworld-learning-environment[mcp] @ git+https://github.com/AppSprout-dev/RLE"
uv pip install -e ".[dev]"
pytest && ruff check src tests && mypy src
```

MIT (this package). Claude Code is Anthropic's product.
