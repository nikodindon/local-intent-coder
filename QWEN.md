# QWEN.md — Intent Engine

## Project Overview

**Intent Engine** is a research project exploring local AI agents running under real hardware constraints — no cloud, no high-end GPU. It investigates the minimum description (seed) needed for a local language model (e.g., Qwen2.5-Coder-7B) to reliably reconstruct a complete software artifact.

The core philosophy: *store the intention, not the content.* Rather than saving generated source code, the system saves a tiny seed (prompt + model identifier + functional hash, ~300 bytes) that can regenerate the full artifact on demand via a local LLM.

### Architecture

The system uses a **5-phase multi-agent pipeline** with **spec-driven generic agents**:

0. **Designer (pre-code)** — Enriches spec with visual guidelines (colors, borders, typography, layout)
1. **Architect** — Converts a user's natural-language prompt into a structured `.md` spec
2. **Coder** — Generates each file sequentially, respecting its declared role
3. **Critic** — Reviews the full project snapshot, listing only blocking issues (returns `ALL_COMPLETE` when done)
4. **Executor** — Runs the artifact in a headless browser, tests actual functionality
5. **Designer (post-render)** — Audits computed styles, scores visual quality, triggers CSS fix loop if needed

The loop runs: Coder → Critic → Executor → Designer → (if needed) Planner → Coder (repeat) until completion.

**v2 Architecture (2026-04-11)**: All agents are now **fully generic** — no hardcoded selectors, no game-specific assumptions. A new `SpecAnalyzer` module extracts artifact metadata (type, controls, win conditions) from the spec, and all agents derive their behavior from this structured data instead of hardcoded templates.

### Key Technical Concepts

- **Functional Hashing**: Hashes *execution output* instead of source code, enabling cross-machine stability despite GPU vs CPU float16 arithmetic differences
- **Seed Storage**: Optional persistence of seeds in Cloudflare DNS TXT records (via `seed.py`), treating DNS as a key-value store
- **Local LLM**: Uses llama.cpp server (or LM Studio / Ollama) via an OpenAI-compatible API
- **Type-Aware Testing**: Executor detects artifact type (board game, to-do app, counter) and generates appropriate tests

## Building and Running

### Prerequisites

```bash
pip install openai requests playwright
playwright install chromium
```

A local LLM server must be running. Example with llama.cpp (CPU-only):

```powershell
llama-server -m C:\models\Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf -ngl 0 -c 32768 -np 1 -t 10 --host 0.0.0.0 --port 8080
```

### Configuration

Copy `config.example.json` to `config.json` and adjust:

```json
{
  "base_url": "http://localhost:8080/v1",
  "api_key": "sk-placeholder",
  "model": "qwen2.5-coder-7b",
  "context_size": 32768,
  "max_out_tokens": 3000,
  "snapshot_limit": 800,
  "temperature": 0.1
}
```

### Running

```bash
# Full 5-phase pipeline: Designer → Architect → Coder → Critic → Executor → Designer
python main.py "create a playable Tic-Tac-Toe game"

# With logging (tail with: Get-Content -Wait <path>)
python main.py "create a Tic-Tac-Toe game" --max_cycles 8 --output output/tictactoe --log output/tictactoe.log
```

### Seed Storage (optional)

```bash
# Store a seed in DNS
python seed.py store --key tictactoe-v1 --session output/tictactoe/session.json

# Retrieve a seed
python seed.py get --key tictactoe-v1

# Reconstruct from seed
python seed.py reconstruct --key tictactoe-v1 --output output/tictactoe-reconstructed
```

## Project Structure

```
C:\local-intent\
├── main.py                  # CLI entry point
├── seed.py                  # DNS seed storage CLI (mnemo integration)
├── validate.py              # Validation script (artifact quality checks)
├── config.example.json      # Config template (config.json is gitignored)
├── requirements.txt         # Python dependencies: openai, requests, playwright
│
├── agent/                   # Agent logic
│   ├── architect.py         # Prompt → structured spec.md
│   ├── coder.py             # Generates one file per response
│   ├── critic.py            # Lists blocking issues only (with repetition detection)
│   ├── planner.py           # Minimal fix plan (≤3 actions/cycle)
│   ├── designer.py          # Visual guidelines + post-render style audit [v2: fully generic]
│   ├── spec_analyzer.py     # Artifact type detection from spec [NEW v2]
│   ├── loop.py              # Orchestrates all 5 phases
│   └── prompts.py           # All system prompts [v2: no hardcoded game assumptions]
│
├── core/                    # Infrastructure
│   ├── config.py            # Load config.json with defaults
│   ├── llm.py               # OpenAI-compatible LLM client (streaming via http.client)
│   ├── session.py           # Session dataclass: all run state + metrics
│   ├── hasher.py            # Functional hashing (hash execution output)
│   └── executor.py          # Playwright browser test runner [NEW]
│
├── storage/
│   └── dns_layer.py         # Cloudflare DNS TXT storage backend
│
├── output/                  # Generated artifacts (gitignored)
├── results/                 # Experiment results
│   ├── phase1-results.md
│   ├── phase1-5-results.md
│   └── dev-summary-2026-04-10.md
└── local-intent-coder/      # (submodule or external reference)
```

