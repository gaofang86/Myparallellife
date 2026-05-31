"""
Orchestrator for Parallel Lives.
Stories run in parallel. Tea House dialogue runs in structured rounds.
Judge loads lazily on demand.
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
load_dotenv(override=True)
import weave
import wandb
from life_agent import LifeAgent
from judge import score_life, final_synthesis, log_scores_to_wandb
from personas import PERSONAS

WANDB_PROJECT = "parallel-lives"
WEAVE_PROJECT = "parallel-lives"
_wandb_initialized = False


def _ensure_wandb(situation, current_age, years_forward):
    global _wandb_initialized
    if not _wandb_initialized:
        weave.init(WEAVE_PROJECT)
        wandb.init(
            project=WANDB_PROJECT,
            config={"situation": situation, "current_age": current_age, "years_forward": years_forward},
        )
        _wandb_initialized = True


def _generate_one(key, situation, current_age, years_forward):
    agent = LifeAgent(key, situation, current_age)
    story = agent.generate_story(years_forward)
    return key, agent, story


def run_stories_parallel(situation: str, current_age: int, years_forward: int = 10):
    """Phase 1: All 4 agents generate their life story in parallel."""
    _ensure_wandb(situation, current_age, years_forward)

    agents = {}
    all_stories = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_generate_one, key, situation, current_age, years_forward): key
            for key in PERSONAS.keys()
        }
        for future in as_completed(futures):
            key, agent, story = future.result()
            agents[key] = agent
            all_stories[PERSONAS[key]["label"]] = story
            wandb.log({f"story_{key}": story})

    return agents, all_stories


def run_tea_house_dialogue(agents: dict, all_stories: dict, current_age: int, years_forward: int):
    """
    The Time-Space Tea House: 3 rounds of structured dialogue.

    Round 1 — FORWARD: Junior (age current_age) asks each Senior what they wish they'd known.
    Round 2 — CLASH: Each Senior reacts to one other Senior's story (envy, critique, regret).
    Round 3 — BACKWARD: Each Senior writes a letter back to their Junior self.
    """
    future_age = current_age + years_forward
    dialogue_rounds = []

    # ── Round 1: Junior looks FORWARD ──────────────────────────────────────
    # Simulated as: each Senior answers the question their Junior self would ask
    round1 = []
    junior_question = (
        f"Your {current_age}-year-old self is sitting across from you. "
        f"They ask: 'I'm standing at this crossroads right now. "
        f"What do you wish someone had told you before you made your choice?' "
        f"Answer them directly. Be honest, not reassuring. Under 80 words."
    )
    for key, agent in agents.items():
        answer = agent._call_llm(junior_question)
        round1.append({
            "type": "forward",
            "speaker": agent.label,
            "speaker_age": future_age,
            "listener": f"Your {current_age}-year-old self",
            "message": answer,
        })
        wandb.log({f"tea_round1_{key}": answer})

    dialogue_rounds.append({"round": 1, "title": f"Junior ({current_age}) looks Forward", "exchanges": round1})

    # ── Round 2: Seniors CLASH with each other ─────────────────────────────
    clash_pairs = [
        ("steady",   "maverick",  "You hear The Maverick's story. You feel a mix of envy and vindication."),
        ("maverick", "ghost",     "You hear The Ghost Path's story. You feel lucky — and guilty about feeling lucky."),
        ("ghost",    "wildcard",  "You hear The Wildcard's story. You wonder if freedom was always an option you dismissed too quickly."),
        ("wildcard", "steady",    "You hear The Steady One's story. You feel something between pity and respect."),
    ]
    round2 = []
    for speaker_key, target_key, context in clash_pairs:
        speaker = agents[speaker_key]
        target = agents[target_key]
        target_label = PERSONAS[target_key]["label"]
        target_story = all_stories[target_label]

        prompt = (
            f"{context}\n\n"
            f"Their story: \"{target_story[:400]}...\"\n\n"
            f"Speak directly to them — one honest thing you envy, "
            f"one honest thing you're relieved you avoided. "
            f"Raw and human. Under 100 words."
        )
        response = speaker._call_llm(prompt)
        round2.append({
            "type": "clash",
            "speaker": speaker.label,
            "speaker_age": future_age,
            "listener": target_label,
            "message": response,
        })
        wandb.log({f"tea_round2_{speaker_key}_to_{target_key}": response})

    dialogue_rounds.append({"round": 2, "title": "Tea House Clash — Seniors vs Seniors", "exchanges": round2})

    # ── Round 3: Seniors look BACKWARD ────────────────────────────────────
    round3 = []
    letter_prompt = (
        f"Write a short letter to your {current_age}-year-old self — the one who hasn't made the choice yet. "
        f"Not advice. Not a warning. Just the truth about what lies ahead on your path. "
        f"Two or three sentences. Make it land."
    )
    for key, agent in agents.items():
        letter = agent._call_llm(letter_prompt)
        round3.append({
            "type": "backward",
            "speaker": agent.label,
            "speaker_age": future_age,
            "listener": f"Their {current_age}-year-old self",
            "message": letter,
        })
        wandb.log({f"tea_round3_{key}": letter})

    dialogue_rounds.append({"round": 3, "title": f"Seniors ({future_age}) look Backward", "exchanges": round3})

    return dialogue_rounds


def run_judge(stories: dict, dialogue_rounds: list, current_age: int, years_forward: int):
    """Phase 4+5: Score each life and produce synthesis. Called lazily."""
    all_scores = {}
    for key in PERSONAS.keys():
        label = PERSONAS[key]["label"]
        scores = score_life(label, stories[label])
        all_scores[label] = scores
        for metric, val in scores.items():
            wandb.log({f"score_{key}_{metric}": val})

    log_scores_to_wandb(all_scores)

    # Flatten dialogues for judge
    flat_dialogues = [
        (ex["speaker"], ex["listener"], ex["message"])
        for rd in dialogue_rounds
        for ex in rd["exchanges"]
    ]
    reflections = {
        ex["speaker"]: ex["message"]
        for ex in dialogue_rounds[-1]["exchanges"]  # round 3 = letters back
    }

    synthesis = final_synthesis(stories, flat_dialogues, reflections)
    wandb.log({"judge_synthesis": synthesis})

    return {"scores": all_scores, "synthesis": synthesis}


if __name__ == "__main__":
    situation = "Age 25 — should I become an ML engineer or stay on the data science track?"
    current_age = 25
    years_forward = 10

    agents, stories = run_stories_parallel(situation, current_age, years_forward)

    for label, story in stories.items():
        print(f"\n[{label}]\n{story}\n")

    rounds = run_tea_house_dialogue(agents, stories, current_age, years_forward)
    for rd in rounds:
        print(f"\n=== {rd['title']} ===")
        for ex in rd["exchanges"]:
            print(f"\n{ex['speaker']} → {ex['listener']}:\n{ex['message']}")

    judge = run_judge(stories, rounds, current_age, years_forward)
    print("\n=== SYNTHESIS ===")
    print(judge["synthesis"])
    wandb.finish()
