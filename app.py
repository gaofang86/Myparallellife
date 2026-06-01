"""
Parallel Lives — Visual-first redesign.
Dashboard before stories. Cards over walls of text.
"""
import json, re, threading, time
from functools import partial
import gradio as gr
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv(override=True)

from life_agent import LifeAgent
from personas import PERSONAS
from judge import DIMENSIONS, score_life, final_synthesis
from evaluator import evaluate_stories
import wandb, weave
import os, anthropic

_anthropic_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
_SIMPLE_SYSTEM = [{"type": "text", "text": "You are a concise assistant. Follow instructions exactly.", "cache_control": {"type": "ephemeral"}}]

WANDB_PROJECT = "parallel-lives"
WEAVE_PROJECT = "parallel-lives"

PERSONA_KEYS = list(PERSONAS.keys())
PERSONA_COLORS = {
    "steady":   "#4A90D9",
    "maverick": "#E85D4A",
    "ghost":    "#7C3AED",
    "wildcard": "#D97706",
}
PLOTLY_COLORS = {
    "The Steady One":  ("#4A90D9", "rgba(74,144,217,0.25)"),
    "The Maverick":    ("#E85D4A", "rgba(232,93,74,0.25)"),
    "The Ghost Path":  ("#7C3AED", "rgba(124,58,237,0.25)"),
    "The Wildcard":    ("#D97706", "rgba(217,119,6,0.25)"),
}
STAT_ICONS = {"wealth": "💰", "happiness": "❤️", "stress": "🔥", "health": "🩺", "fulfillment": "🧠"}
YEAR_OPTIONS = [-30, -20, -10, 10, 20, 30]
CHIPS = [
    "Age 25 — should I join a big tech company or an early-stage startup?",
    "Age 28 — go back to hometown for a stable government job, or keep grinding in the city?",
    "Age 30 — quit my industry and go abroad for a Master's degree to pivot careers?",
    "Age 25 — should I become an ML engineer or stay on the data science track?",
]

# ── Shared state ──────────────────────────────────────────────────────────────
_state         = {}
_outline_done  = {k: threading.Event() for k in PERSONA_KEYS}
_outline_data  = {}
_persona_agent = {}
_persona_story = {}
_score_data    = {}
_score_done    = {k: threading.Event() for k in PERSONA_KEYS}
_regret_data   = {}
_all_scored    = threading.Event()
_oneliner_data = {}
_oneliner_done = {k: threading.Event() for k in PERSONA_KEYS}
_trace_events  = []   # list of dicts: {name, persona, phase, start, end, duration}
_trace_t0      = 0.0  # session start time
_eval_data     = {}
_eval_done     = threading.Event()


def _record(name: str, persona: str, phase: str, start: float, end: float):
    _trace_events.append({
        "name": name, "persona": persona, "phase": phase,
        "start": round(start - _trace_t0, 3),
        "end": round(end - _trace_t0, 3),
        "duration": round(end - start, 3),
    })


# ── LLM helper ───────────────────────────────────────────────────────────────

def _call_llm_simple(prompt, max_tokens=120):
    resp = _anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=_SIMPLE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _stream_simple(prompt, system=None, max_tokens=300):
    """Yield text tokens from a one-shot streaming LLM call."""
    kwargs = dict(model="claude-haiku-4-5-20251001", max_tokens=max_tokens,
                  messages=[{"role": "user", "content": prompt}])
    if system:
        kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}] if isinstance(system, str) else system
    else:
        kwargs["system"] = _SIMPLE_SYSTEM
    with _anthropic_client.messages.stream(**kwargs) as stream:
        yield from stream.text_stream


def _get_one_liner(key, outline):
    p = PERSONAS[key]
    narrative = outline.get("narrative", outline.get("key_life_event", ""))
    prompt = (
        f"{p['label']}: {p['tagline']}.\n"
        f"Their life at this point: {narrative}\n\n"
        f"Write ONE punchy sentence that captures this life. Third person. Under 15 words. "
        f"Make it sting or resonate — like: "
        f"'He got everything he wanted too early to enjoy it.' "
        f"Output only the sentence, no quotes, no labels."
    )
    try:
        return _call_llm_simple(prompt, max_tokens=50)
    except Exception:
        return p["tagline"]


def _get_regret_quote(label, story):
    prompt = (
        f"Life story for {label}:\n\"{story[:900]}\"\n\n"
        f"Write ONE sentence (under 25 words) as this person's deepest regret. "
        f"First person, present tense. Specific and vivid — not a generic platitude. "
        f"Output only the sentence, no labels or preamble."
    )
    try:
        return _call_llm_simple(prompt, max_tokens=80)
    except Exception:
        return "No regrets captured."


# ── Visual HTML helpers ───────────────────────────────────────────────────────

def years_display_html(val):
    sign = "+" if val > 0 else ""
    color = "#4A90D9" if val > 0 else "#E85D4A"
    direction = "forward →" if val > 0 else "← backward"
    return (
        f'<div style="text-align:center;padding:10px 0 6px 0;">'
        f'<span style="color:#888;font-size:13px;">Jump </span>'
        f'<span style="font-size:26px;font-weight:800;color:{color};">{sign}{val}</span>'
        f'<span style="color:#888;font-size:13px;"> years &nbsp;{direction}</span>'
        f'</div>'
    )


def md_to_html(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^*\n]+?)\*', r'<em>\1</em>', text)
    return text.replace('\n', '<br>')


def _score_bar(val, color):
    pct = int(val * 10)
    return (
        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
        f'<div style="flex:1;height:5px;background:#eee;border-radius:3px;overflow:hidden;">'
        f'<div style="width:{pct}%;height:100%;background:{color};border-radius:3px;transition:width 0.3s;"></div>'
        f'</div>'
        f'<span style="font-size:11px;color:#888;min-width:14px;">{val}</span>'
        f'</div>'
    )