## Development Conventions

- **Python 3.11+**
- **Dependencies**: `openai`, `requests`, `playwright`
- **Type hints** on all public functions
- **Docstrings** on every class and public method
- **No print statements in `core/`** — use the `label` parameter of `LLMClient.call()` for section headers
- System prompts live in `agent/prompts.py` — this is the primary tuning surface
- For experiments across prompt versions, version them (e.g., `ARCHITECT_V1`, `ARCHITECT_V2`) and add a `--prompt_version` flag

## Research Phases

| Phase | Question | Status |
|---|---|---|
| 1 — Agent loop baseline | Can Qwen2.5-Coder-7B generate a working multi-file JS project autonomously? | ✅ Complete |
| 1.5 — Execution validation | Can we catch runtime bugs the Critic can't see? | ✅ Complete |
| 1.6 — Visual design audit | Can an automated designer catch ugly CSS the Critic misses? | ✅ Complete |
| 1.7 — Planner file routing | Can the Planner map issues to the correct file? | ✅ Complete |
| 1.8 — Compression measurement | What's the actual seed/artifact ratio? | ✅ Complete (1:47 for Tic-Tac-Toe) |
| **1.9 — Pipeline v2 (generic agents)** | **Can agents work on ANY artifact without hardcoded assumptions?** | 🔶 **In progress** |
| 2 — Architect quality | Does role-annotated specs reduce Critic cycles vs flat specs? | Not started |
| 3 — Seed compression ratio | How much does the seed compress the artifact? | Not started |
| 4 — Functional hash stability | Is the functional hash stable across runs at temperature=0? | Not started |
| 5 — Cross-machine seed portability | Can a seed generated on one machine be reconstructed on another? | Not started |
| 6 — Generalisation | Does the pipeline work for non-Tic-Tac-Toe targets? | 🔶 Started (Blobby Volley) |

## Key Findings

1. **Temperature=0 is deterministic on the same machine** — 8/8 perfect SHA matches across 5 runs
2. **Cross-machine determinism breaks completely** — CPU vs GPU produces 0/5 matching hashes (float16 arithmetic divergence)
3. **CPU-only inference is the more stable environment for seeds** — sequential float operations are fully deterministic
4. **A minimal custom agent outperforms a general tool harness for small models** — ~80-line custom agent with simple `<tool>` format is more reliable than Hermes Agent with tool-call format mismatch
5. **File role assignment is load-bearing for multi-file coherence** — explicit responsibility descriptions reduce cross-file variable collision
6. **The Python `openai` library hangs with llama-server on Windows** — replaced with raw HTTP via `http.client` (2026-04-10)
7. **The Critic cannot catch runtime logic bugs** — it only reads code, can't execute it. Catches "no localStorage" but misses "saveTasks() never called". Requires execution-based validation (Phase 1.5).
8. **Executor MUST detect artifact type** (2026-04-11) — A to-do app test suite fails catastrophically on board games (timeout waiting for `<input>` that doesn't exist). Type detection is essential.
9. **`alert()` dialogs must be intercepted** (2026-04-11) — Playwright blocks alerts by default. Executor must use `page.on("dialog", ...)` to capture win/lose messages.
10. **ALL_COMPLETE ≠ visually acceptable** (2026-04-11) — The Critic validates code correctness but can't see borders, colors, or layout. A post-render Designer audit is essential for visual quality.
11. **Designer pre-code + post-render = enforcement** (2026-04-11) — Pre-code sets visual standards, post-render enforces them. Together they drove Tic-Tac-Toe from 3/10 to 10/10 in one fix cycle.
12. **4-phase pipeline completes in 2 cycles** (2026-04-11) — Tic-Tac-Toe went from bare-bones to polished in ~8 minutes CPU-only.
13. **Win timing bug in generated games** (2026-04-11) — LLM generates `alert()` → `resetBoard()` synchronously, so the player never sees the winning line. Needs `setTimeout` delay or visual highlight.
14. **Planner doesn't map issues to the correct file** (2026-04-11) — Designer flags "no borders" (CSS), Planner says "fix index.html" (HTML). Infinite loop. Requires rule-based file routing or structured issue reports from Designer.
15. **External review: measure compression NOW** (2026-04-11) — Three AI reviews (GPT, Grok, Claude) unanimously agreed: compression ratio is the core research question and has zero measured data. Tic-Tac-Toe v4 has all the data needed.
16. **Agents are hardcoded to Tic-Tac-Toe** (2026-04-11) — Designer post-render searches for `.board`, `.cell`, `#reset` selectors. On Blobby Volley, finds nothing → hallucinates "add board and cells" → infinite repair loop. ALL agents have game-specific assumptions baked in.
17. **Pipeline v2: spec-driven agents** (2026-04-11) — Complete refactoring: `SpecAnalyzer` extracts artifact type from spec, Designer derives audit targets from visual guidelines, all prompts remove hardcoded function names (`resetBoard()`) and game examples. Agents now adapt to ANY artifact type.
