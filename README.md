# FailBot - Multi-Agent CI Failure Triage & Test Generation

A LangGraph-based multi-agent system that automatically triages CI failures, generates regression tests, and files GitHub issues.

## Features

- **Multi-Agent Pipeline**: LogParserAgent → TriageAgent → TestSuggesterAgent → IssueFilingAgent
- **Tool Binding (LangGraph-native)**: Tools are bound to LLMs with `@tool` + ToolNode execution
- **MCP GitHub Support**: Optional MCP server → REST API → Local file fallback
- **Structured Logging**: JSON-line logging with token tracking and latency metrics
- **Production-Ready**: Error recovery, retry logic, comprehensive documentation

## Quick Start

### 1. Clone & Setup

```bash
# Clone the repository
git clone https://github.com/your-org/failbot.git
cd failbot

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

### 2. Configure

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your API keys
export OPENAI_API_KEY=sk-...
export GITHUB_TOKEN=ghp_...

# Optional MCP GitHub integration
export FAILBOT_USE_MCP=true
export MCP_GITHUB_SERVER_CMD="npx -y @modelcontextprotocol/server-github"
export MCP_GITHUB_TOOL_CREATE_ISSUE=create_issue
```

### 3. Run

```bash
# Run FailBot on a CI log file
python -m src.main --log-source /path/to/log.txt --repo owner/repo

# Or fetch from a GitHub Actions run
python -m src.main --log-source https://github.com/.../logs/1234 --repo owner/repo
```

## Architecture

```
Input Log
    ↓
[Ingest] → Fetch & Truncate (8000 tokens max)
    ↓
[Parse Log Agent] → Extract error signature, files, language
    ↓
[Triage Agent] → Classify: code_bug | flaky | infra | unknown
    ↓
         ├→ "code_bug" ──→ [Suggest Test] → Generate regression test
         ├→ "flaky"    ──→ [Suggest Test Generic] → Tool-aware strategy
         └→ "unknown"  ──→ [File Issue] → Tool-bound issue filing
                              ↓
[File Issue] → MCP GitHub Server → REST API → Local Fallback
    ↓
[Report] → Print summary, save results
```

## Project Structure

```
failbot/
├── src/
│   ├── nodes/          # Agent node implementations
│   ├── tools/          # Knowledge base, validators, API clients
│   ├── utils/          # Token counter, retry logic, logging, tool runner
│   ├── callbacks/      # LangGraph event handlers
│   ├── graph.py        # StateGraph builder
│   ├── state.py        # FailBotState TypedDict
│   ├── config.py       # Configuration loader
│   └── main.py         # CLI entry point
├── config/
│   └── prompts.yaml    # All system prompts & settings
├── evals/
│   ├── test_logs/      # Sample CI log files
│   ├── ground_truth.json
│   ├── eval.py          # Evaluation harness
│   └── results/        # Analysis outputs
├── tests/              # Unit & integration tests (expand as needed)
├── docs/               # Architecture & guides (in progress)
└── README.md
```

## Configuration

Edit `config/prompts.yaml` to customize:

- **Models**: Which LLM models to use (gpt-4o-mini, claude, etc.)
- **Token Limits**: Context window per agent
- **System Prompts**: Agent instructions (few-shot examples, style)
- **Retry Strategy**: Backoff parameters for resilience

## Metrics & Analysis

FailBot captures structured events in `runs/failbot_*.jsonl`. Use the metrics CLI:

```bash
python -m src.metrics analyze
python -m src.metrics list
python -m src.metrics compare --logs runs/failbot_*.jsonl
```

## Evaluation Harness

Run evals with the bundled sample logs:

```bash
python -m evals.eval --repo owner/repo
```

Inputs live in `evals/test_logs/` and expected outputs in `evals/ground_truth.json`.
Results are written to `evals/results/` (CSV, JSON summary, and HTML report).

## Documentation

- [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) — Code practice consistency details
- [TOOL_BINDING_REFACTORING.md](TOOL_BINDING_REFACTORING.md) — Tool binding architecture
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — System design overview
- [docs/FAILURE_MODES.md](docs/FAILURE_MODES.md) — Failure handling guide
- [docs/EVAL_WORKFLOW.md](docs/EVAL_WORKFLOW.md) — Evaluation workflow
- [docs/API.md](docs/API.md) — CLI and API reference
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Deployment notes

## Development

### Running Tests

```bash
python test_code_consistency.py
python test_tool_binding.py
python test_phase5.py
```

### Code Quality

```bash
black src/  # Format
ruff check src/  # Lint
mypy src/  # Type check
```

### Viewing Logs

FailBot creates structured logs in `runs/failbot_*.jsonl`. View with:

```bash
# Pretty-print latest log
tail -f runs/failbot_*.jsonl | jq .

# Count events by type
grep '"event_type"' runs/failbot_*.jsonl | jq -r '.event_type' | sort | uniq -c
```

## Performance

Typical pipeline execution:

- **Ingest**: 0.1–0.5s (network fetch + truncation)
- **Parse Log**: 2–4s (LLM call)
- **Triage**: 1–3s (LLM call + optional tool)
- **Suggest Test**: 2–4s (LLM call)
- **File Issue**: 1–2s (API call)

**Total**: ~6–14s end-to-end

**Token Usage** (per run): ~1500–3000 tokens (~$0.01–0.05 with gpt-4o-mini)

## Troubleshooting

### LLM API Errors
- Check `OPENAI_API_KEY` is set correctly
- Check rate limits (60/min free, 5000/min paid)
- View logs in `runs/*.jsonl` for detailed error

### GitHub Issue Filing Fails
- Verify `GITHUB_TOKEN` has `repo` and `issues` permissions
- Check repo exists and token has access
- Issue will be saved locally to `runs/*_issue_draft.md`

### MCP GitHub Issues
- Ensure Node.js is installed
- Set `MCP_GITHUB_SERVER_CMD` (default uses `npx -y @modelcontextprotocol/server-github`)
- Toggle MCP via `FAILBOT_USE_MCP=true|false`

### Config Not Loading
- Set `export FAILBOT_CONFIG=/path/to/config/prompts.yaml`
- Or place `config/prompts.yaml` in project root

## Contributing

Contributions welcome! Areas to extend:

- [ ] Support more CI platforms (GitLab, BitBucket, Jenkins)
- [ ] Fine-tuned models for better accuracy
- [ ] Slack/Discord bot integration
- [ ] Web dashboard (Streamlit/FastAPI)
- [ ] Custom evaluation metrics

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License — See [LICENSE](LICENSE)

## Authors

Built with ❤️ for reliable CI/CD systems.

## Citation

If you use FailBot in research, please cite:

```bibtex
@software{failbot2026,
  title={FailBot: Multi-Agent CI Failure Triage and Test Generation},
  author={FailBot Team},
  year={2026},
  url={https://github.com/your-org/failbot}
}
```