def snapshot_card_html(key):
    c = PERSONA_COLORS[key]
    p = PERSONAS[key]
    oneliner = _oneliner_data.get(key, "…")
    scores = _score_data.get(key)

    if scores:
        avg = round(sum(scores.values()) / len(scores), 1)
        score_rows = "".join(
            f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
            f'<span style="font-size:11px;color:#888;width:70px;">{STAT_ICONS.get(d,"·")} {d[:3].upper()}</span>'
            f'{_score_bar(scores.get(d, 5), c)}'
            f'</div>'
            for d in ["wealth", "happiness", "fulfillment", "stress"]
        )
        avg_html = f'<span style="font-size:22px;font-weight:800;color:{c};">{avg}</span><span style="font-size:11px;color:#aaa;">/10</span>'
    else:
        score_rows = '<div style="color:#ccc;font-size:12px;">Scoring…</div>'
        avg_html = ""

    eval_result = _eval_data.get(key)
    if eval_result:
        eval_pills = "".join(
            f'<span style="background:#f3f4f6;border-radius:6px;padding:2px 7px;'
            f'font-size:10px;color:#666;margin-right:3px;white-space:nowrap;">'
            f'{dim[:3].upper()} <b style="color:{"#16a34a" if eval_result[dim]["score"]>=7 else "#dc2626" if eval_result[dim]["score"]<=4 else "#888"};">{eval_result[dim]["score"]}</b></span>'
            for dim in ["consistency", "realism", "divergence"]
            if dim in eval_result
        )
        eval_row = f'<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:3px;">{eval_pills}</div>'
    else:
        eval_row = ""

    return (
        f'<div style="border:2px solid {c}30;border-radius:16px;padding:20px;'
        f'background:linear-gradient(135deg,{c}0a,white);height:100%;box-sizing:border-box;">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">'
        f'<div>'
        f'<div style="color:{c};font-size:16px;font-weight:800;">{p["label"]}</div>'
        f'<div style="color:#aaa;font-size:11px;font-style:italic;">{p["tagline"]}</div>'
        f'</div>'
        f'{avg_html}'
        f'</div>'
        f'<p style="font-size:14px;color:#222;line-height:1.5;margin:10px 0 12px 0;font-style:italic;">"{oneliner}"</p>'
        f'{score_rows}'
        f'{eval_row}'
        f'</div>'
    )


def snapshots_grid_html(keys_ready):
    """Render a 2x2 grid of snapshot cards for the given ready keys."""
    if not keys_ready:
        return '<p style="color:#aaa;text-align:center;padding:40px;">Generating outlines…</p>'
    cards = "".join(
        f'<div style="flex:0 0 calc(50% - 6px);">{snapshot_card_html(k)}</div>'
        for k in keys_ready
    )
    return f'<div style="display:flex;flex-wrap:wrap;gap:12px;">{cards}</div>'


def story_card_html(key, text, streaming=False):
    c = PERSONA_COLORS[key]
    p = PERSONAS[key]
    cursor = '<span style="animation:blink 1s infinite;color:#999;">▌</span>' if streaming else ""
    rendered = md_to_html(text) if not streaming else text.replace('\n', '<br>')
    scores = _score_data.get(key)

    if scores:
        pills = "".join(
            f'<span style="background:{c}18;color:{c};padding:2px 9px;border-radius:20px;'
            f'font-size:11px;font-weight:700;margin-right:4px;white-space:nowrap;">'
            f'{STAT_ICONS.get(d,"·")} {d[:3].upper()} {scores.get(d,5)}/10</span>'
            for d in ["wealth", "happiness", "fulfillment", "stress"]
        )
        score_row = f'<div style="margin-bottom:12px;line-height:2;">{pills}</div>'
    else:
        score_row = ""

    return (
        f'<div style="border-left:4px solid {c};border-radius:10px;padding:20px 24px;'
        f'background:#fafafa;box-shadow:0 2px 8px rgba(0,0,0,0.05);">'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;">'
        f'<h3 style="color:{c};margin:0;font-size:18px;">{p["label"]}</h3>'
        f'<span style="color:#bbb;font-size:12px;font-style:italic;">{p["tagline"]}</span></div>'
        f'{score_row}'
        f'<div style="color:#333;line-height:1.9;font-size:14px;">{rendered}{cursor}</div>'
        f'</div>'
    )


def build_radar_chart(all_scores):
    dims = [d.capitalize() for d in DIMENSIONS]
    fig = go.Figure()
    for label, scores in all_scores.items():
        vals = [scores.get(d.lower(), 5) for d in DIMENSIONS]
        line_color, fill_color = PLOTLY_COLORS.get(label, ("#999", "rgba(150,150,150,0.2)"))
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]], theta=dims + [dims[0]], fill="toself", name=label,
            line=dict(color=line_color, width=2.5), fillcolor=fill_color,
        ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 10], tickfont=dict(size=10)),
                   angularaxis=dict(tickfont=dict(size=13))),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="center", x=0.5),
        margin=dict(t=40, b=70, l=60, r=60), height=420, paper_bgcolor="white",
        title=dict(text="Life Quality — 5 Dimensions", font=dict(size=15)),
    )
    return fig


def comparison_dashboard_html(all_scores, regrets):
    label_to_key = {PERSONAS[k]["label"]: k for k in PERSONA_KEYS}
    dims = ["wealth", "happiness", "stress", "health", "fulfillment"]

    # Score table
    header_cells = "".join(
        f'<th style="padding:8px 14px;background:#f7f7f7;font-size:12px;font-weight:600;'
        f'text-align:center;white-space:nowrap;">{STAT_ICONS[d]} {d.capitalize()}</th>'
        for d in dims
    ) + '<th style="padding:8px 14px;background:#f7f7f7;font-size:12px;font-weight:700;text-align:center;">Avg</th>'

    rows = ""
    for label, scores in all_scores.items():
        key = label_to_key.get(label)
        c = PERSONA_COLORS.get(key, "#888")
        avg = round(sum(scores.values()) / len(scores), 1) if scores else 0
        cells = "".join(
            f'<td style="padding:8px 14px;text-align:center;font-size:13px;font-weight:600;'
            f'color:{"#16a34a" if scores.get(d,5)>=7 else "#dc2626" if scores.get(d,5)<=4 else "#666"};">'
            f'{scores.get(d,5)}</td>'
            for d in dims
        )
        rows += (
            f'<tr style="border-bottom:1px solid #f0f0f0;">'
            f'<td style="padding:8px 14px;font-weight:700;color:{c};font-size:13px;white-space:nowrap;">{label}</td>'
            f'{cells}'
            f'<td style="padding:8px 14px;text-align:center;font-size:15px;font-weight:800;color:{c};">{avg}</td>'
            f'</tr>'
        )

    table = (
        f'<div style="overflow-x:auto;margin-bottom:24px;border:1px solid #eee;border-radius:10px;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>'
        f'<th style="padding:8px 14px;background:#f7f7f7;font-size:12px;font-weight:600;text-align:left;">Life</th>'
        f'{header_cells}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div>'
    )

    # Regret cards (2-column grid)
    regret_cards = ""
    for label, regret in regrets.items():
        key = label_to_key.get(label)
        c = PERSONA_COLORS.get(key, "#888")
        if regret:
            regret_cards += (
                f'<div style="border-left:4px solid {c};padding:12px 16px;background:white;'
                f'border-radius:0 8px 8px 0;box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
                f'<div style="font-size:11px;font-weight:700;color:{c};margin-bottom:5px;">{label}</div>'
                f'<div style="font-size:13px;color:#444;font-style:italic;line-height:1.6;">"{regret}"</div>'
                f'</div>'
            )

    regrets_section = (
        f'<div>'
        f'<h4 style="color:#333;font-size:14px;margin:0 0 12px 0;font-weight:700;">💔 Biggest Regrets</h4>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">{regret_cards}</div>'
        f'</div>'
    ) if regret_cards else ""

    return table + regrets_section


