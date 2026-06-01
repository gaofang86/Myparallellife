"""
LLM-as-judge evaluation for generated life stories.
Three scorers: consistency, realism, divergence.
All decorated with @weave.op() for Weave tracing.
"""
import os
import json
import anthropic
import weave

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"

EVAL_SYSTEM = [
    {
        "type": "text",
        "text": (
            "You are an impartial story quality evaluator. "
            "Score honestly on a 1-10 scale. Be specific. Be brief. No flattery."
        ),
        "cache_control": {"type": "ephemeral"},
    }
]


def _llm_json(prompt: str, max_tokens: int = 120) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=EVAL_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"score": 5, "reason": raw[:80]}


@weave.op()
def score_consistency(persona_label: str, outline: dict, story: str) -> dict:
    """Does the story match the outline facts? Score 1-10."""
    outline_str = ", ".join(f"{k}: {v}" for k, v in outline.items() if k != "narrative")
    prompt = (
        f"Life outline for {persona_label}: {outline_str}\n\n"
        f"Story: \"{story[:600]}\"\n\n"
        f"Does the story match the outline facts (city, career, family, events)? "
        f"Respond ONLY with JSON: {{\"score\": <1-10>, \"reason\": \"<one sentence>\"}}"
    )
    return _llm_json(prompt)


@weave.op()
def score_realism(persona_label: str, tagline: str, situation: str, story: str) -> dict:
    """Is the story outcome realistic for this persona's archetype? Score 1-10."""
    prompt = (
        f"Persona: {persona_label} — \"{tagline}\"\n"
        f"Original decision: {situation}\n\n"
        f"Story: \"{story[:600]}\"\n\n"
        f"Is this outcome statistically and psychologically realistic for someone "
        f"who made this choice? Consider real-world base rates. "
        f"Respond ONLY with JSON: {{\"score\": <1-10>, \"reason\": \"<one sentence>\"}}"
    )
    return _llm_json(prompt)


@weave.op()
def score_divergence(persona_label: str, story: str, other_stories_summary: str) -> dict:
    """How distinct is this story from the other 3 personas? Score 1-10."""
    prompt = (
        f"Story for {persona_label}: \"{story[:400]}\"\n\n"
        f"The other 3 lives in brief: {other_stories_summary[:400]}\n\n"
        f"How distinct and differentiated is this story? "
        f"10 = completely unique voice and outcome, 1 = basically the same as the others. "
        f"Respond ONLY with JSON: {{\"score\": <1-10>, \"reason\": \"<one sentence>\"}}"
    )
    return _llm_json(prompt)


def evaluate_stories(stories: dict, outlines: dict, personas: dict, situation: str) -> dict:
    """
    Run all 3 scorers on all 4 stories.
    Returns: {persona_key: {consistency: {score, reason}, realism: ..., divergence: ...}}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {k: {} for k in stories}

    def run_scorer(key, scorer_name, fn, *args):
        try:
            return key, scorer_name, fn(*args)
        except Exception as e:
            return key, scorer_name, {"score": 5, "reason": str(e)[:60]}

    tasks = []
    persona_keys = list(stories.keys())
    for key in persona_keys:
        story = stories.get(key, "")
        outline = outlines.get(key, {})
        p = personas[key]
        others = "; ".join(
            f"{personas[k]['label']}: {stories[k][:120]}..."
            for k in persona_keys if k != key and stories.get(k)
        )
        tasks.append((key, "consistency", score_consistency, p["label"], outline, story))
        tasks.append((key, "realism", score_realism, p["label"], p["tagline"], situation, story))
        tasks.append((key, "divergence", score_divergence, p["label"], story, others))

    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = [ex.submit(run_scorer, *t) for t in tasks]
        for f in as_completed(futures):
            key, scorer_name, result = f.result()
            results[key][scorer_name] = result

    return results
