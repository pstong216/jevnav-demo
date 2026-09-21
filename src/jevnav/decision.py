from __future__ import annotations

from typing import Protocol

from .models import Decision, RobotState


class DecisionEngine(Protocol):
    def decide(self, state: RobotState) -> Decision: ...


class MockDecisionEngine:
    """A deterministic decision engine for a credential-free demo."""

    def decide(self, state: RobotState) -> Decision:
        if state.task_complete and "stop" in state.legal_actions:
            action = "stop"
        elif state.holding == "mug_1" and "navigate_to:sink_1" in state.legal_actions:
            action = "navigate_to:sink_1"
        elif state.holding == "mug_1" and "place:mug_1:sink_1" in state.legal_actions:
            action = "place:mug_1:sink_1"
        elif "navigate_to:mug_1" in state.legal_actions:
            action = "navigate_to:mug_1"
        elif "pick_up:mug_1" in state.legal_actions:
            action = "pick_up:mug_1"
        else:
            action = "stop"

        count = len(state.legal_actions)
        probabilities = {
            candidate: (0.96 if candidate == action else 0.04 / (count - 1))
            for candidate in state.legal_actions
        } if count > 1 else {action: 1.0}
        return Decision(
            action=action,
            action_confidence=probabilities[action],
            probabilities=probabilities,
            unsafe_probability=0.01,
            needs_planner_probability=0.02,
            complete_probability=0.99 if state.task_complete else 0.01,
            model="mock-reflex",
        )


class TypeSafeJevEngine:
    """TypeSafe SDK adapter. Import is delayed so mock mode has no dependencies."""

    def __init__(self) -> None:
        try:
            from typesafe_sdk import Choice, Noul, TypeSafeClient
        except ImportError as exc:
            raise RuntimeError("Install Jev support with: pip install -e '.[jev]'") from exc

        self._choice = Choice
        self._noul = Noul
        self._client = TypeSafeClient()

    def decide(self, state: RobotState) -> Decision:
        criteria = {
            action: _describe_action(action)
            for action in state.legal_actions
        }
        response = self._client.system_one(
            state=state.as_prompt(),
            questions={
                "next_action": self._choice(
                    instructions=(
                        "Choose the single legal high-level robot action that best advances "
                        "the goal from the current state. Do not invent an action."
                    ),
                    criteria=criteria,
                ),
                "unsafe": self._noul(
                    instructions=(
                        "Executing the most appropriate next legal action would create an "
                        "unacceptable safety or property risk."
                    )
                ),
                "needs_planner": self._noul(
                    instructions=(
                        "The state is ambiguous or requires multi-step reasoning from a stronger planner."
                    )
                ),
                "complete": self._noul(
                    instructions="The user's goal is already fully completed.",
                ),
            },
        )
        answer = response.answers["next_action"]
        return Decision(
            action=answer.choice,
            action_confidence=float(answer.confidence),
            probabilities=dict(answer.probabilities),
            unsafe_probability=float(response.answers["unsafe"].noul),
            needs_planner_probability=float(response.answers["needs_planner"].noul),
            complete_probability=float(response.answers["complete"].noul),
            model=getattr(response, "model", "jev-latest"),
        )


def _describe_action(action: str) -> str:
    verb, *args = action.split(":")
    descriptions = {
        "navigate_to": "Use the navigation controller to approach the target",
        "pick_up": "Pick up the target object when reachable",
        "place": "Place the held object into or onto the destination",
        "inspect": "Inspect a location to obtain more state information",
        "replan": "Request a new high-level plan",
        "stop": "Stop because the task is complete or no safe action exists",
    }
    suffix = f" ({', '.join(args)})" if args else ""
    return descriptions.get(verb, f"Execute {verb}") + suffix