def tea_clash_card_html(speaker, listener, speaker_age, envy, relief, warning, speaker_key):
    c = PERSONA_COLORS.get(speaker_key, "#888")
    slot_items = [
        ("❤️", "ENVY",    envy,    "#fff1f2", "#881337"),
        ("😌", "RELIEF",  relief,  "#f0fdf4", "#14532d"),
        ("⚠️", "WARNING", warning, "#fffbeb", "#78350f"),
    ]
    slots = "".join(
        f'<div style="padding:12px 14px;background:{bg};border-radius:8px;">'
        f'<div style="font-size:10px;font-weight:700;color:{fg};letter-spacing:1px;margin-bottom:5px;">{icon} {label}</div>'
        f'<div style="font-size:13px;color:#333;line-height:1.6;">"{content}"</div>'
        f'</div>'
        for icon, label, content, bg, fg in slot_items
    )
    return (
        f'<div style="border:1.5px solid {c}40;border-radius:12px;padding:14px 16px;'
        f'background:white;margin:8px 0;box-shadow:0 1px 6px rgba(0,0,0,0.04);">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">'
        f'<span style="font-size:13px;color:{c};font-weight:700;">{speaker}</span>'
        f'<span style="color:#ddd;font-size:16px;">→</span>'
        f'<span style="font-size:13px;color:#555;">{listener}</span>'
        f'<span style="font-size:11px;color:#bbb;margin-left:auto;">age {speaker_age}</span>'
        f'</div>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">{slots}</div>'
        f'</div>'
    )


def tea_quote_card_html(speaker, listener, speaker_age, message, direction, speaker_key, streaming=False):
    c = PERSONA_COLORS.get(speaker_key, "#888")
    icon = "⏩" if direction == "forward" else "⏪"
    cursor = '<span style="animation:blink 1s infinite;color:#999;">▌</span>' if streaming else ""
    return (
        f'<div style="border-left:3px solid {c};padding:12px 16px;margin:8px 0;'
        f'background:#fafafa;border-radius:0 8px 8px 0;">'
        f'<div style="font-size:11px;color:#aaa;margin-bottom:6px;">'
        f'{icon} <b style="color:{c};">{speaker}</b> (age {speaker_age}) → {listener}</div>'
        f'<div style="font-size:13px;color:#333;line-height:1.75;font-style:italic;">"{md_to_html(message)}"{cursor}</div>'
        f'</div>'
    )


# ── Background generation ─────────────────────────────────────────────────────

def _generate_full_one(key, age, years):
    """Outline → Story → Score → Regret in one background thread."""
    # Outline
    try:
        outline = _persona_agent[key].generate_outline(years)
        _outline_data[key] = outline
    except Exception as e:
        _outline_data[key] = {
            "city": "Unknown", "career_title": "Unknown", "marital_status": "Unknown",
            "children": "Unknown", "financial_status": "Unknown",
            "key_life_event": f"Error: {e}", "narrative": "",
        }
    finally:
        _outline_done[key].set()

    # One-liner — fast, only needs outline
    _oneliner_data[key] = _get_one_liner(key, _outline_data.get(key, {}))
    _oneliner_done[key].set()

    # Story (non-streaming, for scoring)
    try:
        story = _persona_agent[key].generate_story_from_outline(years, _outline_data[key])
        _persona_story[key] = story
        _state.setdefault("stories", {})[PERSONAS[key]["label"]] = story
    except Exception as e:
        _persona_story[key] = f"[Error: {e}]"
        _score_done[key].set()
        return

    # Score
    try:
        scores = score_life(PERSONAS[key]["label"], _persona_story[key])
        _score_data[key] = scores
        try:
            wandb.log({f"score_{key}_{m}": v for m, v in scores.items()})
        except Exception:
            pass
    except Exception:
        _score_data[key] = {d.lower(): 5 for d in DIMENSIONS}

    # Regret quote
    _regret_data[key] = _get_regret_quote(PERSONAS[key]["label"], _persona_story[key])

    _score_done[key].set()
    if all(_score_done[k].is_set() for k in PERSONA_KEYS):
        _all_scored.set()


def _start_background_generation(enriched_situation, age, years):
    from orchestrator import LifeOrchestrator
    agents = {k: LifeAgent(k, enriched_situation, age) for k in PERSONA_KEYS}
    _persona_agent.update(agents)

    orchestrator = LifeOrchestrator(enriched_situation, age, years)

    def _orchestrated_run():
        global _trace_t0
        _trace_t0 = time.time()
        _trace_events.clear()

        # Phase 1: orchestrator coordinates all 4 outlines in parallel
        t0 = time.time()
        outlines = orchestrator.orchestrate_outlines(agents)
        _record("orchestrate_outlines", "orchestrator", "outline", t0, time.time())
        for k, outline in outlines.items():
            _outline_data[k] = outline
            _oneliner_data[k] = _get_one_liner(k, outline)
            _oneliner_done[k].set()
            _outline_done[k].set()

        # Phase 2: generate stories (each in its own thread for streaming support)
        def _gen_story(k):
            t0 = time.time()
            try:
                story = agents[k].generate_story_from_outline(years, _outline_data[k])
                _persona_story[k] = story
                _state.setdefault("stories", {})[PERSONAS[k]["label"]] = story
            except Exception as e:
                _persona_story[k] = f"[Error: {e}]"
                _score_done[k].set()
            _record("generate_story", k, "story", t0, time.time())

        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(_gen_story, PERSONA_KEYS))

        # Phase 3: orchestrator coordinates all 4 scores in parallel
        t0 = time.time()
        scores = orchestrator.orchestrate_scores(agents, _persona_story)
        _record("orchestrate_scores", "orchestrator", "score", t0, time.time())
        for k, s in scores.items():
            _score_data[k] = s
            try:
                wandb.log({f"score_{k}_{m}": v for m, v in s.items()})
            except Exception:
                pass
            _regret_data[k] = _get_regret_quote(PERSONAS[k]["label"], _persona_story.get(k, ""))
            _score_done[k].set()

        if all(_score_done[k].is_set() for k in PERSONA_KEYS):
            _all_scored.set()

        def _run_eval():
            try:
                results = evaluate_stories(
                    _persona_story, _outline_data, PERSONAS, _state.get("situation", "")
                )
                _eval_data.update(results)
            except Exception:
                pass
            finally:
                _eval_done.set()

        threading.Thread(target=_run_eval, daemon=True).start()

    threading.Thread(target=_orchestrated_run, daemon=True).start()


# ── Stage handlers ────────────────────────────────────────────────────────────

def show_questions():
    return gr.update(visible=False), gr.update(visible=True)


