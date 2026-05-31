"""
Judge agent: evaluates all parallel lives on 5 life dimensions + produces synthesis.
"""
import os
import weave
import anthropic
import wandb

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"


def _call(system: str, prompt: str, max_tokens: int = 300) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text

JUDGE_SYSTEM = """You are an impartial life analyst and psychologist.
You have observed four parallel versions of the same person.
Evaluate each life honestly. Be specific, grounded in psychology and statistics. Do not moralize.
"""

DIMENSIONS = ["WEALTH", "HAPPINESS", "STRESS", "HEALTH", "FULFILLMENT"]


@weave.op()
def score_life(persona_label: str, story: str) -> dict:
    prompt = f"""Evaluate this life story for {persona_label}:

\"{story}\"

Score each dimension 1-10 based on what this life story implies. Be realistic, not generous.
- WEALTH: financial security, income trajectory, assets
- HAPPINESS: day-to-day emotional wellbeing, relationships, life satisfaction
- STRESS: inverse of chronic stress and anxiety (10 = very low stress, 1 = burnout)
- HEALTH: physical and mental health outcomes implied by this lifestyle
- FULFILLMENT: sense of meaning, purpose, and personal growth

Respond in EXACTLY this format (one per line, nothing else):
WEALTH: <score>
HAPPINESS: <score>
STRESS: <score>
HEALTH: <score>
FULFILLMENT: <score>
"""
    raw = _call(JUDGE_SYSTEM, prompt, max_tokens=200)
    scores = {}
    for line in raw.strip().split("\n"):
        for dim in DIMENSIONS:
            if line.strip().startswith(dim + ":"):
                try:
                    scores[dim.lower()] = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    scores[dim.lower()] = 5
    # fill any missing dims with 5
    for dim in DIMENSIONS:
        scores.setdefault(dim.lower(), 5)
    return scores


@weave.op()
def final_synthesis(all_stories: dict, all_dialogues: list, all_reflections: dict) -> str:
    stories_text = "\n\n".join(f"[{label}]: {story}" for label, story in all_stories.items())
    dialogues_text = "\n".join(f"{s} → {t}: {m}" for s, t, m in all_dialogues)
    reflections_text = "\n".join(f"[{label}]: {r}" for label, r in all_reflections.items())

    prompt = f"""You have observed four parallel lives, their dialogues across time, and their final letters.

=== LIFE STORIES ===
{stories_text}

=== CROSS-LIFE DIALOGUES ===
{dialogues_text}

=== LETTERS TO THEIR YOUNGER SELF ===
{reflections_text}

Produce a final synthesis (in English, for a demo presentation):
1. One sentence capturing the core trade-off each life represents
2. The one thing ALL four versions share in common (regret, desire, or fear)
3. What The Ghost Path reveals about the role of luck vs. choice
4. What The Wildcard challenges about how we frame the original decision
5. One universal insight about decision-making that only emerges when you see all four lives together

Under 300 words. Make every sentence earn its place.
"""
    return _call(JUDGE_SYSTEM, prompt, max_tokens=1200)


def log_scores_to_wandb(all_scores: dict):
    columns = ["persona"] + [d.lower() for d in DIMENSIONS] + ["average"]
    table = wandb.Table(columns=columns)
    for persona_label, scores in all_scores.items():
        avg = round(sum(scores.values()) / len(scores), 1) if scores else 0
        table.add_data(persona_label, *[scores.get(d.lower(), 0) for d in DIMENSIONS], avg)
    wandb.log({"life_quality_scores": table})
