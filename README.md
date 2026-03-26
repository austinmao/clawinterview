# ClawInterview

Pipeline interview compilation, validation, and execution for OpenClaw.

ClawInterview compiles typed interview contracts from participating agents and skills, resolves inputs from available data sources in mandatory precedence order, and runs brainstorming-style interactive intake when human questioning is required. It produces a layered execution brief consumed by downstream pipeline stages.

Part of [ClawSuite](https://github.com/austinmao/clawsuite).

## Install

```bash
pip install clawinterview
```

For development:

```bash
git clone https://github.com/austinmao/clawinterview.git
cd clawinterview
pip install -e ".[dev]"
```

## CLI Usage

```bash
# Compile contracts for a pipeline
clawinterview compile path/to/pipeline.yaml

# Validate a contract
clawinterview validate path/to/contract.yaml

# Run interview (interactive)
clawinterview run path/to/pipeline.yaml

# Run with bypass (resolvers only, no questions)
clawinterview run path/to/pipeline.yaml --bypass
```

## Interview Contract Example

```yaml
contracts:
  interview:
    version: "1.0"
    required_inputs:
      - id: campaign_topic
        type: string
        description: Core campaign topic
        facets: [topic, positioning]
        resolution_strategies: [user_args, user_message, tenant_file, ask]
        confidence_threshold: 0.8
    optional_inputs: []
    produces_outputs:
      - id: discovery_brief
        type: object
        facets: [brief]
    completion_rules:
      all_of:
        - require: campaign_topic
```

## Gateway Plugin

ClawInterview includes an OpenClaw gateway plugin so agents can invoke it during reasoning sessions.

### Installation

1. Copy the plugin directory to your OpenClaw extensions:

```bash
cp -r extensions/clawinterview ~/.openclaw/extensions/clawinterview/
```

2. Add to `plugins.allow` in `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "allow": ["clawinterview"]
  }
}
```

3. Restart the gateway. You should see:

```
[clawinterview] tool registered
```

## Architecture

- **compiler.py** -- Compiles pipeline-scoped run contracts from target interview contracts
- **resolver.py** -- Pluggable resolver registry with mandatory precedence order
- **resolvers/** -- 10 built-in resolvers (user_args, memory, tenant_file, rag, web, ask, etc.)
- **planner.py** -- Question planning with layer-by-layer assembly and light/deep modes
- **brief.py** -- Layered brief assembler (context -> strategy -> constraints -> execution brief)
- **engine.py** -- Main engine orchestrating compile -> resolve -> plan -> turn loop
- **conflict.py** -- Semantic conflict detection with bounded self-repair
- **overlay.py** -- Department packs and tenant overlay merging
- **state.py** -- YAML state persistence for resume support
- **schema.py** -- JSON Schema + semantic validation for interview contracts
- **packs/** -- 8 department default packs (marketing, sales, operations, etc.)

## Test

```bash
pytest --cov=src --cov-report=term-missing
```

## ClawSuite

| Package | Description | Repo |
|---|---|---|
| **ClawPipe** | Config-driven pipeline orchestration engine | [austinmao/clawpipe](https://github.com/austinmao/clawpipe) |
| **ClawSpec** | Contract-first testing for skills & agents | [austinmao/clawspec](https://github.com/austinmao/clawspec) |
| **ClawWrap** | Outbound policy & conformance engine | [austinmao/clawwrap](https://github.com/austinmao/clawwrap) |
| **ClawAgentSkill** | Skill discovery, scanning & adoption | [austinmao/clawagentskill](https://github.com/austinmao/clawagentskill) |
| **ClawScaffold** | Agent/skill scaffold interviews | [austinmao/clawscaffold](https://github.com/austinmao/clawscaffold) |
| **ClawInterview** | Pipeline interview compilation & execution | [austinmao/clawinterview](https://github.com/austinmao/clawinterview) |

## Requirements

- Python 3.11+
- OpenClaw v2026.3.24+ (for gateway plugin)

## License

MIT