def reveal_and_start(situation, age, years_val, ans1, ans2, ans3, ans4):
    global _state
    _state = {}
    _all_scored.clear()
    for e in _outline_done.values():
        e.clear()
    for e in _score_done.values():
        e.clear()
    _outline_data.clear()
    _persona_story.clear()
    _persona_agent.clear()
    _score_data.clear()
    _regret_data.clear()
    _oneliner_data.clear()
    for e in _oneliner_done.values():
        e.clear()
    _eval_data.clear()
    _eval_done.clear()

    age, years = int(age), int(years_val)
    _state.update({"age": age, "years": years, "situation": situation})

    user_ctx = ". ".join(filter(None, [
        f"Location: {ans1}" if ans1 else "",
        f"Relationship: {ans2}" if ans2 else "",
        f"Career: {ans3}" if ans3 else "",
        f"Priority: {ans4}" if ans4 else "",
    ]))
    enriched = f"{situation}\n\nUser's self-reported vision: {user_ctx}." if user_ctx else situation
    _state["enriched_situation"] = enriched

    try:
        weave.init(WEAVE_PROJECT)
        wandb.init(project=WANDB_PROJECT, config={"situation": situation, "age": age, "years": years})
    except Exception:
        pass

    threading.Thread(
        target=_start_background_generation, args=(enriched, age, years), daemon=True
    ).start()

    # Force-initialize all section DOMs by including their visibility state in this return.
    # _switch_section is pure Python (<1ms), included here so Gradio renders all
    # section components on first reveal instead of lazily on first nav click.
    section_inits = _switch_section("stories")
    return (
        gr.update(visible=False),  # questions
        gr.update(visible=True),   # main section
        "⏳ Generating 4 parallel lives in background — pick a story to read while it runs.",
        *section_inits,
    )


# ── Snapshot auto-loader (triggered via .then() chaining) ────────────────────

def load_snapshots():
    """Stream snapshot cards one by one as each outline + one-liner completes."""
    ready = []
    for k in PERSONA_KEYS:
        _oneliner_done[k].wait(timeout=45)
        ready.append(k)
        yield snapshots_grid_html(ready)
    # Final pass: re-render once scores arrive (may already be set)
    _all_scored.wait(timeout=90)
    yield snapshots_grid_html(PERSONA_KEYS)


# ── Persona story (typewriter from cache or stream from LLM) ─────────────────

def pick_persona(key):
    c = PERSONA_COLORS[key]
    p = PERSONAS[key]
    years = _state.get("years", 10)

    yield f'<div style="text-align:center;padding:24px;color:{c};">' \
          f'<b style="font-size:14px;">⏳ Preparing {p["label"]}…</b></div>'

    _outline_done[key].wait(timeout=60)

    if key in _persona_story:
        # Typewriter from cache
        story = _persona_story[key]
        for i in range(0, len(story), 18):
            yield story_card_html(key, story[:i + 18], streaming=True)
            time.sleep(0.012)
        accumulated = story
    else:
        # Stream from LLM
        accumulated = ""
        try:
            for token in _persona_agent[key].generate_story_from_outline_streaming(
                years, _outline_data.get(key, {})
            ):
                accumulated += token
                yield story_card_html(key, accumulated, streaming=True)
        except Exception as e:
            accumulated = f"[Error: {e}]"
        _persona_story[key] = accumulated
        _state.setdefault("stories", {})[p["label"]] = accumulated
        # Score in background
        def _bg_score():
            try:
                _score_data[key] = score_life(p["label"], accumulated)
            except Exception:
                _score_data[key] = {d.lower(): 5 for d in DIMENSIONS}
            _regret_data[key] = _get_regret_quote(p["label"], accumulated)
            _score_done[key].set()
            if all(_score_done[k].is_set() for k in PERSONA_KEYS):
                _all_scored.set()
        threading.Thread(target=_bg_score, daemon=True).start()

    try:
        wandb.log({f"story_{key}": accumulated})
    except Exception:
        pass

    yield story_card_html(key, accumulated, streaming=False)


# ── Dashboard ─────────────────────────────────────────────────────────────────

def load_dashboard():
    if not _persona_agent:
        yield "Start a session first.", gr.update(visible=False), "<div style='min-height:400px;'></div>"
        return
    yield "⏳ Waiting for all 4 lives to score (~20–30s)…", gr.update(visible=False), "<div style='min-height:400px;'></div>"
    _all_scored.wait(timeout=180)
    all_scores = {
        PERSONAS[k]["label"]: _score_data.get(k, {d.lower(): 5 for d in DIMENSIONS})
        for k in PERSONA_KEYS
    }
    regrets = {PERSONAS[k]["label"]: _regret_data.get(k, "") for k in PERSONA_KEYS}
    yield "✅ All 4 lives scored.", gr.update(visible=True, value=build_radar_chart(all_scores)), comparison_dashboard_html(all_scores, regrets)


# ── Tea House ─────────────────────────────────────────────────────────────────

def _ensure_all_stories():
    missing = [k for k in PERSONA_KEYS if k not in _persona_story]
    if not missing:
        return
    for k in missing:
        _outline_done[k].wait(timeout=60)
    def _gen(k):
        try:
            story = _persona_agent[k].generate_story_from_outline(
                _state["years"], _outline_data.get(k, {})
            )
            _persona_story[k] = story
            _state.setdefault("stories", {})[PERSONAS[k]["label"]] = story
        except Exception as e:
            _persona_story[k] = f"[Error: {e}]"
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(_gen, missing))


def _tea_stream_card(html_so_far, key, listener, age, message, streaming, direction):
    """Render accumulated html + one live card at the bottom."""
    card = tea_quote_card_html(
        _persona_agent[key].label, listener, age, message, direction, key, streaming=streaming
    )
    return html_so_far + card


@weave.op()
def _log_tea_round(round_num: int, situation: str, age: int, years: int):
    """Weave trace entry point for Tea House rounds."""
    return {"round": round_num, "situation": situation, "age": age, "years": years}


