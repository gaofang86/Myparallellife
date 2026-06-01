# 🪞 My Parallel Lives

![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Gradio](https://img.shields.io/badge/Gradio-6.x-orange)
![Claude Haiku](https://img.shields.io/badge/Claude-Haiku_4.5-blueviolet)
![W&B Weave](https://img.shields.io/badge/W%26B-Weave-yellow)
![Plotly](https://img.shields.io/badge/Plotly-Charts-lightgrey)
![LLM Eval](https://img.shields.io/badge/LLM--as--Judge-Evaluation-green)

**Let your other lives speak.**

A multi-agent simulation that takes one life decision and generates four parallel futures — lived out by four different versions of you — then lets them compare notes across time.

> *The moment you choose, you lose the ability to see what you've sacrificed.*

---

## The Problem

Every major decision collapses your future into one path. You optimize for the choice you can see — but you can never see the lives you didn't live.

Most decision tools tell you to **pros-and-cons list** your way to clarity. They don't tell you what your risk-averse self will feel at 45, or what your bold self will regret by 50, or what the version of you who left everything behind discovered that you haven't.

---

## What It Does

Input one decision (e.g. *"Age 28 — stay in the city or go home for a stable job?"*). Four AI agents simulate four divergent lives from that crossroads, then surface:

| Section | What happens |
|---|---|
| 📖 **Explore Stories** | Each persona lives out their path — scored across 5 life dimensions, one-line verdict, LLM-as-judge quality badges |
| 📊 **Life Dashboard** | Radar chart + score table comparing all 4 lives on wealth, happiness, stress, health, fulfillment |
| ☕ **Tea House** | The 4 versions of you talk across time — all 3 rounds run automatically in sequence |
| 🧠 **Synthesis** | A judge agent reads all 4 lives and finds what they share: the regret, the fear, the thing only visible when you see all four at once |
| ✨ **The Insight** | The core truth the simulation keeps returning to |
| 🔍 **Traces** | Live LLM call timeline (Gantt chart) + LLM-as-judge evaluation scores per persona |

---

## The Four Personas

| Persona | Archetype |
|---|---|
| 🔵 **The Steady One** | Played it safe. Built it slow. |
| 🔴 **The Maverick** | Bet everything. Won some, lost more. |
| 🟣 **The Ghost Path** | Chose well. Then the world changed. |
| 🟡 **The Wildcard** | Left the map entirely. |

---

## Architecture

```
User input (situation + age + questions)
        │
        ▼
LifeOrchestrator  ◄── Claude tool_use (cached system prompt)
        │
        ├── Phase 1: one orchestrator call → 4× run_outline tool_use
        │           └── ThreadPoolExecutor: 4 parallel outline generations
        │
        ├── Phase 2: 4× generate_story (parallel, streaming-ready)
        │           └── one-liner + regret quote per persona (cached system)
        │
        └── Phase 3: one orchestrator call → 4× run_score tool_use
                    └── ThreadPoolExecutor: 4 parallel score evaluations
        │
        ▼
LLM-as-Judge Evaluation (background, after Phase 3)
   12 scorer calls in parallel — ThreadPoolExecutor(max_workers=12)
   ├── consistency: does the story match the outline facts?
   ├── realism:     is the outcome plausible for this persona's choices?
   └── divergence:  how distinct is this story from the other 3?
        │
        ▼
Tea House (streaming, auto-advances through all 3 rounds)
   Round 1: junior → senior (forward advice)
   Round 2: senior ↔ senior (clash + envy + warning)
   Round 3: senior → junior (letter back)
        │
        ▼
Final Synthesis (judge agent reads all 4 stories)
```

**Why this is genuinely multi-agent:** the `LifeOrchestrator` makes a single LLM call that returns 4 `tool_use` blocks — one per persona. The orchestrator decides which agents to invoke; subagents execute in parallel. Not prompt injection or hardcoded routing.

**Why it's fast:** all LLM calls use `cache_control: ephemeral` on system prompts. After the first call per session, system prompts (~400 tokens each) are served from cache — ~85% token savings on every subsequent request. Evaluation runs 12 scorer calls concurrently instead of sequentially.

All LLM calls use **Claude Haiku 4.5** via the Anthropic API. Traces logged to **W&B Weave**.

---

## Quickstart

```bash
git clone https://github.com/gaofang86/Myparallellife.git
cd Myparallellife
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:
```
ANTHROPIC_API_KEY=your_key_here
WANDB_API_KEY=your_key_here   # optional
```

Run:
```bash
python app.py
```

Open `http://localhost:7860`

---

## Stack

- **LLM** — Anthropic Claude Haiku 4.5 (streaming + tool_use + prompt caching)
- **Multi-agent** — `LifeOrchestrator` + 4 subagents via Anthropic `tool_use`; `cache_control: ephemeral` on all system prompts
- **Evaluation** — LLM-as-judge (`@weave.op()`) scoring consistency / realism / divergence; 12 parallel calls via `ThreadPoolExecutor`
- **Observability** — W&B Weave for LLM traces + evaluation; W&B for score logging; in-app Gantt timeline
- **UI** — Gradio 6.x with custom CSS nav pills
- **Charts** — Plotly radar chart + horizontal bar timeline
- **Concurrency** — `ThreadPoolExecutor` for parallel tool execution and evaluation; `threading` for background generation
