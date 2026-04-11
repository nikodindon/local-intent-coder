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
User prompt
    ↓
Phase 0: Designer (pre-code)
    → Adds visual guidelines (colors, borders, layout)
    ↓
Architect → spec.md + visual guidelines
    ↓
                    ┌───────────────────────────┐
                    │        Agent loop          │
                    │                             │
Phase 1:  Coder  →  files                        │
                    │       ↓                     │
Phase 2:  Critic  →  issues                      │
                    │       ↓                     │
            Planner  →  fix plan                 │
                    │       ↓                     │
Phase 3:  Coder  →  (repeat until ALL_COMPLETE)  │
                    │       ↓                     │
Phase 3:  Executor  →  browser tests (Playwright)│
                    │       ↓                     │
Phase 4:  Designer  →  visual audit (score /10)  │
                    │       ↓                     │
            If failed → Planner → Coder → loop   │
                    └───────────────────────────┘
                                │
                          Runnable artifact
                          + SHA256 (functional hash)
                                │
                          Seed stored
                          (prompt + model + hash ~ 300 bytes)
```

**Designer (pre-code)** — Before coding, adds concrete visual guidelines to the spec: color palettes with hex codes, border values, typography, layout rules, interactive states.

**Architect** — receives the user's natural-language prompt, produces a structured `.md` spec: target directory, file list with roles, feature requirements, technical constraints.

**Coder** — generates each file in sequence, respecting its declared role and the current state of the project. Writes complete code, no stubs.

**Critic** — reviews the full project snapshot. Lists only blocking problems (missing functions, broken dependencies, logic errors). Returns `ALL_COMPLETE` when done.

**Executor** — opens the artifact in a headless Chromium browser via Playwright. Detects the artifact type (board game, to-do app, counter, etc.) and runs type-specific tests. Catches runtime bugs the Critic can't see.

**Planner** — converts the Critic's or Executor's output into a minimal fix plan (≤3 files per cycle), combining all issues from the same file into a single action.

**Designer (post-render)** — opens the rendered page in Playwright, extracts computed styles via `getComputedStyle()`, audits against the visual guidelines. Scores 1-10. If below threshold, triggers a CSS fix cycle.

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
├── main.py               # Entry point: python main.py "create a tic-tac-toe game"
├── validate.py           # Validation script: check if generated artifacts meet criteria
├── seed.py               # DNS seed storage CLI
├── agent/
│   ├── architect.py      # Prompt → structured spec .md
│   ├── coder.py          # Generates each file per its declared role
│   ├── critic.py         # Lists blocking issues only (with repetition detection)
│   ├── planner.py        # Minimal fix plan (≤3 actions per cycle)
│   ├── designer.py       # Visual guidelines + post-render style audit [NEW]
│   ├── loop.py           # Orchestrates all 5 phases
│   └── prompts.py        # All system prompts (primary tuning surface)
├── core/
│   ├── llm.py            # Local LLM client (OpenAI-compat, llama.cpp / LM Studio / Ollama)
│   ├── config.py         # Load config.json with defaults
│   ├── session.py        # Session state + project snapshot + metrics
│   ├── hasher.py         # Functional hashing (hash execution output, not source)
│   └── executor.py       # Playwright browser test runner [NEW]
├── storage/
│   └── dns_layer.py      # Optional: store seeds in Cloudflare DNS TXT records (from mnemo)
├── output/               # Generated artifacts (gitignored)
├── results/              # Experiment results, populated as research progresses
│   ├── phase1-results.md
│   ├── phase1-5-results.md   # Execution validation + visual audit results
│   └── dev-summary-2026-04-10.md
└── config.json           # LLM endpoint, model, context size (gitignored)
```

---

## Quickstart

### Requirements

```bash
pip install openai requests playwright
playwright install chromium
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
  "max_out_tokens": 3000,
  "snapshot_limit": 800,
  "temperature": 0.1
}
```

### Run

```bash
# Full 5-phase pipeline
python main.py "create a playable Tic-Tac-Toe game"

# With logging (tail with: Get-Content -Wait <path>)
python main.py "create a Tic-Tac-Toe game" --max_cycles 8 --output output/tictactoe --log output/tictactoe.log
```

The Designer adds visual guidelines, the Architect builds the spec, the loop runs until the Critic says `ALL_COMPLETE`, Executor validates functionality, and Designer audits visual quality.

### Validate

After generation, check if the artifact meets success criteria:

```bash
python validate.py output/tictactoe
```

This validates:
- HTML structure and script includes
- Core game features (pieces, controls, collision, scoring, game over)
- Sound and color system implementation
- Session completion status

---

## Research agenda

This project documents experiments as they run. Each phase answers a specific question.

### Phase 1 — Agent loop baseline

*Can Qwen2.5-Coder-7B generate a working multi-file JS project autonomously?*

The Tetris clone is the reference benchmark. Success criteria: `index.html` opens in a browser, pieces fall, lines clear, score updates, game over triggers.

**Status:** ✅ Complete. See `results/phase1-results.md` for full analysis.