def run_tea_round(round_num):
    if not _persona_agent:
        yield "Start a session first.", ""
        return
    _log_tea_round(round_num, _state.get("situation", ""), _state.get("age", 0), _state.get("years", 0))

    yield "⏳ Ensuring all stories ready…", ""
    _ensure_all_stories()

    stories = {PERSONAS[k]["label"]: _persona_story[k] for k in PERSONA_KEYS}
    age, years = _state["age"], _state["years"]
    future_age = age + years
    done_html = ""  # finalized cards accumulate here

    try:
        if round_num == 1:
            header = '<h3 style="color:#3b82f6;margin:0 0 14px 0;">⏩ Junior looks Forward</h3>'
            done_html = header
            question = (
                f"Your {age}-year-old self asks: 'I'm at this crossroads — "
                f"what do you wish someone had told me before I chose?' "
                f"Answer directly. Honest, not reassuring. Under 60 words."
            )
            for k in PERSONA_KEYS:
                partial = ""
                for token in _persona_agent[k]._call_llm_streaming(question, max_tokens=150):
                    partial += token
                    yield f"💬 {PERSONAS[k]['label']}…", _tea_stream_card(done_html, k, f"Their {age}-year-old self", future_age, partial, True, "forward")
                done_html += tea_quote_card_html(_persona_agent[k].label, f"Their {age}-year-old self", future_age, partial, "forward", k)
            yield "✅ Round 1 ready.", done_html

        elif round_num == 2:
            header = '<h3 style="color:#ef4444;margin:0 0 14px 0;">⚡ Seniors Clash</h3>'
            done_html = header
            pairs = [
                ("steady",   "maverick", "You hear The Maverick's story. A mix of envy and vindication."),
                ("maverick", "ghost",    "You hear The Ghost Path's story. Lucky — and guilty about it."),
                ("ghost",    "wildcard", "You hear The Wildcard's story. Was freedom always an option?"),
                ("wildcard", "steady",   "You hear The Steady One's story. Pity and respect, mixed."),
            ]
            for spk, tgt, ctx in pairs:
                tgt_label = PERSONAS[tgt]["label"]
                prompt = (
                    f"{ctx}\n\nTheir story: \"{stories.get(tgt_label, '')[:300]}...\"\n\n"
                    f"Respond with ONLY a JSON object (no markdown):\n"
                    f'{{"envy":"one thing you genuinely envy, under 20 words",'
                    f'"relief":"one thing you\'re relieved to have avoided, under 20 words",'
                    f'"warning":"one raw warning from your experience, under 20 words"}}'
                )
                # Stream the raw response, show a "thinking" card, then render formatted card
                raw = ""
                placeholder = (
                    f'<div style="border:1.5px solid {PERSONA_COLORS[spk]}40;border-radius:12px;'
                    f'padding:14px 16px;margin:8px 0;color:#aaa;font-size:13px;">'
                    f'<b style="color:{PERSONA_COLORS[spk]};">{PERSONAS[spk]["label"]}</b>'
                    f' → {tgt_label} &nbsp;<span style="animation:blink 1s infinite;">▌</span></div>'
                )
                yield f"💬 {PERSONAS[spk]['label']} → {tgt_label}…", done_html + placeholder
                for token in _persona_agent[spk]._call_llm_streaming(prompt, max_tokens=200):
                    raw += token
                try:
                    parsed = json.loads(raw.strip().replace("```json","").replace("```","").strip())
                except Exception:
                    parsed = {"envy": "…", "relief": "…", "warning": "…"}
                done_html += tea_clash_card_html(
                    _persona_agent[spk].label, tgt_label, future_age,
                    parsed.get("envy","…"), parsed.get("relief","…"), parsed.get("warning","…"), spk,
                )
                yield f"✅ {PERSONAS[spk]['label']} done.", done_html
            yield "✅ Round 2 ready.", done_html

        else:  # round 3
            header = f'<h3 style="color:#22c55e;margin:0 0 14px 0;">⏪ Seniors ({future_age}) look Backward</h3>'
            done_html = header
            prompt = (
                f"Write a short letter to your {age}-year-old self. "
                f"Not advice. The truth about what lies ahead. Two sentences. Make it land."
            )
            for k in PERSONA_KEYS:
                partial = ""
                for token in _persona_agent[k]._call_llm_streaming(prompt, max_tokens=120):
                    partial += token
                    yield f"✍️ {PERSONAS[k]['label']}…", _tea_stream_card(done_html, k, f"Their {age}-year-old self", future_age, partial, True, "backward")
                done_html += tea_quote_card_html(_persona_agent[k].label, f"Their {age}-year-old self", future_age, partial, "backward", k)
            yield "✅ Round 3 ready.", done_html

    except Exception as e:
        yield f"Error: {e}", done_html


# ── Synthesis ─────────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """You are an impartial life analyst and psychologist.
You have observed four parallel versions of the same person.
Evaluate honestly. Be specific, grounded in psychology. Do not moralize.
"""

def run_judge_ui():
    if not _persona_agent:
        yield "Start a session first.", ""
        return
    yield "⏳ Ensuring all stories ready…", ""
    _ensure_all_stories()
    stories = {PERSONAS[k]["label"]: _persona_story[k] for k in PERSONA_KEYS}
    stories_text = "\n\n".join(f"[{lbl}]: {story}" for lbl, story in stories.items())
    prompt = f"""Four parallel lives from the same starting point:

{stories_text}

Write a synthesis (under 250 words):
1. One sentence capturing the core trade-off each life represents
2. The one thing ALL four versions share (regret, desire, or fear)
3. What The Ghost Path reveals about luck vs. choice
4. What The Wildcard challenges about the original decision
5. One universal insight that only emerges when you see all four lives together

