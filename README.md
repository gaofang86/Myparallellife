# 🪞 My Parallel Lives

![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Gradio](https://img.shields.io/badge/Gradio-6.x-orange)
![Claude Haiku](https://img.shields.io/badge/Claude-Haiku_4.5-blueviolet)
![W&B Weave](https://img.shields.io/badge/W%26B-Weave-yellow)
![Plotly](https://img.shields.io/badge/Plotly-Radar_Chart-lightgrey)

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
| 📖 **Explore Stories** | Each persona lives out their path — scored across 5 life dimensions, with a one-line verdict |
| 📊 **Life Dashboard** | Radar chart + score table comparing all 4 lives on wealth, happiness, stress, health, fulfillment |
| ☕ **Tea House** | The 4 versions of you talk to each other — junior self asks forward, senior selves clash, then write letters back |
| 🧠 **Synthesis** | A judge agent reads all 4 lives and finds what they share: the regret, the fear, the thing only visible when you see all four at once |
| ✨ **The Insight** | The core truth the simulation keeps returning to |

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
4 × LifeAgent (parallel threads)
   ├── generate_outline()      → JSON life snapshot
   ├── generate_story()        → 250-word narrative
   ├── score_life()            → 5-dimension scores via judge LLM
   └── get_regret_quote()      → one-sentence deepest regret
        │
        ▼
Tea House rounds (streaming)
   Round 1: junior → senior (forward advice)
   Round 2: senior ↔ senior (clash + envy)
   Round 3: senior → junior (letter back)
        │
        ▼
Final Synthesis (judge agent, all 4 stories)
```

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

- **LLM** — Anthropic Claude Haiku 4.5 (streaming)
- **UI** — Gradio 6.x with custom CSS nav pills
- **Charts** — Plotly radar chart
- **Observability** — W&B Weave for LLM traces, W&B for score logging
- **Concurrency** — Python `threading` for parallel persona generation
