# Contributing to Intent Engine

This document describes the internal architecture in enough detail to add new agents, new storage backends, or new experiment phases without breaking existing ones.

---

## Repository layout

```
intent-engine/
├── main.py                  # CLI entry point
├── config.json              # Local config (gitignored)
├── config.example.json      # Safe template to commit
├── requirements.txt
│
├── core/                    # Infrastructure — no agent logic here
│   ├── config.py            # Load config.json with defaults
│   ├── llm.py               # LLMClient: streaming calls, context bar
│   ├── session.py           # Session dataclass: all run state
│   └── hasher.py            # Source hash + functional hash
│
├── agent/                   # The four agents
│   ├── prompts.py           # All system prompts (tune here)
│   ├── architect.py         # Prompt → spec .md
│   ├── coder.py             # Spec + context → write one file
│   ├── critic.py            # Full snapshot → problem list
│   ├── planner.py           # Problem list → fix plan JSON
│   └── loop.py              # Orchestrates create + repair phases
│
├── storage/                 # Optional persistence backends
│   └── dns_layer.py         # Cloudflare DNS TXT (from mnemo)
│
├── examples/
│   └── tetris/
│       └── spec.md          # Hand-written reference spec
│
└── results/                 # Experiment result files (JSON)
```

---

## Data flow

```
main.py
  │
  ├─► Architect.build_spec(prompt)  →  spec_md  →  session.spec_md
  │         │
  │         └─► Architect.parse_spec(spec_md)
  │                   → session.file_list
  │                   → session.file_roles
  │
  └─► AgentLoop.run()
        │
        ├─► PHASE 1: for each missing file → Coder.write(filename, session)
        │
        └─► PHASE 2: loop until ALL_COMPLETE or max_cycles
              │
              ├─► Critic.review(session)   → critic_output
              ├─► Planner.plan(critic_output, session)  → plan[]
              └─► for each step in plan → Coder.write(filename, session, reason)
```

---

## The Session object

`Session` is the single source of truth for a run. Every agent reads from it and writes back to it. It is serialised to `output/session.json` at the end of every run.

Key fields:

| Field | Set by | Used by |
|---|---|---|
| `prompt` | `main.py` | Architect, Critic |
| `output_dir` | `main.py` | Coder, Session.snapshot() |
| `spec_md` | Architect | loop.py (parse) |
| `file_list` | `parse_spec()` | Coder, Critic, Planner |
| `file_roles` | `parse_spec()` | Coder (context block) |
| `critic_history` | Critic | (research, session.json) |
| `cycles_run` | loop.py | (research, session.json) |
| `completed` | loop.py | main.py |

---

## Adding a new storage backend

1. Create `storage/your_backend.py`
2. Implement `store_seed(key, seed_dict)` and `retrieve_seed(key) -> dict | None`
3. Add an optional `--storage` flag in `main.py` that instantiates your backend and calls `store_seed()` after a successful run

The seed dict format:
```json
{
  "prompt": "...",
  "model": "qwen2.5-coder-7b",
  "artifact_hash": "sha256...",
  "functional_hash": "sha256... or null",
  "cycles_run": 7,
  "file_count": 6
}
```

---

## Tuning prompts

All system prompts are in `agent/prompts.py`. This is the highest-leverage file for improving output quality.

When running experiments across different prompt versions:
1. Keep the old prompt as `ARCHITECT_V1`, `CODER_V1`, etc.
2. Add your new version as `ARCHITECT_V2`
3. Add a `--prompt_version` flag in `main.py` if you want to switch at runtime
4. Record results in `results/` with the version clearly noted

---

## Adding a new experiment phase

1. Document the hypothesis and success criteria in `README.md` under the relevant phase heading
2. Run the experiment, save raw results as `results/phase_N_<description>.json`
3. Fill in the result tables in `README.md`
4. If the experiment required a code change, describe it in a comment at the top of the changed file

---

## Context budget

The agent loop uses a rough token estimate (1 token ≈ 4 characters). The context bar printed before each LLM call shows:

```
✅ Context [████████░░░░░░░░░░░░░░░░░░░░░░] 38.2%
   Input ~4821 tok | +3000 out | = ~7821/32768 [CODER — game.js]
```

If you see ⚠️ (>80%), the prompt is too long. Options:
- Reduce `snapshot_limit` in `config.json` (truncates file previews)
- Reduce `max_out_tokens` for the Critic and Planner (they don't need 3000 tokens)
- Increase `context_size` if your llama-server was launched with a larger `-c` value

---

## Running the Tetris reference example

```bash
# Using the hand-written spec (fastest, no Architect step)
python main.py "create a tetris clone" \
  --spec examples/tetris/spec.md \
  --output output/tetris \
  --max_cycles 12

# Full pipeline (Architect generates the spec from scratch)
python main.py "create a playable Tetris clone in the browser, with colors and sounds" \
  --output output/tetris \
  --max_cycles 12
```

Open `output/tetris/index.html` in a browser to test.

---

## Code style

- Python 3.11+
- No external dependencies beyond `openai` and `requests`
- Type hints on all public functions
- Docstring on every class and public method
- No print statements in `core/` — use the `label` parameter of `LLMClient.call()` for section headers
