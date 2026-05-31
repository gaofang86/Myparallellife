"""
A single parallel life agent — powered by Claude API.
"""
import os
import json
import weave
import anthropic
from personas import get_persona_prompt, PERSONAS

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"   # fast + cheap; swap to claude-sonnet-4-6 for higher quality


def _story_prompt(time_ctx, outline_str, age_vars, ending):
    return (
        f"{time_ctx}\nLife setting:\n{outline_str}\n\n"
        f"Context: {age_vars}\n\n"
        f"Tell your story in plain flowing prose. No markdown headers or bullet points. "
        f"Two to three paragraphs, under 250 words total. Be specific and vivid — "
        f"one concrete scene, one turning point, one emotional truth. {ending}"
    )


def get_age_appropriate_variables(current_age: int, years: int) -> str:
    target_age = current_age + years
    if years < 0:
        return "Focus on: early career anxiety, identity formation, relationship beginnings, dreams not yet tested"
    elif target_age < 30:
        return "Focus on: first job, romantic relationships, renting vs. buying, identity, grad school decisions"
    elif target_age < 40:
        return "Focus on: marriage/partnership, children or the decision not to have them, mortgage, career growth, side projects"
    elif target_age < 50:
        return "Focus on: career peak or plateau, teenage children, aging parents, net worth, mid-life reassessment"
    elif target_age < 60:
        return "Focus on: retirement planning, health declining, wealth inheritance planning, empty nest, legacy"
    else:
        return "Focus on: retirement, grandchildren, health management, life review, passing on wisdom"


class LifeAgent:
    def __init__(self, persona_key: str, user_situation: str, current_age: int):
        self.persona_key = persona_key
        self.persona = PERSONAS[persona_key]
        self.name = self.persona["name"]
        self.label = self.persona["label"]
        self.current_age = current_age
        self.conversation_history = []
        self.system_prompt = get_persona_prompt(persona_key, user_situation)
        self.story = None
        self.outline = None

    def _call_llm(self, user_message: str, max_tokens: int = 700) -> str:
        self.conversation_history.append({"role": "user", "content": user_message})
        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=self.conversation_history,
        )
        reply = response.content[0].text
        self.conversation_history.append({"role": "assistant", "content": reply})
        return reply

    def _call_llm_streaming(self, user_message: str, max_tokens: int = 800):
        """Stream tokens from Claude, yielding small chunks for UI effect."""
        self.conversation_history.append({"role": "user", "content": user_message})
        reply = ""
        with client.messages.stream(
            model=MODEL,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=self.conversation_history,
        ) as stream:
            for token in stream.text_stream:
                reply += token
                yield token
        self.conversation_history.append({"role": "assistant", "content": reply})
        self.story = reply

    @weave.op()
    def generate_outline(self, years: int) -> dict:
        target_age = self.current_age + years
        age_vars = get_age_appropriate_variables(self.current_age, years)
        prompt = (
            f"You are {self.label}. The user is currently {self.current_age} years old. "
            f"{'Fast-forward' if years > 0 else 'Go back'} {abs(years)} years to age {target_age}.\n\n"
            f"Age-appropriate variables: {age_vars}\n\n"
            f"Generate a fate outline. Respond ONLY with a JSON object, no markdown:\n"
            f'{{"city": "...", "career_title": "...", "marital_status": "...", '
            f'"children": "...", "financial_status": "...", "key_life_event": "...", '
            f'"narrative": "2-3 sentence vivid summary of this life at age {target_age}. '
            f'Write in second person. Capture the emotional texture, not just facts."}}'
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        try:
            self.outline = json.loads(raw)
        except json.JSONDecodeError:
            self.outline = {
                "city": "Unknown", "career_title": "Unknown",
                "marital_status": "Unknown", "children": "Unknown",
                "financial_status": "Unknown", "key_life_event": raw[:120],
                "narrative": raw[:200],
            }
        return self.outline

    @weave.op()
    def generate_story_from_outline(self, years: int, outline: dict) -> str:
        target_age = self.current_age + years
        age_vars = get_age_appropriate_variables(self.current_age, years)
        outline_str = "\n".join(f"- {k.replace('_',' ').title()}: {v}" for k, v in outline.items())
        if years > 0:
            time_ctx = f"You are now {target_age} years old ({years} years have passed)."
            ending = "End with one thing you're most proud of and one thing you most regret."
        else:
            time_ctx = f"You are {target_age} years old — {abs(years)} years before the crossroads."
            ending = "End with what you fear most about the choice ahead, and what you secretly hope for."
        prompt = _story_prompt(time_ctx, outline_str, age_vars, ending)
        self.story = self._call_llm(prompt, max_tokens=500)
        return self.story

    def generate_story_from_outline_streaming(self, years: int, outline: dict):
        target_age = self.current_age + years
        age_vars = get_age_appropriate_variables(self.current_age, years)
        outline_str = "\n".join(f"- {k.replace('_',' ').title()}: {v}" for k, v in outline.items())
        if years > 0:
            time_ctx = f"You are now {target_age} years old ({years} years have passed)."
            ending = "End with one thing you're most proud of and one thing you most regret. One sentence each."
        else:
            time_ctx = f"You are {target_age} years old — {abs(years)} years before the crossroads."
            ending = "End with what you fear most, and what you secretly hope for. One sentence each."
        yield from self._call_llm_streaming(_story_prompt(time_ctx, outline_str, age_vars, ending), max_tokens=500)

    @weave.op()
    def react_to_other(self, other_label: str, other_story: str) -> str:
        prompt = (
            f"You just heard the story of another version of yourself — {other_label}:\n\n"
            f"\"{other_story}\"\n\n"
            f"Respond directly. What do you feel? What do you envy? "
            f"What are you relieved you avoided? Under 100 words, raw and honest."
        )
        return self._call_llm(prompt, max_tokens=200)

    @weave.op()
    def final_reflection(self) -> str:
        prompt = (
            "Having heard all the other versions of yourself, give your final reflection. "
            "One thing you'd tell your younger self. One sentence only."
        )
        return self._call_llm(prompt, max_tokens=100)