**Summary:**
- 6/6 files generated (100%)
- All critical features present in code: piece, move, rotate, collision, game over, score
- Critic issue: Got stuck in repetition loop (now fixed with repetition detection)
- **Reality check**: Generated code has logic bugs (const vs let, duplicate gameLoop functions)
- **Phase 1.5 discovery**: Text-only Critic can't catch runtime bugs → added Executor

| Metric | Result |
|---|---|
| Files generated correctly on first pass | 6/6 (100%) |
| Average cycles to ALL_COMPLETE | N/A (Critic bug - now fixed) |
| Average tokens consumed per run | ~10 LLM calls |
| Code generated | ✅ Yes |
| Code actually works in browser | ⚠️ Partially (has logic bugs) |

---

### Phase 1.5 — Execution-based validation

*Can we catch runtime bugs that the text-only Critic misses?*

**Status:** ✅ Complete. See `results/phase1-5-results.md` for full analysis.

**What we built:**
- `core/executor.py` — Playwright-based browser test runner with artifact type detection
- Auto-generates type-specific tests (board game, to-do app, counter, generic web)
- Intercepts `alert()` dialogs to capture win/lose messages
- Tests actual functionality (not just code presence)
- Feeds concrete failures back to Coder for fixes

**Results — Tic-Tac-Toe v4 (2026-04-11):**

| Metric | Result |
|---|---|
| Files generated | 3/3 (100%) |
| Critic cycles | 2 total |
| Executor tests | ✅ **5/5 PASSED** |
| — Board renders | ✅ |
| — Cell click places mark | ✅ |
| — Turn alternation | ✅ |
| — Win detection (via alert) | ✅ |
| — Reset works | ✅ |

**Key discoveries:**
- Executor MUST detect artifact type — hardcoded to-do tests fail on board games
- `alert()` dialogs must be intercepted — Playwright blocks them by default
- ALL_COMPLETE ≠ visually acceptable — need post-render visual audit

---

### Phase 1.6 — Visual Design Audit

*Can an automated Designer catch ugly CSS that the Critic and Executor both miss?*

**Status:** ✅ Complete. See `results/phase1-5-results.md` for full analysis.

**What we built:**
- `agent/designer.py` — Two-phase visual quality agent
  - **Pre-code**: Enriches spec with concrete visual guidelines (hex colors, borders, typography, layout, hover states)
  - **Post-render**: Opens page in Playwright, extracts computed styles, audits against guidelines, scores 1-10

**Results — Tic-Tac-Toe v4 (2026-04-11):**

| Round | Score | Verdict |
|---|---|---|
| Pre-code guidelines | — | Added: blue `#3498db` / red `#e74c3c` palette, borders, centered layout |
| Post-render audit (1st) | **3/10** | ❌ NEEDS_VISUAL_FIXES — no cell borders, transparent background, title not centered |
| CSS fix cycle | — | Planner → Coder added borders, background color |
| Post-render audit (2nd) | **10/10** | ✅ VISUALLY_COMPLETE |

**Key discovery:** The Coder frequently ignores pre-code visual guidelines. The post-render audit is the enforcement mechanism that actually drives improvements. The combination works: pre-code sets the standard, post-render enforces it.

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

Tested targets:
- ✅ Tic-Tac-Toe game (Phase 1.5/1.6 complete, 2 cycles, visually polished)
- ✅ Counter app (Phase 1.5, 1 cycle, validated)
- ✅ To-do app v5 (Phase 1.5, 3/4 tests pass)

| Artifact | Functional | Visual | Cycles | Notes |
|---|---|---|---|---|
| Tetris clone | ⚠️ Logic bugs | ❌ Bare | 2 (incomplete) | Phase 1 baseline |
| Counter app | ✅ | N/A | 1 | Simple, works |
| To-do v5 | ✅ | N/A | — | 3/4 tests pass |
| Tic-Tac-Toe v4 | ✅ | ✅ (10/10) | 2 | Full 5-phase pipeline |

---

## Key findings so far

*(Updated 2026-04-11)*

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

**Finding 6 — Python `openai` library hangs with llama-server on Windows.**
The official `openai` Python library freezes when communicating with llama-server on Windows. Replaced with raw HTTP requests via `http.client` — now works reliably. (2026-04-10)

**Finding 7 — The Critic cannot catch runtime logic bugs.**
The text-based Critic can verify "is localStorage code present?" but cannot detect "saveTasks() is never called" or "delete button created on wrong event handler". It only reads code, doesn't execute it. This discovery led to Phase 1.5: execution-based validation. (2026-04-10)

