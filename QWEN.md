# QWEN.md — Intent Engine

## Project Overview

**Intent Engine** is a research project exploring local AI agents running under real hardware constraints — no cloud, no high-end GPU. It investigates the minimum description (seed) needed for a local language model (e.g., Qwen2.5-Coder-7B) to reliably reconstruct a complete software artifact.

The core philosophy: *store the intention, not the content.* Rather than saving generated source code, the system saves a tiny seed (prompt + model identifier + functional hash, ~300 bytes) that can regenerate the full artifact on demand via a local LLM.

### Architecture

The system uses a multi-agent pipeline:

1. **Architect** — Converts a user's natural-language prompt into a structured `.md` spec (file list with roles, features, constraints)
2. **Coder** — Generates each file sequentially, respecting its declared role
3. **Critic** — Reviews the full project snapshot, listing only blocking issues (returns `ALL_COMPLETE` when done)
4. **Planner** — Converts Critic feedback into a minimal fix plan (≤3 files per cycle)

The loop runs: Coder → Critic → Planner → Coder (repeat) until completion or max cycles.

### Key Technical Concepts

- **Functional Hashing**: Hashes *execution output* instead of source code, enabling cross-machine stability despite GPU vs CPU float16 arithmetic differences
- **Seed Storage**: Optional persistence of seeds in Cloudflare DNS TXT records (via `seed.py`), treating DNS as a key-value store
- **Local LLM**: Uses llama.cpp server (or LM Studio / Ollama) via an OpenAI-compatible API

## Building and Running

### Prerequisites

```bash
pip install openai requests
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
  "snapshot_limit": 2000,
  "temperature": 0.1
}
```

### Running

```bash
# Full pipeline: Architect → Coder → Critic → Planner loop
python main.py "create a playable Tetris clone in the browser"

# With custom output and cycle limit
python main.py "create a Tetris clone" --max_cycles 12 --output ./output/tetris
```

### Seed Storage (optional)

```bash
# Store a seed in DNS
python seed.py store --key tetris-v1 --session output/tetris/session.json

# Retrieve a seed
python seed.py get --key tetris-v1

# Reconstruct from seed
python seed.py reconstruct --key tetris-v1 --output output/tetris-reconstructed
```

## Project Structure

```
C:\local-intent\
├── main.py                  # CLI entry point
├── seed.py                  # DNS seed storage CLI (mnemo integration)
├── config.example.json      # Config template (config.json is gitignored)
├── requirements.txt         # Python dependencies: openai, requests
│
├── agent/                   # Agent logic
│   ├── architect.py         # Prompt → structured spec.md
│   ├── coder.py             # Generates one file per response
│   ├── critic.py            # Lists blocking issues only
│   ├── planner.py           # Minimal fix plan (≤3 actions/cycle)
│   ├── loop.py              # Orchestrates create + repair phases
│   └── prompts.py           # All system prompts (highest-leverage tuning file)
│
├── core/                    # Infrastructure
│   ├── config.py            # Load config.json with defaults
│   ├── llm.py               # OpenAI-compatible LLM client (streaming)
│   ├── session.py           # Session dataclass: all run state
│   └── hasher.py            # Functional hashing (hash execution output)
│
├── storage/
│   └── dns_layer.py         # Cloudflare DNS TXT storage backend
│
├── output/                  # Generated artifacts (gitignored)
├── results/                 # Experiment results (populated as research progresses)
└── local-intent-coder/      # (submodule or external reference)
```

## Development Conventions

- **Python 3.11+**
- **No external dependencies** beyond `openai` and `requests`
- **Type hints** on all public functions
- **Docstrings** on every class and public method
- **No print statements in `core/`** — use the `label` parameter of `LLMClient.call()` for section headers
- System prompts live in `agent/prompts.py` — this is the primary tuning surface
- For experiments across prompt versions, version them (e.g., `ARCHITECT_V1`, `ARCHITECT_V2`) and add a `--prompt_version` flag

## Research Phases

| Phase | Question | Status |
|---|---|---|
| 1 — Agent loop baseline | Can Qwen2.5-Coder-7B generate a working multi-file JS project autonomously? | ✅ Complete |
| **1.5 — Execution validation** | Can we catch runtime bugs the Critic can't see (logic errors, broken event handlers)? | **🔶 In progress** |
| 2 — Architect quality | Does role-annotated specs reduce Critic cycles vs flat specs? | Not started |
| 3 — Seed compression ratio | How much does the seed compress the artifact? | Not started |
| 4 — Functional hash stability | Is the functional hash stable across runs at temperature=0? | Not started |
| 5 — Cross-machine seed portability | Can a seed generated on one machine be reconstructed on another? | Not started |
| 6 — Generalisation | Does the pipeline work for non-Tetris targets? | Not started |

## Key Findings

1. **Temperature=0 is deterministic on the same machine** — 8/8 perfect SHA matches across 5 runs
2. **Cross-machine determinism breaks completely** — CPU vs GPU produces 0/5 matching hashes (float16 arithmetic divergence)
3. **CPU-only inference is the more stable environment for seeds** — sequential float operations are fully deterministic
4. **A minimal custom agent outperforms a general tool harness for small models** — ~80-line custom agent with simple `<tool>` format is more reliable than Hermes Agent with tool-call format mismatch
5. **File role assignment is load-bearing for multi-file coherence** — explicit responsibility descriptions reduce cross-file variable collision
6. **The Python `openai` library hangs with llama-server on Windows** — replaced with raw HTTP via `http.client` (2026-04-10)
7. **The Critic cannot catch runtime logic bugs** — it only reads code, can't execute it. Catches "no localStorage" but misses "saveTasks() never called". Requires execution-based validation (Phase 1.5).