Every sentence must earn its place."""

    yield "✍️ Writing…", ""
    accumulated = ""
    try:
        for token in _stream_simple(prompt, system=JUDGE_SYSTEM, max_tokens=600):
            accumulated += token
            yield "✍️ Writing…", accumulated
        try:
            wandb.log({"synthesis": accumulated})
            wandb.finish()
        except Exception:
            pass
        yield "✅ Done.", accumulated
    except Exception as e:
        yield f"Error: {e}", str(e)


# ── Trace visualization ───────────────────────────────────────────────────────

def build_trace_chart():
    if not _trace_events:
        return go.Figure().update_layout(
            title="No trace data yet — run a session first.",
            height=300, paper_bgcolor="white"
        )

    fig = go.Figure()

    events = sorted(_trace_events, key=lambda e: e["start"])

    y_labels = []
    for e in events:
        if e["persona"] == "orchestrator":
            label = f"[{e['phase'].upper()}] orchestrator"
        else:
            label = f"[{e['phase'].upper()}] {PERSONAS[e['persona']]['label']}"
        y_labels.append(label)

    colors = []
    for e in events:
        if e["phase"] == "outline":
            colors.append("#818cf8")
        elif e["phase"] == "score":
            colors.append("#22c55e")
        else:
            colors.append(PERSONA_COLORS.get(e["persona"], "#888"))

    for i, (e, label, color) in enumerate(zip(events, y_labels, colors)):
        fig.add_trace(go.Bar(
            x=[e["duration"]],
            y=[label],
            base=[e["start"]],
            orientation="h",
            marker_color=color,
            text=f'{e["duration"]}s',
            textposition="inside",
            insidetextanchor="middle",
            showlegend=False,
            hovertemplate=f"<b>{label}</b><br>Start: {e['start']}s<br>Duration: {e['duration']}s<extra></extra>",
        ))

    max_end = max(e["end"] for e in events)
    fig.update_layout(
        barmode="overlay",
        xaxis=dict(title="Seconds from session start", range=[0, max_end * 1.05]),
        yaxis=dict(autorange="reversed"),
        height=max(300, len(events) * 48 + 80),
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
        margin=dict(l=20, r=20, t=40, b=40),
        title=dict(text="LLM Call Timeline", font=dict(size=14)),
    )
    return fig


def build_trace_table():
    if not _trace_events:
        return "<p style='color:#aaa;'>No data.</p>"
    rows = "".join(
        f'<tr style="border-bottom:1px solid #f0f0f0;">'
        f'<td style="padding:6px 12px;font-size:12px;color:#555;">{e["phase"].upper()}</td>'
        f'<td style="padding:6px 12px;font-size:12px;font-weight:600;">{PERSONAS[e["persona"]]["label"] if e["persona"] in PERSONAS else e["persona"]}</td>'
        f'<td style="padding:6px 12px;font-size:12px;">{e["name"]}</td>'
        f'<td style="padding:6px 12px;font-size:12px;color:#4A90D9;font-weight:700;">{e["duration"]}s</td>'
        f'<td style="padding:6px 12px;font-size:12px;color:#aaa;">{e["start"]}s → {e["end"]}s</td>'
        f'</tr>'
        for e in sorted(_trace_events, key=lambda e: e["start"])
    )
    return (
        f'<div style="overflow-x:auto;border:1px solid #eee;border-radius:8px;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="background:#f7f7f7;">'
        f'<th style="padding:6px 12px;font-size:11px;text-align:left;">Phase</th>'
        f'<th style="padding:6px 12px;font-size:11px;text-align:left;">Agent</th>'
        f'<th style="padding:6px 12px;font-size:11px;text-align:left;">Function</th>'
        f'<th style="padding:6px 12px;font-size:11px;text-align:left;">Duration</th>'
        f'<th style="padding:6px 12px;font-size:11px;text-align:left;">Timeline</th>'
        f'</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div>'
    )


EVAL_COLORS = {"consistency": "#4A90D9", "realism": "#22c55e", "divergence": "#f59e0b"}


def build_eval_html():
    if not _eval_data:
        return "<p style='color:#aaa;text-align:center;padding:24px;'>Evaluation running… check back in ~15s after generation completes.</p>"

    cards = ""
    for key in PERSONA_KEYS:
        if key not in _eval_data:
            continue
        c = PERSONA_COLORS[key]
        p = PERSONAS[key]
        evals = _eval_data[key]

        metrics = ""
        total = 0
        for dim in ["consistency", "realism", "divergence"]:
            ev = evals.get(dim, {})
            score = ev.get("score", 5)
            reason = ev.get("reason", "")
            total += score
            col = EVAL_COLORS[dim]
            bar_pct = int(score * 10)
            metrics += (
                f'<div style="margin:8px 0;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">'
                f'<span style="font-size:11px;font-weight:700;color:{col};text-transform:uppercase;letter-spacing:0.5px;">{dim}</span>'
                f'<span style="font-size:13px;font-weight:800;color:{col};">{score}/10</span>'
                f'</div>'
                f'<div style="height:4px;background:#eee;border-radius:2px;overflow:hidden;margin-bottom:4px;">'
                f'<div style="width:{bar_pct}%;height:100%;background:{col};border-radius:2px;"></div>'
                f'</div>'
                f'<div style="font-size:11px;color:#666;font-style:italic;line-height:1.4;">{reason}</div>'
                f'</div>'
            )
        avg = round(total / 3, 1)

        cards += (
            f'<div style="border:2px solid {c}30;border-radius:14px;padding:18px;'
            f'background:linear-gradient(135deg,{c}08,white);flex:0 0 calc(50% - 6px);box-sizing:border-box;">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px;">'
            f'<div style="color:{c};font-size:14px;font-weight:800;">{p["label"]}</div>'
            f'<div><span style="font-size:20px;font-weight:900;color:{c};">{avg}</span>'
            f'<span style="font-size:10px;color:#aaa;">/10</span></div>'
            f'</div>'
            f'{metrics}'
            f'</div>'
        )

    return f'<div style="display:flex;flex-wrap:wrap;gap:12px;">{cards}</div>'


def load_eval():
    _eval_done.wait(timeout=60)
    yield build_eval_html()


def load_traces():
    if not _trace_events:
        yield gr.update(value=go.Figure().update_layout(title="Run a session first.", height=250, paper_bgcolor="white")), "<p style='color:#aaa;'>No trace data yet.</p>"
        return
    yield gr.update(value=build_trace_chart()), build_trace_table()


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
footer { display:none !important; }
/* fixed layout — prevent width collapse */
.gradio-container { max-width:1100px !important; margin:0 auto !important; padding:0 24px !important; }
body { overflow-y: scroll !important; }
/* hide Gradio's empty Plot label badge */
.empty { display:none !important; }
.gap { gap:8px !important; }
.form { gap:8px !important; }
.year-btn  { border-radius:10px !important; font-size:13px !important; font-weight:600 !important; }
.chip-btn  { border-radius:20px !important; font-size:11px !important; padding:6px 12px !important;
             white-space:normal !important; word-break:break-word !important; text-align:center !important; line-height:1.4 !important; }
.gen-btn   { border-radius:12px !important; font-size:15px !important; font-weight:700 !important; }
.persona-btn { border-radius:14px !important; font-size:13px !important; font-weight:600 !important;
               min-height:64px !important; white-space:normal !important; }
.q-radio label { font-size:13px !important; }
/* nav pill styling */
#nav-row { gap:0 !important; border-bottom:2px solid #e5e7eb; margin-bottom:16px; }
#nav-row > div { flex:0 0 auto !important; }
.nav-pill { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
.nav-pill button { background:transparent !important; border:none !important; border-radius:0 !important;
  box-shadow:none !important; padding:10px 18px !important; font-size:14px !important;
  font-weight:500 !important; color:#888 !important; border-bottom:3px solid transparent !important;
  margin-bottom:-2px !important; transition:color 0.15s,border-color 0.15s !important;
  width:auto !important; min-width:0 !important; }
.nav-pill button:hover { color:#6366f1 !important; }
.nav-pill button.primary, .nav-pill button[class*="primary"] { color:#6366f1 !important;
  border-bottom-color:#6366f1 !important; font-weight:700 !important; }
"""

ALL_SECTIONS = ["stories", "dash", "tea", "synth", "insight", "traces"]


def _switch_section(active):
    """Return visibility updates for 6 sections + variant updates for 6 nav buttons."""
    sec_updates = [gr.update(visible=(s == active)) for s in ALL_SECTIONS]
    nav_updates = [gr.update(variant="primary" if s == active else "secondary") for s in ALL_SECTIONS]
    return sec_updates + nav_updates


META_HTML = """
<div style="text-align:center;padding:64px 40px;background:linear-gradient(135deg,#0f0f1a,#1a1a2e);
     border-radius:20px;margin:8px 0;">
  <p style="color:#818cf8;font-size:11px;letter-spacing:4px;margin:0 0 28px 0;text-transform:uppercase;">
    The Core Insight
  </p>
  <h2 style="color:white;font-size:2.2em;font-weight:900;line-height:1.25;margin:0 0 24px 0;
       max-width:560px;margin-left:auto;margin-right:auto;letter-spacing:-1px;">
    The moment you choose,<br>you lose the ability to see<br>what you've sacrificed.
  </h2>
  <div style="width:36px;height:2px;background:#818cf8;margin:0 auto 24px auto;"></div>
  <p style="color:#a5b4fc;font-size:1.2em;line-height:1.9;max-width:420px;
      margin-left:auto;margin-right:auto;font-weight:500;">
    Regret is evidence<br>of a real choice.
  </p>
</div>
"""