**Finding 8 — Executor MUST detect artifact type.**
A hardcoded to-do app test suite fails catastrophically on board games (30-second timeout waiting for `<input>` elements that don't exist). The Executor now detects artifact type (board game, to-do, counter, generic web) and generates appropriate tests. (2026-04-11)

**Finding 9 — `alert()` dialogs must be intercepted.**
Many LLM-generated games use `alert()` for win/lose messages. Playwright blocks these by default, causing the test to hang. The Executor uses `page.on("dialog", ...)` to accept dialogs and capture their content for verification. (2026-04-11)

**Finding 10 — ALL_COMPLETE ≠ visually acceptable.**
The Critic validates code correctness but cannot see that a page has no borders, no colors, and an uncentered title. The Designer Phase 4 is essential for visual quality. Without it, every generated artifact is functional but bare-bones. (2026-04-11)

**Finding 11 — Designer pre-code + post-render = enforcement.**
Pre-code adds detailed visual guidelines (specific hex colors, font sizes, border values) to the spec. The Coder frequently ignores these. The post-render audit enforces them by scoring the actual rendered page and triggering fix cycles. Together they drove Tic-Tac-Toe from 3/10 to 10/10 in one cycle. (2026-04-11)

**Finding 12 — 4-phase pipeline completes in 2 cycles.**
Tic-Tac-Toe v4 went from bare-bones to visually polished in just 2 total cycles (~8 minutes CPU-only). This is efficient for a 5-phase pipeline with visual enforcement. (2026-04-11)

**Finding 13 — Win timing bug in generated games.**
The LLM generates `alert()` followed by synchronous `resetBoard()`. The browser hasn't repainted the winning cell before the alert blocks the thread, and then the board resets. The player never sees the completed winning line. This is a gameplay UX bug that neither Critic nor Executor can catch. (2026-04-11)

**Finding 14 — Planner doesn't map issues to the correct file.**
During Tic-Tac-Toe v5, the Designer flagged "no borders on cells" (a CSS issue). The Planner told the Coder to fix `index.html` (HTML). The Coder added a title tag but didn't touch CSS. The Designer re-audited → same issues → infinite loop. The LLM-as-Planner has no understanding of which file type owns which problem. Requires rule-based file routing or structured issue reports. (2026-04-11)

**Finding 15 — External review consensus: measure compression NOW.**
Three independent AI reviews (GPT, Grok, Claude) unanimously agreed: the project is strong research but the core claim (compression ratio) has zero measured data points. Tic-Tac-Toe v4 has all the data needed — this should be the next priority. (2026-04-11)

---

## The deeper question

Every experiment here is building an empirical answer to a question information theory poses in the abstract:

> What is the practical Kolmogorov complexity of human-authored programs, as measured by a 7B-parameter language model at temperature=0?

Not the theoretical minimum description length — that's uncomputable. The *practical* minimum: the shortest prompt that, fed to this specific model with these specific parameters, reliably produces a working implementation.

The LLM is a learned compression dictionary, trained on the entire corpus of human-written code. The more structured and intentional the target artifact, the better the compression ratio. A Tetris clone — with its well-defined rules, standard piece set, and conventional architecture — should compress better than a novel or a random binary blob. That's the hypothesis. The results will say.

---

## Roadmap

What's done, what's next, what's planned.

### ✅ Complete

- [x] **Phase 1** — Agent loop baseline (Tetris clone, 6/6 files)
- [x] **Phase 1.5** — Execution-based validation (Executor with Playwright, type detection)
- [x] **Phase 1.6** — Visual design audit (Designer pre-code + post-render, 3/10 → 10/10)
- [x] Tic-Tac-Toe as second benchmark (5/5 tests, visually polished, 2 cycles)

### 🔶 In progress — Now

- [ ] **Gameplay polish** — Tic-Tac-Toe: win line highlight, turn indicator, alert timing fix
- [ ] **Coder → visual sensitivity** — Make the Coder actually use Designer guidelines when generating CSS
- [ ] **Executor coverage** — Add Snake (grid game), Counter, and meaningful generic web fallback

### 📋 Next up

- [ ] **Phase 2** — Architect quality (flat spec vs role-annotated, measure cycle reduction)
- [ ] **Phase 3** — Seed compression ratio (first real measurement with Tic-Tac-Toe v4)
- [ ] **Phase 6** — Generalisation (Snake game as third benchmark)

### 🔭 Planned

- [ ] **Phase 4** — Functional hash stability (same machine, temp=0, multiple runs)
- [ ] **Phase 5** — Cross-machine seed portability (laptop → desktop reconstruction)

### Known issues

| Issue | Impact | Priority | Status |
|---|---|---|---|
| Win alert shows before repaint, board resets instantly | Player never sees winning line | 🔴 High | Fix identified (setTimeout) |
| No turn indicator ("Player X's turn") | UX gap | 🟡 Medium | Designer specified, Coder ignores |
| Coder ignores Designer visual guidelines | CSS requires fix cycles | 🟡 Medium | Prompt improved, needs validation |
| Executor generic fallback always passes | False positives for unknown types | 🟡 Medium | |
| **Planner maps issues to wrong files** | **Infinite loops in Phase 4** | 🔴 **Critical** | **Fix in progress** |
| Compression ratio never measured (all TBD) | Core research question unanswered | 🟠 **Critical** | **Next after Planner fix** |

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
- New target artifacts beyond Tetris and Tic-Tac-Toe
- Better Architect, Critic, or Designer prompts that produce tighter specs and better code

---

## License

MIT
