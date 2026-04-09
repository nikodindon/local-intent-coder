# Intent Engine

> *Store the intention, not the content.*

**Intent Engine** is a research project on local AI agents running under real hardware constraints — no cloud, no high-end GPU. It explores a deceptively simple question:

> What is the minimum description needed for a local language model to reliably reconstruct a complete software artifact?

This project synthesises two earlier experiments — **[mnemo](https://github.com/nikodindon/mnemo)** (intentional compression over DNS) and **[local-agent-tetris](https://github.com/nikodindon/local-agent-tetris)** (autonomous agent coding loop) — into a unified, cleanly documented research platform.

Named after Mnemosyne, the Greek goddess of memory. What we store isn't data — it's the *memory of how to produce data*.

---

## The core idea

Classic software storage: you keep the file.
Mnemo's insight: you keep the *intent* to recreate the file, and let a local LLM reconstruct it on demand.

The natural next question: what if the agent that generates the file *is itself* the compression pipeline? Give it a short prompt. It builds the spec. It writes the code. It critiques and repairs itself. What you're left with is a tiny seed — the original intent — that can regenerate a working program, on your machine, with no internet connection.

This is not theoretical compression in the Kolmogorov sense. It's empirical: we measure how short a prompt has to be, for a specific 7B model at temperature=0, to reliably regenerate a specific artifact. Every experiment adds a data point to that map.

---

## Architecture

```
User prompt  →  Architect  →  spec.md
                                │
                                ▼
                    ┌───────────────────────┐
                    │      Agent loop       │
                    │                       │
                    │  Coder  → files       │
                    │    ↓                  │
                    │  Critic → issues      │
                    │    ↓                  │
                    │  Planner → fix plan   │
                    │    ↓                  │
                    │  Coder  → (repeat)    │
                    └───────────────────────┘
                                │
                          Runnable artifact
                          + SHA256 (functional hash)
                                │
                          Seed stored
                          (prompt + model + hash ~ 300 bytes)
```

**Architect** — receives the user's natural-language prompt, produces a structured `.md` spec: target directory, file list with roles, feature requirements, technical constraints.

**Coder** — generates each file in sequence, respecting its declared role and the current state of the project. Writes complete code, no stubs.

**Critic** — reviews the full project snapshot. Lists only blocking problems (missing functions, broken dependencies, logic errors). Returns `ALL_COMPLETE` when done.

**Planner** — converts the Critic's output into a minimal fix plan (≤3 files per cycle), combining all issues from the same file into a single action.

**Functional hash** — rather than hashing source code (which drifts across machines due to float16 arithmetic differences in GPU vs CPU inference), we hash the *execution output*. Two machines generating slightly different Python that both print `1\n2\n...100\n` produce identical hashes. This makes seeds cross-machine stable.

---

## Hardware

This project is explicitly designed for modest hardware. Every result is documented with its exact environment.

| Machine | CPU | RAM | GPU | Mode | Speed |
|---|---|---|---|---|---|
| Asus VivoBook 15 | Ryzen 5 5500U | 20 GB | None | CPU only | **4.81 tok/s** |
| Custom desktop | Ryzen 5 1600 AF | 32 GB | GTX 1650 Super 4 GB | Partial GPU offload | TBD |

> No RTX 3090. No cloud API. If your machine runs Windows 11, it can probably run this.

Model: **Qwen2.5-Coder-7B-Instruct Q4_K_M** (~4.3 GB) via llama.cpp.

---

## Project structure

```
intent-engine/
├── README.md
├── main.py               # Entry point: python main.py "create a tetris clone"
├── agent/
│   ├── architect.py      # Prompt → structured spec .md
│   ├── coder.py          # Generates each file per its declared role
│   ├── critic.py         # Lists blocking issues only
│   └── planner.py        # Minimal fix plan (≤3 actions per cycle)
├── core/
│   ├── llm.py            # Local LLM client (OpenAI-compat, llama.cpp / LM Studio / Ollama)
│   ├── context.py        # Token budget estimation and context management
│   ├── session.py        # Session state + project snapshot
│   └── hasher.py         # Functional hashing (hash execution output, not source)
├── storage/
│   └── dns_layer.py      # Optional: store seeds in Cloudflare DNS TXT records (from mnemo)
├── examples/
│   └── tetris/           # Reference example: full Tetris clone
│       ├── spec.md
│       └── [generated files]
├── results/              # Experiment results, populated as research progresses
└── config.json           # LLM endpoint, model, context size
```

---

## Quickstart

### Requirements

```bash
pip install openai requests
```

Run llama-server locally (CPU-only example):

```powershell
llama-server `
  -m C:\models\Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf `
  -ngl 0 -c 32768 -np 1 -t 10 `
  --host 0.0.0.0 --port 8080
```

### Config

```json
{
  "base_url": "http://localhost:8080/v1",
  "api_key": "sk-placeholder",
  "model": "qwen2.5-coder-7b",
  "context_size": 32768,
  "max_out_tokens": 3000
}
```

### Run

```bash
python main.py "create a playable Tetris clone in the browser, with colors and sounds"
```

The Architect builds the spec, the loop runs until the Critic says `ALL_COMPLETE` or max cycles is reached.

```bash
python main.py "create a playable Tetris clone" --max_cycles 12 --output ./output/tetris
```

---

## Research agenda

This project documents experiments as they run. Each phase answers a specific question.

### Phase 1 — Agent loop baseline

*Can Qwen2.5-Coder-7B generate a working multi-file JS project autonomously?*

The Tetris clone is the reference benchmark. Success criteria: `index.html` opens in a browser, pieces fall, lines clear, score updates, game over triggers.

**Status:** In progress.

| Metric | Result |
|---|---|
| Files generated correctly on first pass | TBD |
| Average cycles to ALL_COMPLETE | TBD |
| Average tokens consumed per run | TBD |
| Success rate (3 independent runs) | TBD |

---

### Phase 2 — Architect quality

*How good is the Architect's spec.md at constraining the Coder?*

Hypothesis: a spec that assigns an explicit role to each file (rather than a flat file list) reduces the number of Critic cycles needed.

We compare two conditions:
- **Flat spec** — just file names and a feature list
- **Role-annotated spec** — each file gets a precise responsibility description

| Condition | Avg cycles | Avg tokens | Success rate |
|---|---|---|---|
| Flat spec | TBD | TBD | TBD |
| Role-annotated spec | TBD | TBD | TBD |

---

### Phase 3 — Seed compression ratio

*How much does the seed compress the artifact?*

For each successful run, we measure:

```
Compression ratio = seed_size_bytes / artifact_size_bytes
```

Where `seed_size_bytes` is the length of the compressed prompt + model identifier + functional hash, and `artifact_size_bytes` is the total size of all generated files.

| Artifact | Seed size | Artifact size | Ratio |
|---|---|---|---|
| Tetris clone | TBD | TBD | TBD |

---

### Phase 4 — Functional hash stability

*Is the functional hash of the generated artifact stable across runs?*

At `temperature=0`, same machine, same model: the source code should be byte-identical (as established in mnemo phase 1). But does the *running game* produce a deterministic enough output to hash reliably?

For code artifacts that produce interactive output (rather than a printed stdout), we define the functional hash as the SHA256 of a controlled execution trace (e.g. simulated key inputs, captured frame state).

---

### Phase 5 — Cross-machine seed portability

*Can a seed generated on the laptop be reconstructed on the desktop?*

This is the hardest phase. CPU vs GPU inference produces different floating-point accumulation, which can flip token choices at low probability margins. Functional hashing (phase 4) is the proposed solution: if two machines produce different source code that runs identically, the seed is still valid.

---

### Phase 6 — Generalisation

*Does the pipeline work for non-Tetris targets?*

We test two additional targets:
- A terminal-based snake game
- A single-page weather dashboard (static HTML/CSS, no JS framework)

If the Architect can produce a correct spec and the loop converges for these targets, the pipeline is general.

---

## Key findings so far

*(Migrated from mnemo and local-agent-tetris)*

**Finding 1 — Temperature=0 is deterministic on the same machine.**
Running the full 8-prompt benchmark with `temperature=0` on the laptop produced 8/8 perfect SHA matches across 5 independent runs with varying seeds and model unloading between runs. The seed parameter is irrelevant at temperature=0 (greedy decoding has no randomness to seed).

**Finding 2 — Cross-machine determinism breaks completely.**
CPU-only and GPU inference produce 0/5 matching hashes across all tested prompts, including trivial ones. The divergence is often a single extra sentence added by one machine and not the other — enough to flip SHA256. Root cause: float16 arithmetic is not associative; GPU parallel accumulation vs CPU sequential accumulation produces different rounding at narrow probability gaps.

**Finding 3 — CPU-only inference is the more stable environment for seeds.**
Sequential float operations on a fixed CPU architecture are fully deterministic. GPU is faster but non-portable. For same-machine use, both work. For cross-machine seeds, functional hashing (hash the execution output, not the source) is the correct approach.

**Finding 4 — A minimal custom agent outperforms a general tool harness for small models.**
Hermes Agent failed silently on Qwen2.5-Coder-7B due to tool-call format mismatch and context overhead (~4K tokens of system prompt). A ~80-line custom agent with a simple `<tool>{...}</tool>` format and direct subprocess execution was more reliable and used context more efficiently.

**Finding 5 — File role assignment is load-bearing for multi-file coherence.**
When each file is given an explicit responsibility description in the system prompt, the Coder produces less cross-file variable collision and fewer "undefined function" errors caught by the Critic. This reduces the average number of repair cycles.

---

## The deeper question

Every experiment here is building an empirical answer to a question information theory poses in the abstract:

> What is the practical Kolmogorov complexity of human-authored programs, as measured by a 7B-parameter language model at temperature=0?

Not the theoretical minimum description length — that's uncomputable. The *practical* minimum: the shortest prompt that, fed to this specific model with these specific parameters, reliably produces a working implementation.

The LLM is a learned compression dictionary, trained on the entire corpus of human-written code. The more structured and intentional the target artifact, the better the compression ratio. A Tetris clone — with its well-defined rules, standard piece set, and conventional architecture — should compress better than a novel or a random binary blob. That's the hypothesis. The results will say.

---

## Intellectual property note

*(See mnemo README for the full discussion)*

A prompt that reliably regenerates a specific program occupies a legally ambiguous space. Under current doctrine, a prompt is closer to a specification or recipe than to the protected work itself. But when paired with `temperature=0` and functional hashing, it can act as a practical decompressor for that work. Where the line sits between "unprotectable idea" and "contributory infringement" is an open question this project intentionally surfaces — not to answer it, but to make it concrete and empirically measurable.

---

## Prior work

- **[mnemo](https://github.com/nikodindon/mnemo)** — DNS as a generative filesystem; determinism experiments; functional hashing design
- **[local-agent-tetris](https://github.com/nikodindon/local-agent-tetris)** — agent harness; hardware benchmarks; Critic/Planner loop
- **[doom-over-dns](https://github.com/resumex/doom-over-dns)** — the original inspiration: constrained storage as a feature
- **[Octopus Invaders by @sudoingX](https://x.com/sudoingX)** — agent coding experiment that started the chain

---

## Contributing

Especially welcome:
- Results from different hardware (other CPUs, other GPU tiers)
- Prompts that compress well (high artifact/seed ratio with reliable reconstruction)
- New target artifacts beyond Tetris
- Better Architect prompts that produce tighter specs

---

## License

MIT
