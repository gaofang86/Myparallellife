"""
Orchestrator agent: coordinates 4 parallel life agents via tool_use.
One LLM call → N parallel tool executions → faster + genuinely multi-agent.
"""
import os
import anthropic
from concurrent.futures import ThreadPoolExecutor
from personas import PERSONAS

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"

PERSONA_KEYS = ["steady", "maverick", "ghost", "wildcard"]

ORCHESTRATOR_SYSTEM = """You are a life simulation orchestrator coordinating 4 parallel life agents.
Each agent represents a different version of the same person at a life crossroads.
The 4 persona keys are: steady, maverick, ghost, wildcard.
When asked to run a phase, always call the provided tool for ALL 4 personas simultaneously."""

# Tool definitions
OUTLINE_TOOL = {
    "name": "run_outline",
    "description": "Generate a life outline for a persona. Call for all 4 personas at once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "persona": {"type": "string", "enum": PERSONA_KEYS}
        },
        "required": ["persona"]
    }
}

SCORE_TOOL = {
    "name": "run_score",
    "description": "Score a persona's life story. Call for all 4 personas at once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "persona": {"type": "string", "enum": PERSONA_KEYS}
        },
        "required": ["persona"]
    }
}


class LifeOrchestrator:
    def __init__(self, situation: str, age: int, years: int):
        self.situation = situation
        self.age = age
        self.years = years
        self._system = [
            {"type": "text", "text": ORCHESTRATOR_SYSTEM, "cache_control": {"type": "ephemeral"}}
        ]

    def _get_tool_calls(self, tool: dict, user_msg: str) -> list:
        """Ask orchestrator to dispatch tool calls for all personas."""
        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=self._system,
            tools=[tool],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": user_msg}],
        )
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        # Ensure all 4 personas are covered even if orchestrator missed some
        called = {tc.input["persona"] for tc in tool_calls}
        for k in PERSONA_KEYS:
            if k not in called:
                # Create a synthetic tool call for missing persona
                tool_calls.append(type("TC", (), {"input": {"persona": k}})())
        return tool_calls

    def orchestrate_outlines(self, agents: dict) -> dict:
        """One orchestrator call → 4 parallel outline generations."""
        tool_calls = self._get_tool_calls(
            OUTLINE_TOOL,
            f"Generate outlines for all 4 personas. "
            f"Situation: {self.situation}. Age: {self.age}, jump {self.years} years."
        )

        def run(tc):
            key = tc.input["persona"]
            return key, agents[key].generate_outline(self.years)

        results = {}
        with ThreadPoolExecutor(max_workers=4) as ex:
            for key, outline in ex.map(run, tool_calls):
                results[key] = outline
        return results

    def orchestrate_scores(self, agents: dict, stories: dict) -> dict:
        """One orchestrator call → 4 parallel score evaluations."""
        from judge import score_life, DIMENSIONS

        tool_calls = self._get_tool_calls(
            SCORE_TOOL,
            "Score the life stories for all 4 personas."
        )

        def run(tc):
            key = tc.input["persona"]
            label = PERSONAS[key]["label"]
            story = stories.get(key, "")
            if story:
                return key, score_life(label, story)
            return key, {d.lower(): 5 for d in DIMENSIONS}

        results = {}
        with ThreadPoolExecutor(max_workers=4) as ex:
            for key, scores in ex.map(run, tool_calls):
                results[key] = scores
        return results