# ── Layout ────────────────────────────────────────────────────────────────────

with gr.Blocks(title="Parallel Lives", css=CSS) as demo:

    # Hero
    gr.HTML("""
    <div style="padding:40px 0 24px 0;">
      <h1 style="font-size:3em;font-weight:900;margin:0 0 8px 0;letter-spacing:-1.5px;line-height:1.1;">
        My Parallel Lives
      </h1>
      <p style="color:#888;font-size:1.05em;margin:0;">
        Let your other lives speak.
      </p>
    </div>
    """)

    # ── SECTION 1: Input ──────────────────────────────────────────────────────
    with gr.Column(visible=True) as input_section:
        with gr.Row(equal_height=False):
            with gr.Column(scale=5):
                situation_input = gr.Textbox(
                    label="✏️ What decision are you facing?",
                    placeholder="e.g. Age 25 — should I join a big tech company or an early-stage startup?",
                    lines=4,
                )
                with gr.Row():
                    chip_btns = [gr.Button(c, size="sm", elem_classes=["chip-btn"]) for c in CHIPS]
            with gr.Column(scale=3):
                age_input = gr.Number(label="Current age", value=25, precision=0)
                gr.HTML('<p style="font-weight:600;font-size:13px;color:#818cf8;margin:8px 0 4px 0;">⏱ Jump how many years?</p>')
                years_state = gr.State(10)
                years_disp  = gr.HTML(value=years_display_html(10))
                with gr.Row():
                    year_btns = [
                        gr.Button(f"{'+' if y>0 else ''}{y}y", size="sm", elem_classes=["year-btn"])
                        for y in YEAR_OPTIONS
                    ]
        run_btn = gr.Button("Set the Scene →", variant="primary", size="lg", elem_classes=["gen-btn"])

    # ── SECTION 2: Questions ──────────────────────────────────────────────────
    with gr.Column(visible=False) as question_section:
        gr.HTML("""
        <div style="display:flex;align-items:center;justify-content:space-between;
             padding:12px 20px;background:linear-gradient(135deg,#f0f4ff,#fff);
             border-radius:12px;margin-bottom:12px;border:1.5px solid #e0e7ff;">
          <div>
            <span style="font-size:11px;color:#818cf8;font-weight:700;letter-spacing:2px;">STEP 2 / 2 &nbsp;·&nbsp;</span>
            <span style="font-size:15px;font-weight:800;color:#1e1b4b;">Shape your parallel lives</span>
          </div>
          <span style="color:#aaa;font-size:12px;">30 seconds</span>
        </div>
        """)
        with gr.Row():
            with gr.Column():
                q1 = gr.Radio(
                    choices=["Same city as now", "Different city in my country", "Living abroad", "Open / don't know"],
                    label="📍 Where do you picture yourself living?", elem_classes=["q-radio"],
                )
                q3 = gr.Radio(
                    choices=["Steady climb in same field", "Major pivot to something new", "Running my own business", "Still figuring it out"],
                    label="💼 How do you see your career unfolding?", elem_classes=["q-radio"],
                )
            with gr.Column():
                q2 = gr.Radio(
                    choices=["Single & independent", "Serious relationship, no kids", "Married with children", "Divorced / complicated"],
                    label="💑 What does your relationship life look like?", elem_classes=["q-radio"],
                )
                q4 = gr.Radio(
                    choices=["Financial security & stability", "Freedom & personal growth", "Family & deep relationships", "Impact — work that truly matters"],
                    label="🎯 What matters most to you?", elem_classes=["q-radio"],
                )
        with gr.Row():
            back_btn1  = gr.Button("← Back", size="sm", variant="secondary")
            reveal_btn = gr.Button("✨ Generate My Parallel Lives →", variant="primary", size="lg", elem_classes=["gen-btn"])

    # ── SECTION 3: Main Experience ────────────────────────────────────────────
    with gr.Column(visible=False) as main_section:
        gen_status = gr.Markdown("")

        # ── Navigation row (real Gradio buttons, styled as pills) ───────────────
        with gr.Row(elem_id="nav-row"):
            nav_btn_stories = gr.Button("📖 Explore Stories", variant="primary",   elem_classes=["nav-pill"])
            nav_btn_dash    = gr.Button("📊 Life Dashboard",  variant="secondary", elem_classes=["nav-pill"])
            nav_btn_tea     = gr.Button("☕ Tea House",        variant="secondary", elem_classes=["nav-pill"])
            nav_btn_synth   = gr.Button("🧠 Synthesis",       variant="secondary", elem_classes=["nav-pill"])
            nav_btn_insight = gr.Button("✨ The Insight",     variant="secondary", elem_classes=["nav-pill"])
            nav_btn_traces  = gr.Button("🔍 Traces",          variant="secondary", elem_classes=["nav-pill"])

        # ── Section: Explore Stories (visible by default) ────────────────────
        with gr.Column(visible=True) as sec_stories:
            snapshot_html = gr.HTML(
                value='<p style="color:#aaa;text-align:center;padding:40px 0;">Generating your parallel lives…</p>'
            )
            gr.HTML('<p style="color:#aaa;font-size:12px;margin:4px 0 8px 0;">↓ Click to read a full story</p>')
            with gr.Row():
                btn_steady   = gr.Button("🔵 Read The Steady One's Story →",  elem_classes=["persona-btn"])
                btn_maverick = gr.Button("🔴 Read The Maverick's Story →",     elem_classes=["persona-btn"])
                btn_ghost    = gr.Button("🟣 Read The Ghost Path's Story →",   elem_classes=["persona-btn"])
                btn_wildcard = gr.Button("🟡 Read The Wildcard's Story →",     elem_classes=["persona-btn"])
            persona_btns = [btn_steady, btn_maverick, btn_ghost, btn_wildcard]
            story_html = gr.HTML(value="<div style='min-height:120px;'></div>")

        # ── Section: Life Dashboard ───────────────────────────────────────────
        with gr.Column(visible=False) as sec_dash:
            gr.HTML('<p style="color:#888;font-size:13px;margin:0 0 12px 0;">Scoring runs in background. Hit <b>Load</b> any time — instant if stories are already done.</p>')
            dash_btn    = gr.Button("🔄 Load Dashboard", variant="secondary", size="sm")
            dash_status = gr.Markdown("")
            radar_out   = gr.Plot(visible=False)
            dash_html   = gr.HTML(value="<div style='min-height:400px;'></div>")

        # ── Section: Tea House ────────────────────────────────────────────────
        with gr.Column(visible=False) as sec_tea:
            gr.HTML("""
            <div style="background:linear-gradient(135deg,#0f0f1a,#1a1a2e);border-radius:12px;
                 padding:16px 20px;margin-bottom:14px;">
              <h3 style="color:white;margin:0 0 4px 0;font-size:1.1em;">The Time-Space Tea House</h3>
              <p style="color:#a5b4fc;font-size:13px;margin:0;">Different versions of you, talking across time.</p>
            </div>
            """)
            with gr.Row():
                tea_r1 = gr.Button("⏩ Round 1: Junior looks forward", variant="secondary", size="sm")
                tea_r2 = gr.Button("⚡ Round 2: Seniors clash",        variant="secondary", size="sm")
                tea_r3 = gr.Button("⏪ Round 3: Seniors look back",    variant="secondary", size="sm")
            tea_status = gr.Markdown("")
            tea_out    = gr.HTML(value="<div style='min-height:400px;'></div>")

        # ── Section: Synthesis ────────────────────────────────────────────────
        with gr.Column(visible=False) as sec_synth:
            gr.HTML('<p style="color:#888;font-size:13px;margin:0 0 12px 0;">Judge agent reads all 4 lives and finds what they share.</p>')
            judge_btn     = gr.Button("⚖️ Run Final Synthesis →", variant="secondary")
            judge_status  = gr.Markdown("")
            synthesis_out = gr.Markdown(value="<div style='min-height:400px;'></div>")

        # ── Section: The Insight ──────────────────────────────────────────────
        with gr.Column(visible=False) as sec_insight:
            gr.HTML(META_HTML)

        # ── Section: Traces ───────────────────────────────────────────────────
        with gr.Column(visible=False) as sec_traces:
            gr.HTML('<p style="color:#888;font-size:13px;margin:0 0 12px 0;">LLM call timeline for the current session.</p>')
            traces_btn   = gr.Button("🔄 Refresh", variant="secondary", size="sm")
            traces_chart = gr.Plot(visible=True)
            traces_table = gr.HTML(value="<div style='min-height:200px;'></div>")
            gr.HTML('<hr style="margin:20px 0;border:none;border-top:1px solid #eee;">')
            gr.HTML('<h4 style="color:#333;font-size:14px;margin:0 0 12px 0;font-weight:700;">📊 Story Quality Evaluation (LLM-as-Judge)</h4>')
            eval_html = gr.HTML(value="<p style='color:#aaa;'>Loads after generation completes.</p>")

        gr.Button("← Start Over", size="sm", variant="secondary").click(
            fn=lambda: (
                gr.update(visible=True), gr.update(visible=False), gr.update(visible=False),
                '<p style="color:#aaa;text-align:center;padding:40px 0;">Generating your parallel lives…</p>',
                "<div style='min-height:120px;'></div>",
            ),
            outputs=[input_section, question_section, main_section, snapshot_html, story_html],
            scroll_to_output=False,
        )

    # ── Wiring ────────────────────────────────────────────────────────────────

    for btn, yval in zip(year_btns, YEAR_OPTIONS):
        btn.click(fn=lambda v=yval: (v, years_display_html(v)), outputs=[years_state, years_disp])
    for btn, text in zip(chip_btns, CHIPS):
        btn.click(fn=lambda t=text: t, outputs=situation_input)

    run_btn.click(fn=show_questions, outputs=[input_section, question_section])
    back_btn1.click(
        fn=lambda: (gr.update(visible=True), gr.update(visible=False)),
        outputs=[input_section, question_section],
    )
    # Auto-trigger snapshot loading after generation starts (no scroll on .then)
    reveal_btn.click(
        fn=reveal_and_start,
        inputs=[situation_input, age_input, years_state, q1, q2, q3, q4],
        outputs=[question_section, main_section, gen_status] + _all_secs + _all_navs,
        scroll_to_output=False,
    ).then(
        fn=load_snapshots,
        outputs=[snapshot_html],
        scroll_to_output=False,
    )

    # Navigation pill wiring — outputs: 6 sections + 6 nav buttons
    _all_secs = [sec_stories, sec_dash, sec_tea, sec_synth, sec_insight, sec_traces]
    _all_navs = [nav_btn_stories, nav_btn_dash, nav_btn_tea, nav_btn_synth, nav_btn_insight, nav_btn_traces]
    for btn, name in [
        (nav_btn_stories, "stories"),
        (nav_btn_insight, "insight"),
    ]:
        btn.click(fn=partial(_switch_section, name), outputs=_all_secs + _all_navs, scroll_to_output=False)

    # Dashboard nav: switch section then auto-load
    nav_btn_dash.click(
        fn=partial(_switch_section, "dash"), outputs=_all_secs + _all_navs, scroll_to_output=False,
    ).then(
        fn=load_dashboard, outputs=[dash_status, radar_out, dash_html], scroll_to_output=False,
    )

    nav_btn_tea.click(
        fn=partial(_switch_section, "tea"), outputs=_all_secs + _all_navs, scroll_to_output=False,
    )

    nav_btn_synth.click(
        fn=partial(_switch_section, "synth"), outputs=_all_secs + _all_navs, scroll_to_output=False,
    )

    # Traces nav: switch section then auto-load traces
    nav_btn_traces.click(
        fn=partial(_switch_section, "traces"), outputs=_all_secs + _all_navs, scroll_to_output=False,
    ).then(fn=load_traces, outputs=[traces_chart, traces_table], scroll_to_output=False
    ).then(fn=load_eval, outputs=[eval_html], scroll_to_output=False)

    traces_btn.click(fn=load_traces, outputs=[traces_chart, traces_table], scroll_to_output=False
    ).then(fn=load_eval, outputs=[eval_html], scroll_to_output=False)

    dash_btn.click(fn=load_dashboard, outputs=[dash_status, radar_out, dash_html], scroll_to_output=False)

    for btn, key in [
        (btn_steady,   "steady"),
        (btn_maverick, "maverick"),
        (btn_ghost,    "ghost"),
        (btn_wildcard, "wildcard"),
    ]:
        btn.click(
            fn=partial(pick_persona, key),
            outputs=[story_html],
            scroll_to_output=False,
        )

    tea_r1.click(
        fn=partial(run_tea_round, 1), outputs=[tea_status, tea_out], scroll_to_output=False,
    ).then(
        fn=partial(run_tea_round, 2), outputs=[tea_status, tea_out], scroll_to_output=False,
    ).then(
        fn=partial(run_tea_round, 3), outputs=[tea_status, tea_out], scroll_to_output=False,
    )
    tea_r2.click(fn=partial(run_tea_round, 2), outputs=[tea_status, tea_out], scroll_to_output=False)
    tea_r3.click(fn=partial(run_tea_round, 3), outputs=[tea_status, tea_out], scroll_to_output=False)

    judge_btn.click(fn=run_judge_ui, outputs=[judge_status, synthesis_out], scroll_to_output=False)


if __name__ == "__main__":
    demo.launch(share=False, css=CSS, theme=gr.themes.Soft())
